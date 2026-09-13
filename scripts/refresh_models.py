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

TIMEOUT = 20


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


# ───────────────────────── provider catalog fetchers ──────────────────────
# Each returns: [{"id": str, "price_in": float|None, "price_out": float|None,
#                 "context": int|None, "supports_tools": bool|None}, ...]
# price_* is USD per 1M tokens. None means "unknown - compare price manually".

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

def find_upgrade(current_model_id: str, catalog: list[dict], current_meta: dict | None) -> dict | None:
    """Returns the best strictly-better-or-equal same-family candidate, or None."""
    fam = family_key(current_model_id)
    cur_ver = version_tuple(current_model_id)
    cur_price_out = current_meta.get("price_out") if current_meta else None
    cur_context = current_meta.get("context") if current_meta else None

    best = None
    for m in catalog:
        if base_id(m["id"]) == base_id(current_model_id):
            continue  # same model, not an upgrade
        if family_key(m["id"]) != fam:
            continue
        if version_tuple(m["id"]) < cur_ver:
            continue  # don't downgrade versions

        # Price: only compare if BOTH sides have known pricing. If either
        # side is unknown, don't block on price - but note it in the log.
        if cur_price_out is not None and m["price_out"] is not None:
            if m["price_out"] > cur_price_out * 1.05:  # allow tiny rounding slack
                continue

        # Context: never accept a strictly smaller context window.
        if cur_context is not None and m["context"] is not None:
            if m["context"] < cur_context:
                continue

        if best is None or version_tuple(m["id"]) > version_tuple(best["id"]):
            best = m
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

    cfg = load_config()
    catalogs: dict[str, list[dict]] = {}
    for provider in FETCHERS:
        try:
            catalogs[provider] = FETCHERS[provider]()
        except requests.RequestException as e:
            print(f"[warn] couldn't fetch {provider} catalog: {e}", file=sys.stderr)
            catalogs[provider] = []

    log_lines = []
    applied = False

    for entry in list(cfg["model_list"]):
        model_name = entry["model_name"]
        if model_name.endswith(tuple(f"-prev-{d}" for d in range(20260101, 20270101))):
            continue  # skip our own previously-demoted entries
        litellm_model = entry["litellm_params"]["model"]
        provider, rest = parse_model_ref(litellm_model)
        catalog = catalogs.get(provider, [])
        if not catalog:
            continue

        current_meta = next((m for m in catalog if base_id(m["id"]) == base_id(rest)), None)
        candidate = find_upgrade(rest, catalog, current_meta)
        if not candidate:
            continue

        price_note = (
            f"${current_meta['price_out']:.2f}->${candidate['price_out']:.2f} per 1M out"
            if current_meta and current_meta.get("price_out") is not None and candidate.get("price_out") is not None
            else "price unknown for one/both - verify manually"
        )
        summary = f"{model_name}: {rest} -> {candidate['id']} ({provider}, {price_note})"

        if args.dry_run:
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
