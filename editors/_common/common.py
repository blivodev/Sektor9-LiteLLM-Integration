"""
Shared helpers for the editor installers (opencode, openwork, goose, ...).
Import with:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_common"))
    import common

Older installers (cline, zed, hermes, copilot, tabby) predate this module and
stay standalone on purpose; nothing here is required by them.
"""
from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
GATEWAY = "http://127.0.0.1:4000"  # 127.0.0.1 not localhost: see docs/STATUS.md (IPv6 dead end)

# 👶 ELI5: Used if the LiteLLM proxy is offline while installing an editor.
# We include Sektor9 Auto first, followed by all specialized agent modes.
DEFAULT_MODELS = [
    "sektor9-auto",
    "sektor9-autorouter",
    "sektor9-code",
    "sektor9-ask",
    "sektor9-debug",
    "sektor9-plan",
    "sektor9-orchestrator",
    "sektor9-review",
    "sektor9-refactor",
    "sektor9-test",
    "sektor9-docs",
    "sektor9-sql",
    "sektor9-devops",
    "sektor9-creative",
    "claude",
    "gemini",
    # Backward compatibility aliases
    "kilo-code",
    "kilo-ask",
    "kilo-debug",
    "kilo-plan",
    "kilo-orchestrator",
]


def load_env() -> dict:
    env = {}
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def require_master_key() -> str:
    key = load_env().get("LITELLM_MASTER_KEY")
    if not key:
        print("LITELLM_MASTER_KEY not found in .env -- set that up first.", file=sys.stderr)
        sys.exit(1)
    return key


def litellm_models(master_key: str) -> list[str]:
    """Primary model names live from the proxy (so modes added on the
    dashboard's Custom Routing page show up too); skips the -fallback-N and
    -prev-DATE bookkeeping entries. Falls back to DEFAULT_MODELS."""
    try:
        req = urllib.request.Request(f"{GATEWAY}/v1/models", headers={"Authorization": f"Bearer {master_key}"})
        with urllib.request.urlopen(req, timeout=8) as r:
            ids = [m["id"] for m in json.load(r)["data"]]
        primaries = [m for m in ids if "-fallback-" not in m and "-prev-" not in m]
        if primaries:
            return sorted(primaries, key=lambda m: (DEFAULT_MODELS.index(m) if m in DEFAULT_MODELS else 99, m))
    except Exception as e:  # proxy down / key wrong -> still produce a usable config
        print(f"[warn] couldn't list models from {GATEWAY} ({e}); using the default set.", file=sys.stderr)
    return list(DEFAULT_MODELS)


def set_persistent_env_var(name: str, value: str):
    if platform.system() == "Windows":
        subprocess.run(["setx", name, value], capture_output=True, text=True)
        print(f"Set {name} as a persistent user environment variable (new terminals/apps pick it up).")
    else:
        rc = Path.home() / (".zshrc" if os.environ.get("SHELL", "").endswith("zsh") else ".bashrc")
        line = f'export {name}="{value}"'
        if not rc.exists() or line not in rc.read_text(encoding="utf-8"):
            with open(rc, "a", encoding="utf-8") as f:
                f.write(f"\n{line}\n")
        print(f"Added `export {name}=...` to {rc}. Restart your terminal to pick it up.")


# ───────────────────────── the "power pack" ───────────────────────────────
# Local (stdio) MCP servers that bring an editor closer to Claude Desktop /
# Claude Code: whole-machine file browsing + terminal + process control, and
# real desktop (GUI) control. Both were live-tested under OpenCode this
# session (connected, tools listed) before being wired anywhere.
#
# Deliberately LOCAL per-editor stdio servers, NOT registered in the LiteLLM
# gateway: the gateway runs in a container with no view of your desktop, and
# exposing desktop control over a network port (host.docker.internal is your
# LAN IP on this machine) would be an unauthenticated remote-control hole.
# windows-mcp itself refuses non-loopback binding without auth for the same
# reason. Remote/SSH control and the browser (Playwright) already come
# through the gateway for every editor.

def power_pack() -> dict[str, list[str]]:
    pack = {
        # file system browsing/search/edit anywhere on the machine, terminal
        # sessions, process management (the gateway's filesystem server only
        # sees the mounted /workspace)
        "desktop-commander": ["npx", "-y", "@wonderwhy-er/desktop-commander@latest"],
    }
    if platform.system() == "Windows":
        # screenshots, clicking/typing, window + app control. `serve` is
        # required (bare `windows-mcp` prints help and exits, which shows
        # up as "Connection closed" in an editor).
        pack["windows-mcp"] = ["uvx", "windows-mcp", "serve", "--transport", "stdio"]
    return pack
