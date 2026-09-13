#!/usr/bin/env python3
"""
LiteLLM Workflow Dashboard — one simple local page for everything in this
project: container/MCP health, provider balances, API key configuration
(writes .env AND re-propagates to every configured editor automatically),
and a unified log viewer.

Not fancy on purpose — a handful of Flask routes and inline HTML, nothing
that needs a build step or a framework. Run it, look at it, close it.

Usage:
    python dashboard/app.py
    -> http://127.0.0.1:8877
"""
from __future__ import annotations

import html
import json
import os
import re
import secrets
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, abort, jsonify, request, session

try:
    import requests
except ImportError:
    print("pip install requests flask", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
CONFIG_PATH = ROOT / "config.yaml"
LITELLM_URL = "http://127.0.0.1:4000"

# Reuse scripts/refresh_models.py's provider fetchers + price enrichment and
# scripts/set_preference.py's mode list, rather than re-implementing either
# here -- one definition of "how do we know what a model costs" / "what do
# the preference modes mean", used by both the CLI and this dashboard.
sys.path.insert(0, str(ROOT / "scripts"))
import refresh_models as rm  # noqa: E402
import set_preference as sp  # noqa: E402

PREF_PATH = ROOT / ".model_preferences.json"

# Only these two containers may ever be named on the /logs route -- closes
# both the reflected-XSS and the docker-argument-injection findings from the
# security review (the raw ?c= value used to be interpolated into HTML *and*
# passed straight to `docker logs` as an argv item).
KNOWN_CONTAINERS = {"litellm_proxy", "litellm_db"}

app = Flask(__name__)
# A fresh random secret per process is fine here: this is a single-user,
# localhost-only dashboard, so a restart just means the browser silently
# gets a new session (and a new CSRF token) next load -- nothing persists
# that needs to survive that. Only used to sign the session cookie that
# carries the CSRF token below.
app.secret_key = secrets.token_hex(32)


def csrf_token() -> str:
    """Get-or-create a per-session CSRF token, stored server-side via the
    signed session cookie. Every state-changing form embeds it as a hidden
    field; every state-changing POST verifies it before doing anything."""
    tok = session.get("csrf_token")
    if not tok:
        tok = secrets.token_hex(20)
        session["csrf_token"] = tok
    return tok


def require_csrf() -> None:
    submitted = request.form.get("csrf_token", "")
    expected = session.get("csrf_token", "")
    if not expected or not secrets.compare_digest(submitted, expected):
        abort(403, "Missing or invalid CSRF token -- reload the page and try again.")
    # Defense in depth: a same-origin request should carry a matching
    # Origin/Referer. Cross-site posts (the actual CSRF attack shape) either
    # omit it or carry the attacker's origin.
    #
    # NOTE (security review caught this): a plain .startswith("http://
    # localhost:8877") check is bypassable -- "http://localhost:8877.evil.
    # com" and "http://localhost:88779999" both start with that exact
    # string too. Parse properly and compare scheme+hostname+port instead.
    origin = request.headers.get("Origin") or request.headers.get("Referer") or ""
    if origin:
        try:
            parsed = urlparse(origin)
            port_ok = parsed.port == 8877
            host_ok = parsed.hostname in ("localhost", "127.0.0.1")
            allowed = parsed.scheme in ("http", "https") and host_ok and port_ok
        except ValueError:
            allowed = False  # unparseable port etc. -- deny rather than 500
        if not allowed:
            abort(403, "Request origin did not match the dashboard -- refused.")

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>LiteLLM Workflow Dashboard</title>
<style>
body{{font-family:system-ui,sans-serif;background:#0d1117;color:#c9d1d9;margin:0}}
nav{{background:#161b22;padding:12px 20px;display:flex;gap:20px;align-items:center;border-bottom:1px solid #30363d}}
nav a{{color:#58a6ff;text-decoration:none;font-size:14px}}
nav a:hover{{text-decoration:underline}}
nav b{{color:#c9d1d9;margin-right:10px}}
main{{padding:20px;max-width:1000px}}
h2{{border-bottom:1px solid #30363d;padding-bottom:8px}}
table{{width:100%;border-collapse:collapse;margin:10px 0}}
td,th{{padding:6px 10px;border-bottom:1px solid #21262d;text-align:left;font-size:14px}}
.ok{{color:#3fb950}} .bad{{color:#f85149}} .warn{{color:#d29922}}
pre{{background:#161b22;padding:12px;border-radius:6px;overflow-x:auto;font-size:12px;max-height:400px}}
input[type=text],input[type=password]{{background:#0d1117;border:1px solid #30363d;color:#c9d1d9;padding:6px;width:420px;font-family:monospace}}
button{{background:#238636;color:white;border:none;padding:8px 16px;border-radius:6px;cursor:pointer;margin-top:10px}}
.row{{margin:6px 0}}
label{{display:inline-block;width:220px;font-size:13px}}
.card{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px;margin-bottom:16px}}
</style></head><body>
<nav><b>LiteLLM Dashboard</b>
<a href="/">Overview</a><a href="/balances">Balances</a><a href="/keys">API Keys</a>
<a href="/preference">Preference</a><a href="/routing">Custom Routing</a><a href="/models">Models</a>
<a href="/mcp">MCP Servers</a><a href="/logs">Logs</a>
</nav>
<main>{content}</main></body></html>"""


def docker_ps() -> list[dict]:
    r = subprocess.run(["docker", "ps", "-a", "--filter", "name=litellm_", "--format", "{{.Names}}|{{.Status}}"],
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = []
    for line in r.stdout.strip().splitlines():
        if "|" in line:
            name, status = line.split("|", 1)
            out.append({"name": name, "status": status, "up": status.startswith("Up")})
    return out


def litellm_health() -> tuple[bool, str]:
    try:
        r = requests.get(f"{LITELLM_URL}/health/liveliness", timeout=3)
        return r.status_code == 200, f"HTTP {r.status_code}"
    except requests.RequestException as e:
        return False, str(e)


def master_key() -> str | None:
    if not ENV_PATH.exists():
        return None
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith("LITELLM_MASTER_KEY="):
            return line.split("=", 1)[1].strip()
    return None


def mcp_servers() -> list[dict]:
    key = master_key()
    if not key:
        return []
    try:
        servers = requests.get(f"{LITELLM_URL}/v1/mcp/server", headers={"Authorization": f"Bearer {key}"}, timeout=5).json()
        health = requests.get(f"{LITELLM_URL}/v1/mcp/server/health", headers={"Authorization": f"Bearer {key}"}, timeout=15).json()
        status_by_id = {h["server_id"]: h["status"] for h in health}
        return [
            {"name": s.get("alias") or s.get("server_name"), "status": status_by_id.get(s["server_id"], "unknown")}
            for s in servers
        ]
    except Exception as e:
        return [{"name": f"error: {e}", "status": "error"}]


# ───────────────────────── shared model catalog (for /models + /routing) ──
# Fetching every provider's catalog + the LiteLLM price map on every page
# load would be slow and hammers each provider's API for no reason -- cache
# in-memory for a few minutes; ?refresh=1 on /models forces a re-fetch.
_catalog_cache: dict = {"at": 0.0, "data": []}
CATALOG_TTL = 300  # seconds


def get_model_catalog(force: bool = False) -> list[dict]:
    if not force and _catalog_cache["data"] and (time.time() - _catalog_cache["at"]) < CATALOG_TTL:
        return _catalog_cache["data"]
    price_map = rm.fetch_litellm_price_map()
    flat: list[dict] = []
    for provider, fetcher in rm.FETCHERS.items():
        try:
            entries = fetcher()
        except Exception:
            entries = []
        if not entries:
            continue  # no key configured for this provider, or the fetch failed -- nothing to show
        if price_map:
            entries = rm.enrich_with_price_map(entries, provider, price_map)
        for e in entries:
            flat.append({
                "provider": provider,
                "id": e["id"],
                "full_model": f"{provider}/{e['id']}",
                "price_in": e.get("price_in"),
                "price_out": e.get("price_out"),
                "context": e.get("context"),
                "supports_tools": e.get("supports_tools"),
            })
    _catalog_cache["at"] = time.time()
    _catalog_cache["data"] = flat
    return flat


@app.route("/api/models")
def api_models():
    force = request.args.get("refresh") == "1"
    return jsonify(get_model_catalog(force=force))


@app.route("/models")
def models_page():
    content = """<div class="card"><h2>Available models</h2>
    <p>Every model your configured providers currently expose, with LiteLLM's
    community price map filled in where a provider's own API doesn't report
    pricing. Only providers with a key in <a href="/keys">API keys</a> show up
    here. Used by <a href="/routing">Custom routing</a> to pick a model for a
    mode -- also just useful on its own to compare prices.</p>
    <p><input id="q" type="text" placeholder="Search (id, provider...)" style="width:100%;max-width:600px">
    <button onclick="loadModels(true)" style="margin-left:8px">Refresh from providers</button>
    <span id="count" style="margin-left:8px;color:#8b949e"></span></p>
    <div style="overflow-x:auto"><table id="tbl"><thead><tr>
    <th>Provider</th><th>Model</th><th>$ in /1M</th><th>$ out /1M</th><th>Context</th><th>Tools</th>
    </tr></thead><tbody id="rows"><tr><td colspan=6>Loading…</td></tr></tbody></table></div></div>
    <script>
    let ALL = [];
    function fmtPrice(v){ return (v===null||v===undefined) ? '?' : ('$'+Number(v).toFixed(3)); }
    function render(list){
      const rows = document.getElementById('rows');
      document.getElementById('count').textContent = list.length + ' model(s)';
      if(!list.length){ rows.innerHTML = '<tr><td colspan=6>No models -- add a provider API key first.</td></tr>'; return; }
      rows.innerHTML = list.map(m => `<tr>
        <td>${m.provider}</td><td><code>${m.id}</code></td>
        <td>${fmtPrice(m.price_in)}</td><td>${fmtPrice(m.price_out)}</td>
        <td>${m.context ?? '?'}</td><td>${m.supports_tools === true ? 'yes' : (m.supports_tools === false ? 'no' : '?')}</td>
      </tr>`).join('');
    }
    function applyFilter(){
      const q = document.getElementById('q').value.toLowerCase();
      render(q ? ALL.filter(m => (m.provider+' '+m.id).toLowerCase().includes(q)) : ALL);
    }
    async function loadModels(refresh){
      document.getElementById('rows').innerHTML = '<tr><td colspan=6>Loading' + (refresh ? ' (re-fetching from providers, can take a few seconds)' : '') + '…</td></tr>';
      const r = await fetch('/api/models' + (refresh ? '?refresh=1' : ''));
      ALL = await r.json();
      applyFilter();
    }
    document.getElementById('q').addEventListener('input', applyFilter);
    loadModels(false);
    </script>"""
    return PAGE.format(content=content)


@app.route("/")
def overview():
    containers = docker_ps()
    healthy, detail = litellm_health()
    rows = "".join(
        f'<tr><td>{c["name"]}</td><td class="{"ok" if c["up"] else "bad"}">{c["status"]}</td></tr>'
        for c in containers
    )
    content = f"""
    <div class="card"><h2>Containers</h2><table>{rows or '<tr><td colspan=2>none found</td></tr>'}</table></div>
    <div class="card"><h2>LiteLLM proxy</h2>
    <p class="{'ok' if healthy else 'bad'}">{'✅ healthy' if healthy else '❌ unreachable'} ({detail})</p>
    <p><a href="http://127.0.0.1:4000/ui" target="_blank">Open LiteLLM Admin UI →</a></p></div>
    <div class="card"><h2>Quick links</h2>
    <p><a href="/balances">Provider balances</a> · <a href="/mcp">MCP server health</a> ·
    <a href="/keys">Configure API keys</a> · <a href="/preference">Model preference</a> ·
    <a href="/routing">Custom routing</a> · <a href="/models">Available models</a> · <a href="/logs">View logs</a></p></div>
    """
    return PAGE.format(content=content)


@app.route("/mcp")
def mcp():
    servers = mcp_servers()
    healthy_count = sum(1 for s in servers if s["status"] == "healthy")
    rows = "".join(
        f'<tr><td>{s["name"]}</td><td class="{"ok" if s["status"]=="healthy" else "bad"}">{s["status"]}</td></tr>'
        for s in servers
    )
    content = f"""<div class="card"><h2>MCP Servers ({healthy_count}/{len(servers)} healthy)</h2>
    <table><tr><th>Name</th><th>Status</th></tr>{rows}</table></div>"""
    return PAGE.format(content=content)


@app.route("/balances")
def balances():
    env = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()

    rows = []
    or_key = env.get("OPENROUTER_API_KEY")
    if or_key:
        try:
            j = requests.get("https://openrouter.ai/api/v1/credits", headers={"Authorization": f"Bearer {or_key}"}, timeout=8).json()
            remaining = j["data"]["total_credits"] - j["data"]["total_usage"]
            rows.append(("OpenRouter", f"${remaining:.2f}", "ok" if remaining > 5 else "warn"))
        except Exception as e:
            rows.append(("OpenRouter", f"error: {e}", "bad"))

    di_key = env.get("DEEPINFRA_API_KEY")
    if di_key:
        try:
            j = requests.get("https://api.deepinfra.com/v1/me?checklist=true", headers={"Authorization": f"Bearer {di_key}"}, timeout=8).json()
            cl = j.get("checklist", {})
            limit, recent = cl.get("limit"), cl.get("recent")
            remaining = (limit - recent) if (limit is not None and recent is not None) else -cl.get("stripe_balance", 0)
            rows.append(("DeepInfra", f"${remaining:.2f}", "ok" if remaining > 5 else "warn"))
        except Exception as e:
            rows.append(("DeepInfra", f"error: {e}", "bad"))

    rows.append(("Fireworks / Claude / Gemini", "see VS Code status bar extension (manual-budget tracking not ported here)", "warn"))

    table = "".join(f'<tr><td>{n}</td><td class="{c}">{v}</td></tr>' for n, v, c in rows)
    content = f"""<div class="card"><h2>Provider balances</h2>
    <table><tr><th>Provider</th><th>Remaining</th></tr>{table}</table></div>"""
    return PAGE.format(content=content)


ENV_VAR_LABELS = [
    ("OPENROUTER_API_KEY", "OpenRouter"),
    ("DEEPINFRA_API_KEY", "DeepInfra"),
    ("FIREWORKS_AI_API_KEY", "Fireworks AI"),
    ("ANTHROPIC_API_KEY", "Anthropic (claude escape hatch)"),
    ("GEMINI_API_KEY", "Gemini (gemini escape hatch)"),
    ("SSH_HOST", "SSH MCP: host"),
    ("SSH_USERNAME", "SSH MCP: username"),
    ("SSH_PASSWORD", "SSH MCP: password"),
    ("MESHY_API_KEY", "Meshy AI (3D gen)"),
    ("TRIPO_API_SECRET", "Tripo3D (3D gen)"),
    ("ELEVENLABS_API_KEY", "ElevenLabs (voice)"),
    ("ACEDATACLOUD_API_TOKEN", "AceDataCloud (Suno music)"),
]


def read_env_dict() -> dict:
    env = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


@app.route("/keys", methods=["GET", "POST"])
def keys():
    if request.method == "POST":
        require_csrf()
        env = read_env_dict()
        for var, _ in ENV_VAR_LABELS:
            val = request.form.get(var, "").strip()
            if val:  # blank = leave unchanged, never blank out a working key by accident
                env[var] = val

        lines = []
        seen = set()
        for line in (ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []):
            if "=" in line and not line.lstrip().startswith("#"):
                k = line.split("=", 1)[0].strip()
                if k in env:
                    lines.append(f"{k}={env[k]}")
                    seen.add(k)
                    continue
            lines.append(line)
        for k, v in env.items():
            if k not in seen:
                lines.append(f"{k}={v}")
        ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
        try:
            os.chmod(ENV_PATH, 0o600)  # owner-only where the OS honors it -- this file holds every secret
        except OSError:
            pass

        results = ["Wrote .env"]
        r = subprocess.run(["docker", "compose", "up", "-d", "--force-recreate", "litellm"],
                            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
        results.append("Restarted litellm container" if r.returncode == 0 else f"Container restart FAILED: {r.stderr[-300:]}")

        for script in ["editors/cline/install.py", "editors/zed/install.py"]:
            p = ROOT / script
            if p.exists():
                r = subprocess.run([sys.executable, str(p)], capture_output=True, text=True, encoding="utf-8", errors="replace")
                results.append(f"{script}: {'ok' if r.returncode == 0 else 'FAILED'} — {r.stdout.strip().splitlines()[-1] if r.stdout else r.stderr[-200:]}")

        content = "<div class='card'><h2>Applied</h2><pre>" + "\n".join(results) + "</pre><p><a href='/keys'>Back</a></p></div>"
        return PAGE.format(content=content)

    env = read_env_dict()
    rows = ""
    for var, label in ENV_VAR_LABELS:
        current = env.get(var, "")
        masked = (current[:4] + "…") if current else "(not set)"
        rows += f'<div class="row"><label>{label}</label><input type="password" name="{var}" placeholder="{masked}"></div>'
    content = f"""<div class="card"><h2>API keys</h2>
    <p>Leave a field blank to keep its current value. Saving writes <code>.env</code>,
    restarts the litellm container, and re-runs the Cline/Zed install scripts so
    every configured editor picks up the change automatically.</p>
    <form method="post">{rows}<input type="hidden" name="csrf_token" value="{csrf_token()}">
    <button type="submit">Save &amp; apply everywhere</button></form></div>"""
    return PAGE.format(content=content)


# ───────────────────────── model-selection preference ─────────────────────

def read_preference() -> str:
    if PREF_PATH.exists():
        try:
            return json.loads(PREF_PATH.read_text(encoding="utf-8")).get("mode", "auto")
        except Exception:
            pass
    return "auto"


@app.route("/preference", methods=["GET", "POST"])
def preference():
    if request.method == "POST":
        require_csrf()
        choice = request.form.get("mode", "")
        valid_modes = {mode for mode, _ in sp.MODES.values()}
        if choice not in valid_modes:
            abort(400, "Not a recognized preference mode.")
        PREF_PATH.write_text(json.dumps({"mode": choice}, indent=2), encoding="utf-8")

        if choice == "custom":
            content = (
                "<div class='card'><h2>Saved</h2><p>Preference set to <b>custom</b> -- "
                "refresh_models.py will never auto-apply anything in this mode. "
                "Pick your own model per mode on <a href='/routing'>Custom routing</a>.</p>"
                "<p><a href='/preference'>Back</a></p></div>"
            )
            return PAGE.format(content=content)

        # Every other mode: actually apply it now, right here -- this is the
        # whole point of doing this from the dashboard instead of the CLI
        # script (writes .model_preferences.json AND runs the refresher,
        # non-dry-run, with a container restart, in one click).
        r = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "refresh_models.py"), "--restart"],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180,
        )
        output = (r.stdout or "") + (r.stderr or "")
        content = f"""<div class="card"><h2>Applied: {html.escape(choice)}</h2>
        <pre>{html.escape(output.strip() or '(no output)')}</pre>
        <p><a href="/preference">Back</a> · <a href="/routing">Custom routing</a> · <a href="/">Overview</a></p></div>"""
        return PAGE.format(content=content)

    current = read_preference()
    options = "".join(
        f"""<div class="row"><label style="width:auto;display:flex;gap:8px;align-items:flex-start">
        <input type="radio" name="mode" value="{mode}" {"checked" if mode == current else ""} style="margin-top:3px">
        <span><b>{mode}</b> — {desc}</span></label></div>"""
        for mode, desc in sp.MODES.values()
    )
    content = f"""<div class="card"><h2>Model-selection preference</h2>
    <p>Current: <b>{html.escape(current)}</b>. Choosing anything but "custom" here
    applies immediately -- writes the preference, runs the auto-refresher for
    real (not a dry run), and restarts the container, all in one click. No
    need to run any script yourself. Picking "custom" just saves the choice;
    go to <a href="/routing">Custom routing</a> to hand-pick each mode's model.</p>
    <form method="post">{options}<input type="hidden" name="csrf_token" value="{csrf_token()}">
    <button type="submit">Save &amp; apply</button></form></div>"""
    return PAGE.format(content=content)


# ───────────────────────── custom per-mode routing ─────────────────────────
# Attached to the "custom" preference: hand-pick exactly which model backs
# each mode, instead of letting the auto-refresher choose. Also lets you
# define a brand-new mode/model slot (e.g. for a custom Kilo Code mode you
# named yourself) -- this only wires up the LiteLLM side (a model_name a
# request can address); pointing an actual editor's own custom-mode UI at
# that model_name is still a separate, tool-side step.

PROVIDER_API_KEY_ENV = {
    "openrouter": "OPENROUTER_API_KEY",
    "deepinfra": "DEEPINFRA_API_KEY",
    "fireworks_ai": "FIREWORKS_AI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
}
_FALLBACK_RE = re.compile(r"-fallback-\d+$")
_PREV_RE = re.compile(r"-prev-\d{8}$")


def is_primary_mode(model_name: str) -> bool:
    return not (_FALLBACK_RE.search(model_name) or _PREV_RE.search(model_name))


def load_yaml_roundtrip():
    from ruamel.yaml import YAML
    y = YAML()
    y.preserve_quotes = True
    y.width = 4096  # don't let it wrap long model_list lines
    # Match the indent style config.yaml was originally written in (PyYAML's
    # default: the "-" of a list item sits 2 spaces in, its own content 2
    # more) -- ruamel's own default differs and would otherwise reformat
    # every list item in the file on the first save, drowning the real
    # one-line diff in 70+ lines of pure re-indentation noise.
    y.indent(mapping=2, sequence=4, offset=2)
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return y, y.load(f)


def save_yaml_roundtrip(y, cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        y.dump(cfg, f)


@app.route("/routing", methods=["GET", "POST"])
def routing():
    if request.method == "POST":
        require_csrf()
        y, cfg = load_yaml_roundtrip()
        model_list = cfg["model_list"]
        by_name = {e["model_name"]: e for e in model_list}
        changes = []

        for e in model_list:
            if not is_primary_mode(e["model_name"]):
                continue
            field = f"model__{e['model_name']}"
            new_full = request.form.get(field, "").strip()
            if not new_full or "/" not in new_full:
                continue
            if new_full == e["litellm_params"].get("model"):
                continue
            provider = new_full.split("/", 1)[0]
            e["litellm_params"]["model"] = new_full
            key_env = PROVIDER_API_KEY_ENV.get(provider)
            if key_env:
                e["litellm_params"]["api_key"] = f"os.environ/{key_env}"
            changes.append(f"{e['model_name']} -> {new_full}")

        new_name = request.form.get("new_name", "").strip()
        new_model = request.form.get("new_model", "").strip()
        if new_name and new_model and "/" in new_model:
            if new_name in by_name:
                abort(400, f"'{new_name}' already exists -- edit it above instead of adding it again.")
            provider = new_model.split("/", 1)[0]
            entry = {"model_name": new_name, "litellm_params": {"model": new_model}}
            key_env = PROVIDER_API_KEY_ENV.get(provider)
            if key_env:
                entry["litellm_params"]["api_key"] = f"os.environ/{key_env}"
            model_list.append(entry)
            changes.append(f"added new mode '{new_name}' -> {new_model}")

        if not changes:
            content = "<div class='card'><h2>No changes</h2><p><a href='/routing'>Back</a></p></div>"
            return PAGE.format(content=content)

        save_yaml_roundtrip(y, cfg)
        r = subprocess.run(["docker", "compose", "up", "-d", "--force-recreate", "litellm"],
                            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
        restart_note = "Restarted litellm container." if r.returncode == 0 else f"Container restart FAILED: {r.stderr[-300:]}"
        content = ("<div class='card'><h2>Applied</h2><pre>" + html.escape("\n".join(changes)) +
                   f"</pre><p>{html.escape(restart_note)}</p><p><a href='/routing'>Back</a></p></div>")
        return PAGE.format(content=content)

    _, cfg = load_yaml_roundtrip()
    primaries = [e for e in cfg["model_list"] if is_primary_mode(e["model_name"])]
    rows = "".join(
        f"""<div class="row"><label>{html.escape(e['model_name'])}</label>
        <input type="text" name="model__{html.escape(e['model_name'])}" class="model-picker"
        value="{html.escape(e['litellm_params'].get('model',''))}" style="width:520px"
        list="model-options"></div>"""
        for e in primaries
    )
    content = f"""<div class="card"><h2>Custom routing</h2>
    <p>Every current mode/model slot, editable directly. Start typing in a
    box to search -- suggestions come from <a href="/models">Available
    models</a> (only providers with a key set in <a href="/keys">API
    keys</a> show up). Only takes effect for real once your preference
    (<a href="/preference">here</a>) is set to <b>custom</b> -- otherwise
    the auto-refresher may overwrite these on its next run. Note: this
    only wires up the LiteLLM side; if you're adding a mode for an editor
    like Kilo Code, you still point that editor's own custom-mode setting
    at the model name below, in that editor's own UI.</p>
    <datalist id="model-options"></datalist>
    <form method="post">{rows}
    <div class="row" style="margin-top:16px;border-top:1px solid #30363d;padding-top:12px">
    <label>Add a new mode</label>
    <input type="text" name="new_name" placeholder="mode name, e.g. kilo-execute" style="width:250px">
    <input type="text" name="new_model" placeholder="provider/model-id" style="width:260px" list="model-options">
    </div>
    <input type="hidden" name="csrf_token" value="{csrf_token()}">
    <button type="submit">Save &amp; apply</button></form></div>
    <script>
    (async () => {{
      const r = await fetch('/api/models');
      const models = await r.json();
      const dl = document.getElementById('model-options');
      dl.innerHTML = models.map(m => `<option value="${{m.full_model}}">`).join('');
    }})();
    </script>"""
    return PAGE.format(content=content)


@app.route("/logs")
def logs():
    requested = request.args.get("c", "litellm_proxy")
    # Only ever pass one of the two known, hardcoded container names to
    # `docker logs` and into the HTML -- an unrestricted value here was both
    # a reflected-XSS hole (the raw value was echoed into the page) and a
    # docker-argument-injection hole (it went straight into the argv list).
    which = requested if requested in KNOWN_CONTAINERS else "litellm_proxy"
    # docker logs can emit bytes that aren't valid in the default Windows
    # console codepage (cp1252) -- force UTF-8 with replacement so this
    # never crashes on real log content (confirmed live: it did, on real
    # DeepSeek model output containing non-cp1252 bytes).
    r = subprocess.run(["docker", "logs", which, "--tail", "200"],
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    text = (r.stdout or "") + (r.stderr or "") or "(no output)"
    content = f"""<div class="card"><h2>Logs — {html.escape(which)}</h2>
    <p><a href="/logs?c=litellm_proxy">litellm_proxy</a> · <a href="/logs?c=litellm_db">litellm_db</a></p>
    <pre>{html.escape(text)}</pre></div>"""
    return PAGE.format(content=content)


if __name__ == "__main__":
    print("LiteLLM Workflow Dashboard: http://127.0.0.1:8877")
    app.run(host="127.0.0.1", port=8877, debug=False)
