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
    -> http://localhost:8877
"""
from __future__ import annotations

import html
import os
import secrets
import subprocess
import sys
from pathlib import Path

from flask import Flask, abort, request, session

try:
    import requests
except ImportError:
    print("pip install requests flask", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
LITELLM_URL = "http://localhost:4000"

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
    origin = request.headers.get("Origin") or request.headers.get("Referer") or ""
    if origin and not (origin.startswith("http://localhost:8877") or origin.startswith("http://127.0.0.1:8877")):
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
<a href="/">Overview</a><a href="/balances">Balances</a><a href="/keys">API Keys</a><a href="/mcp">MCP Servers</a><a href="/logs">Logs</a>
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
    <p><a href="http://localhost:4000/ui" target="_blank">Open LiteLLM Admin UI →</a></p></div>
    <div class="card"><h2>Quick links</h2>
    <p><a href="/balances">Provider balances</a> · <a href="/mcp">MCP server health</a> ·
    <a href="/keys">Configure API keys</a> · <a href="/logs">View logs</a></p></div>
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
    print("LiteLLM Workflow Dashboard: http://localhost:8877")
    app.run(host="127.0.0.1", port=8877, debug=False)
