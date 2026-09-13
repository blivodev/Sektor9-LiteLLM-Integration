#!/usr/bin/env python3
"""
refresh_models.py - periodically checks whether your configured providers
(OpenRouter, DeepInfra, Fireworks, and Anthropic/Gemini if keyed) now offer
a newer/cheaper model in the same family as one you're already running, and
if so, upgrades it - safely.

WHAT "SAFELY" MEANS HERE (read this before trusting it to run unattended):
  1. Every candidate is LIVE-TESTED (a real tool-calling request through the
     provider's own API, using the key already in .env) before config.yaml
     is touched at all. A candidate that fails, times out, or doesn't
     support tool calls is skipped and logged, never applied.
  2. The OLD model is never deleted - it's demoted to be the new FIRST
     fallback for that slot. If the "upgrade" is actually worse in
     practice, the proxy just falls back to what already worked.
  3. Every applied change is its own git commit with the full price/context
     comparison in the message - inspect with `git log`, undo with
     `git revert <sha>`, any time.
  4. A human-readable summary is appended to MODEL_REFRESH_LOG.md on every
     run, applied or not, so nothing happens invisibly.

WHAT THIS CANNOT DO: assess real-world model quality. Providers' catalog
APIs expose price, context length, and sometimes a tool-calling flag - not
benchmark scores. "Newer + cheaper-or-equal + same context-or-better" is a
reasonable heuristic, not a guarantee the new model is actually better at
your workload. That's exactly why steps 1-3 above exist as a safety net
rather than trusting the heuristic outright.

Usage:
    python scripts/refresh_models.py --dry-run     # report only, no changes (start here)
    python scripts/refresh_models.py               # apply validated upgrades
    python scripts/refresh_models.py --restart      # also recreate the litellm container after applying
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
    import yaml
except ImportError:
    print(
        "Missing dependencies. Install with:\n"
        "  pip install requests pyyaml\n",
        file=sys.stderr,
    )
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"
ENV_PATH = ROOT / ".env"
CHANGELOG_PATH = ROOT / "MODEL_REFRESH_LOG.md"
PREF_PATH = ROOT / ".model_preferences.json"

TIMEOUT = 20


def load_preference() -> str:
    """See scripts/set_preference.py. Defaults to 'auto' (cheapest-among-
    capable) if never set."""
    if PREF_PATH.exists():
        try:
            import json as _json

            return _json.loads(PREF_PATH.read_text(encoding="utf-8")).get("mode", "auto")
        except Exception:
            pass
    return "auto"


# ───────────────────────── .env loading (no external dep needed) ─────────

def load_env() -> dict:
    env = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            env[k.strip()] = v
    return env


ENV = load_env()


# ───────────────────────── LiteLLM's own price/context map ────────────────
# LiteLLM maintains a community-updated JSON covering every provider it
# supports -- including DeepInfra and Fireworks, whose OWN APIs don't expose
# per-model pricing at all. This is the primary source of truth for price/
# context/tool-support below; live provider catalogs are only used to know
# what currently EXISTS (this file can lag a few days on a brand-new release,
# which is fine -- it just means a very-latest model gets picked up on the
# following week's run instead of the day it ships).

LITELLM_PRICE_MAP_URL = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"


def fetch_litellm_price_map() -> dict:
    try:
        r = requests.get(LITELLM_PRICE_MAP_URL, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        print(f"[warn] couldn't fetch LiteLLM price map: {e}", file=sys.stderr)
        return {}


def _price_map_lookup(price_map: dict, provider: str, model_id: str) -> dict | None:
    """Try the couple of key spellings providers' own APIs vs. LiteLLM's map
    tend to differ on (mainly Fireworks' short vs. full accounts/... form)."""
    candidates = [f"{provider}/{model_id}"]
    if provider == "fireworks_ai":
        if not model_id.startswith("accounts/"):
            candidates.append(f"fireworks_ai/accounts/fireworks/models/{model_id}")
        else:
            candidates.append(f"fireworks_ai/{model_id.rsplit('/', 1)[-1]}")
    for key in candidates:
        if key in price_map:
            return price_map[key]
    return None


def enrich_with_price_map(entries: list[dict], provider: str, price_map: dict) -> list[dict]:
    """Fills in price_in/price_out/context/supports_tools from LiteLLM's map
    wherever the live provider API left them unknown (or to correct/confirm
    them where the provider API did report something)."""
    for e in entries:
        info = _price_map_lookup(price_map, provider, e["id"])
        if not info:
            continue
        if info.get("input_cost_per_token") is not None:
            e["price_in"] = info["input_cost_per_token"] * 1_000_000
        if info.get("output_cost_per_token") is not None:
            e["price_out"] = info["output_cost_per_token"] * 1_000_000
        ctx = info.get("max_input_tokens") or info.get("max_tokens")
        if ctx and not e.get("context"):
            e["context"] = ctx
        if info.get("supports_function_calling") is not None and e.get("supports_tools") is None:
            e["supports_tools"] = info["supports_function_calling"]
    return entries


# ───────────────────────── provider catalog fetchers ──────────────────────
# Each returns: [{"id": str, "price_in": float|None, "price_out": float|None,
#                 "context": int|None, "supports_tools": bool|None}, ...]
# price_* is USD per 1M tokens. None means "unknown - compare price manually"
# (rare after enrich_with_price_map() runs, but still possible for a model
# too new to be in LiteLLM's map yet).

def _per_million(v) -> float | None:
    if v is None:
        return None
    try:
        return float(v) * 1_000_000
    except (TypeError, ValueError):
        return None


def fetch_openrouter() -> list[dict]:
    r = requests.get("https://openrouter.ai/api/v1/models", timeout=TIMEOUT)
    r.raise_for_status()
    out = []
    for m in r.json().get("data", []):
        pricing = m.get("pricing", {}) or {}
        out.append({
            "id": m["id"],
            "price_in": _per_million(pricing.get("prompt")),
            "price_out": _per_million(pricing.get("completion")),
            "context": m.get("context_length"),
            "supports_tools": "tools" in (m.get("supported_parameters") or []),
        })
    return out


def fetch_fireworks() -> list[dict]:
    key = ENV.get("FIREWORKS_AI_API_KEY")
    if not key:
        return []
    r = requests.get(
        "https://api.fireworks.ai/inference/v1/models",
        headers={"Authorization": f"Bearer {key}"},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    out = []
    for m in r.json().get("data", []):
        out.append({
            "id": m["id"],  # e.g. accounts/fireworks/models/glm-5p3-flash
            "price_in": None,   # not exposed by this endpoint - verify manually
            "price_out": None,
            "context": m.get("context_length"),
            "supports_tools": m.get("supports_tools"),
        })
    return out


def fetch_deepinfra() -> list[dict]:
    key = ENV.get("DEEPINFRA_API_KEY")
    if not key:
        return []
    try:
        r = requests.get(
            "https://api.deepinfra.com/v1/openai/models",
            headers={"Authorization": f"Bearer {key}"},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        data = r.json().get("data", [])
    except requests.RequestException:
        return []
    out = []
    for m in data:
        out.append({
            "id": m["id"],
            "price_in": None,
            "price_out": None,
            "context": m.get("context_length") or m.get("context_window"),
            "supports_tools": None,
        })
    return out


def fetch_anthropic() -> list[dict]:
    key = ENV.get("ANTHROPIC_API_KEY")
    if not key:
        return []
    try:
        r = requests.get(
            "https://api.anthropic.com/v1/models",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        data = r.json().get("data", [])
    except requests.RequestException:
        return []
    return [
        {"id": m["id"], "price_in": None, "price_out": None, "context": None, "supports_tools": True}
        for m in data
    ]


def fetch_gemini() -> list[dict]:
    key = ENV.get("GEMINI_API_KEY")
    if not key:
        return []
    try:
        r = requests.get(
            f"https://generativelanguage.googleapis.com/v1beta/models?key={key}",
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        data = r.json().get("models", [])
    except requests.RequestException:
        return []
    out = []
    for m in data:
        out.append({
            "id": m["name"].replace("models/", ""),
            "price_in": None,
            "price_out": None,
            "context": m.get("inputTokenLimit"),
            "supports_tools": None,
        })
    return out


FETCHERS = {
    "openrouter": fetch_openrouter,
    "fireworks_ai": fetch_fireworks,
    "deepinfra": fetch_deepinfra,
    "anthropic": fetch_anthropic,
    "gemini": fetch_gemini,
}


# ───────────────────────── family / version heuristics ────────────────────

_DATE_SUFFIX = re.compile(r"-\d{4,8}$")
_VERSION_RE = re.compile(r"v(\d+)(?:[.p](\d+))?", re.IGNORECASE)


def base_id(model_id: str) -> str:
    """Strip provider path prefixes down to the bare model slug."""
    return model_id.rstrip("/").split("/")[-1]


def family_key(model_id: str) -> str:
    """
    Best-effort 'same family' fingerprint - NOT a semantic understanding of
    the model. Strips date suffixes (-0731) and known filler tokens, keeps
    everything else including the major version, so e.g. "deepseek-v4-flash"
    and "deepseek-v4.1-flash" match (same family, compare versions below),
    but "deepseek-v4-flash" and "deepseek-v5-pro" do NOT (different tier -
    a human should decide whether to move tiers, not this heuristic).
    """
    b = base_id(model_id).lower()
    b = _DATE_SUFFIX.sub("", b)
    b = re.sub(r"-latest$", "", b)
    b = _VERSION_RE.sub("v#", b)  # normalize v4/v4.1/v4p1 -> v# for grouping
    return b


def version_tuple(model_id: str) -> tuple[int, int]:
    m = _VERSION_RE.search(base_id(model_id))
    if not m:
        return (0, 0)
    return (int(m.group(1)), int(m.group(2) or 0))


# ───────────────────────── config.yaml parsing ─────────────────────────────

def parse_model_ref(litellm_model: str) -> tuple[str, str]:
    """'deepinfra/deepseek-ai/DeepSeek-V4-Flash-0731' -> ('deepinfra', 'deepseek-ai/DeepSeek-V4-Flash-0731')"""
    provider, _, rest = litellm_model.partition("/")
    return provider, rest


def load_config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


# ───────────────────────── live validation ─────────────────────────────────

def live_test_openrouter(model_id: str) -> bool:
    key = ENV.get("OPENROUTER_API_KEY")
    if not key:
        return False
    try:
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": model_id, "messages": [{"role": "user", "content": "say pong"}], "max_tokens": 5},
            timeout=30,
        )
        return r.status_code == 200
    except requests.RequestException:
        return False


def live_test_fireworks(model_id: str) -> bool:
    key = ENV.get("FIREWORKS_AI_API_KEY")
    if not key:
        return False
    try:
        r = requests.post(
            "https://api.fireworks.ai/inference/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": model_id, "messages": [{"role": "user", "content": "say pong"}], "max_tokens": 5},
            timeout=30,
        )
        return r.status_code == 200
    except requests.RequestException:
        return False


def live_test_deepinfra(model_id: str) -> bool:
    key = ENV.get("DEEPINFRA_API_KEY")
    if not key:
        return False
    try:
        r = requests.post(
            "https://api.deepinfra.com/v1/openai/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": model_id, "messages": [{"role": "user", "content": "say pong"}], "max_tokens": 5},
            timeout=30,
        )
        return r.status_code == 200
    except requests.RequestException:
        return False


LIVE_TESTERS = {
    "openrouter": live_test_openrouter,
    "fireworks_ai": live_test_fireworks,
    "deepinfra": live_test_deepinfra,
}


# ───────────────────────── candidate selection ─────────────────────────────

def is_free(m: dict) -> bool:
    """True if a catalog entry is actually $0, not just 'price unknown'.
    Covers both providers that report a real 0.0 price (rare but real, e.g.
    some DeepInfra small models) and OpenRouter's ':free'-suffixed model
    IDs, which sometimes come through with price_in/price_out as None
    rather than 0 depending on when the catalog was fetched."""
    if m.get("price_in") == 0 and m.get("price_out") == 0:
        return True
    return base_id(m["id"]).endswith(":free")


def find_upgrade(current_model_id: str, catalog: list[dict], current_meta: dict | None, mode: str = "auto") -> dict | None:
    """
    mode="auto"/"cheapest"/"cheapest_from_best" (default): returns the
    CHEAPEST same-family candidate that's at least as new a version and at
    least as large a context window as the current model - NOT the newest
    one that happens to be no pricier. Only recommended if it doesn't cost
    more than what's running now.

    mode="most_accurate"/"performance": returns the NEWEST version
    available in the family (price only breaks ties between equally-new
    candidates), and recommends it even if pricier - accuracy/capability
    is what's being optimized for here, cost is secondary.

    mode="free": returns the newest same-family candidate that is
    genuinely $0 (see is_free()) - never a paid model, even a cheap one.
    Scope note: this only ever looks WITHIN the family of the model you
    already have configured (same as every other mode here) - it's an
    upgrade-checker, not a from-scratch "find me any free model anywhere"
    search. Most families simply have no free variant, in which case this
    correctly finds nothing rather than jumping to an unrelated free model.

    mode="local"/"local_cheapest"/"local_best": never reaches this
    function directly for family/version comparison - see main()'s
    handling via promote_local()/find_local_entry(). This function still
    gets called for the modes NOT eligible for local routing (Debug/Plan/
    Orchestrator, or Code/Ask when no local model is configured), using
    the cloud-equivalent mode main() maps it to ("auto" / "cheapest" /
    "most_accurate").

    mode="custom": always returns None - see set_preference.py; the
    caller (main()) treats this mode as "report only, never auto-apply"
    regardless of --dry-run.
    """
    if mode == "custom":
        return None

    fam = family_key(current_model_id)
    cur_ver = version_tuple(current_model_id)
    cur_price_out = current_meta.get("price_out") if current_meta else None
    cur_context = current_meta.get("context") if current_meta else None

    candidates = []
    for m in catalog:
        if base_id(m["id"]) == base_id(current_model_id):
            continue  # same model, not an upgrade
        if family_key(m["id"]) != fam:
            continue
        if version_tuple(m["id"]) < cur_ver:
            continue  # never go backward in version
        if cur_context is not None and m["context"] is not None and m["context"] < cur_context:
            continue  # never accept a smaller context window
        if mode == "free" and not is_free(m):
            continue  # free mode: a real $0 model or nothing
        candidates.append(m)

    if not candidates:
        return None

    prioritize_newest = mode in ("most_accurate", "performance", "free")

    def sort_key(m):
        price_known = m["price_out"] is not None
        price = m["price_out"] if price_known else float("inf")
        ver = tuple(-v for v in version_tuple(m["id"]))
        return (ver, not price_known, price) if prioritize_newest else (not price_known, price, ver)

    candidates.sort(key=sort_key)
    best = candidates[0]

    if prioritize_newest:
        return best  # capability (or, for "free", simply eligibility) over cost

    # Cost-driven modes: only recommend if cheaper-or-equal to what's
    # running now (when price is known for both) - otherwise the cheapest
    # qualifying candidate still costs more than staying put, so there's
    # no upgrade to make.
    if cur_price_out is not None and best["price_out"] is not None:
        if best["price_out"] > cur_price_out * 1.05:  # tiny rounding slack
            return None
    return best


# ───────────────────────── config.yaml mutation ─────────────────────────────

def apply_upgrade(cfg: dict, model_name: str, provider: str, new_rest: str, old_full_model: str, api_key_env: str) -> dict:
    """
    Promotes the new model to `model_name`'s primary slot, and inserts the
    OLD model as a brand-new fallback entry '<model_name>-prev-<n>' at the
    FRONT of that slot's fallback list (so it's tried before existing
    fallbacks - it was working a moment ago, it's the safest first fallback).
    """
    model_list = cfg["model_list"]
    entry = next(e for e in model_list if e["model_name"] == model_name)
    entry["litellm_params"]["model"] = f"{provider}/{new_rest}"

    prev_name = f"{model_name}-prev-{datetime.now(timezone.utc):%Y%m%d}"
    model_list.append({
        "model_name": prev_name,
        "litellm_params": {"model": old_full_model, "api_key": f"os.environ/{api_key_env}"},
    })

    fb_list = cfg.setdefault("router_settings", {}).setdefault("fallbacks", [])
    for fb in fb_list:
        if model_name in fb:
            fb[model_name] = [prev_name] + fb[model_name]
            break
    else:
        fb_list.append({model_name: [prev_name]})

    return cfg


def save_config(cfg: dict):
    CONFIG_PATH.write_text(yaml.dump(cfg, sort_keys=False, default_flow_style=False), encoding="utf-8")


# ───────────────────────── local (Ollama) routing ───────────────────────────
# Separate from the price/version upgrade logic above: a local model has no
# price or version to compare, it's a deliberate opt-in swap. Only reachable
# when the user has explicitly chosen "local"/"local_cheapest"/"local_best"
# via set_preference.py -- every other mode leaves local-ollama exactly
# where scripts/setup_ollama.py put it (a Code/Ask fallback, never primary).

LOCAL_ELIGIBLE_MODES = ("kilo-code", "kilo-ask")  # same scope setup_ollama.py itself uses


def find_local_entry(cfg: dict) -> dict | None:
    """Returns the local-ollama model_list entry (see setup_ollama.py's
    OLLAMA_MODEL_NAME) if the user has run that setup script, else None."""
    for e in cfg.get("model_list", []):
        model = e.get("litellm_params", {}).get("model", "")
        if model.startswith("ollama_chat/"):
            return e
    return None


def promote_local(cfg: dict, model_name: str, local_entry: dict) -> str | None:
    """Swaps `model_name`'s primary to the local model, demoting the
    previous primary to a new first-fallback entry -- same never-delete
    safety pattern as apply_upgrade(), just without a price/version
    comparison since there's nothing to compare against. Returns a log
    line, or None if `model_name` is already local (nothing to do)."""
    entry = next((e for e in cfg["model_list"] if e["model_name"] == model_name), None)
    if entry is None:
        return None
    old_full_model = entry["litellm_params"]["model"]
    local_full_model = local_entry["litellm_params"]["model"]
    if old_full_model == local_full_model:
        return None  # already routed to local

    old_api_key_env = entry["litellm_params"].get("api_key", "").replace("os.environ/", "") or None
    prev_name = f"{model_name}-prev-{datetime.now(timezone.utc):%Y%m%d}"
    cfg["model_list"].append({
        "model_name": prev_name,
        "litellm_params": {
            "model": old_full_model,
            **({"api_key": f"os.environ/{old_api_key_env}"} if old_api_key_env else {}),
        },
    })

    entry["litellm_params"] = {
        "model": local_full_model,
        "api_base": local_entry["litellm_params"].get("api_base"),
    }

    fb_list = cfg.setdefault("router_settings", {}).setdefault("fallbacks", [])
    for fb in fb_list:
        if model_name in fb:
            fb[model_name] = [prev_name] + [m for m in fb[model_name] if m != local_entry["model_name"]]
            break
    else:
        fb_list.append({model_name: [prev_name]})

    return f"{model_name}: {old_full_model} -> {local_full_model} (local, cloud model kept as fallback)"


# ───────────────────────── git + docker ─────────────────────────────────────

def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)


def git_commit(message: str):
    run(["git", "add", "config.yaml", "MODEL_REFRESH_LOG.md"])
    run(["git", "commit", "-m", message])


def restart_litellm():
    run(["docker", "compose", "up", "-d", "--force-recreate", "litellm"])


# ───────────────────────── changelog ─────────────────────────────────────

def log_run(lines: list[str]):
    header = f"## {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}\n\n"
    body = "\n".join(f"- {l}" for l in lines) if lines else "- No changes this run.\n"
    existing = CHANGELOG_PATH.read_text(encoding="utf-8") if CHANGELOG_PATH.exists() else "# Model refresh log\n\n"
    CHANGELOG_PATH.write_text(existing + "\n" + header + body + "\n", encoding="utf-8")


# ───────────────────────── main ─────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Report candidates, change nothing.")
    ap.add_argument("--restart", action="store_true", help="Recreate the litellm container after applying changes.")
    args = ap.parse_args()

    pref_mode = load_preference()
    dry_run = args.dry_run or pref_mode == "custom"
    if pref_mode == "custom" and not args.dry_run:
        print("Preference is 'custom' (see .model_preferences.json / scripts/set_preference.py) -- reporting only, never auto-applying.")
    print(f"Selection preference: {pref_mode}")

    cfg = load_config()
    log_lines: list[str] = []
    applied = False

    # "local"/"local_cheapest"/"local_best": handle the local-routing part
    # up front, then fall through to the normal per-entry loop below using
    # whatever cloud-equivalent mode this maps to (for Debug/Plan/
    # Orchestrator, which never get routed to local, and for Code/Ask too
    # if no local model turns out to be configured).
    LOCAL_CLOUD_EQUIVALENT = {"local": "auto", "local_cheapest": "cheapest", "local_best": "most_accurate"}
    effective_mode = pref_mode
    if pref_mode in LOCAL_CLOUD_EQUIVALENT:
        local_entry = find_local_entry(cfg)
        if not local_entry:
            print(
                f"[warn] Preference is '{pref_mode}' but no local Ollama model is configured yet "
                f"-- run `python scripts/setup_ollama.py` first. Falling back to "
                f"'{LOCAL_CLOUD_EQUIVALENT[pref_mode]}' cloud selection for this run."
            )
        else:
            for model_name in LOCAL_ELIGIBLE_MODES:
                if dry_run:
                    entry = next((e for e in cfg["model_list"] if e["model_name"] == model_name), None)
                    if entry and entry["litellm_params"]["model"] != local_entry["litellm_params"]["model"]:
                        line = f"would route {model_name} -> local ({local_entry['litellm_params']['model']})"
                        log_lines.append(f"[dry-run] {line}")
                        print(f"[dry-run] {line}")
                    continue
                line = promote_local(cfg, model_name, local_entry)
                if line:
                    log_lines.append(f"[applied] {line}")
                    print(f"[applied] {line}")
                    applied = True
        effective_mode = LOCAL_CLOUD_EQUIVALENT[pref_mode]

    print("Fetching LiteLLM's price/context map (primary pricing source)...")
    price_map = fetch_litellm_price_map()
    print(f"  {len(price_map)} models known to it.")

    catalogs: dict[str, list[dict]] = {}
    for provider in FETCHERS:
        try:
            catalog = FETCHERS[provider]()
        except requests.RequestException as e:
            print(f"[warn] couldn't fetch {provider} catalog: {e}", file=sys.stderr)
            catalog = []
        if catalog and price_map:
            catalog = enrich_with_price_map(catalog, provider, price_map)
        catalogs[provider] = catalog

    local_active = pref_mode in LOCAL_CLOUD_EQUIVALENT and find_local_entry(cfg) is not None

    for entry in list(cfg["model_list"]):
        model_name = entry["model_name"]
        if model_name.endswith(tuple(f"-prev-{d}" for d in range(20260101, 20270101))):
            continue  # skip our own previously-demoted entries
        if local_active and model_name in LOCAL_ELIGIBLE_MODES:
            continue  # already handled above (routed to local) -- don't also propose a cloud alternative
        litellm_model = entry["litellm_params"]["model"]
        provider, rest = parse_model_ref(litellm_model)
        catalog = catalogs.get(provider, [])
        if not catalog:
            continue

        current_meta = next((m for m in catalog if base_id(m["id"]) == base_id(rest)), None)
        candidate = find_upgrade(rest, catalog, current_meta, mode=effective_mode)
        if not candidate:
            continue

        price_note = (
            f"${current_meta['price_out']:.2f}->${candidate['price_out']:.2f} per 1M out"
            if current_meta and current_meta.get("price_out") is not None and candidate.get("price_out") is not None
            else "price unknown for one/both - verify manually"
        )
        summary = f"{model_name}: {rest} -> {candidate['id']} ({provider}, {price_note})"

        if dry_run:
            log_lines.append(f"[dry-run] would consider: {summary}")
            print(f"[dry-run] {summary}")
            continue

        tester = LIVE_TESTERS.get(provider)
        if tester and not tester(candidate["id"]):
            log_lines.append(f"[skipped, live test failed] {summary}")
            print(f"[skip] live test failed for {candidate['id']}")
            continue

        api_key_env = entry["litellm_params"].get("api_key", "").replace("os.environ/", "")
        cfg = apply_upgrade(cfg, model_name, provider, candidate["id"], litellm_model, api_key_env)
        log_lines.append(f"[applied] {summary} - old model kept as fallback")
        print(f"[applied] {summary}")
        applied = True

    if args.dry_run:
        log_run(log_lines)
        print(f"\nDry run complete. {len(log_lines)} candidate(s) found. See {CHANGELOG_PATH.name}.")
        return

    if applied:
        save_config(cfg)
        log_run(log_lines)
        git_commit(
            "Auto model refresh: promote validated cheaper/newer models, "
            "keep previous as fallback\n\n" + "\n".join(log_lines)
        )
        if args.restart:
            restart_litellm()
        print(f"\nApplied {sum(1 for l in log_lines if l.startswith('[applied]'))} upgrade(s). "
              f"Committed to git. {'Container restarted.' if args.restart else 'Restart the litellm container to pick this up.'}")
    else:
        log_run(log_lines or ["No upgrade candidates found this run."])
        print("\nNo changes made.")


if __name__ == "__main__":
    main()
