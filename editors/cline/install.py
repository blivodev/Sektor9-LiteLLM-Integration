#!/usr/bin/env python3
"""
Merges the LiteLLM MCP gateway into Cline's real MCP config, WITHOUT
touching any other server you've already got configured there. Safe to
re-run any time (e.g. after rotating your master key).

Cline's provider (base URL + API key) still needs a one-time manual step
in its Settings UI -- that part isn't in a plain file Cline reads, so
there's nothing safe to script. See README.md in this folder for the
exact values to enter.
"""
import json
import os
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


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


def cline_settings_path() -> Path:
    system = platform.system()
    if system == "Windows":
        base = Path(os.environ["APPDATA"]) / "Code" / "User" / "globalStorage" / "saoudrizwan.claude-dev" / "settings"
    elif system == "Darwin":
        base = Path.home() / "Library" / "Application Support" / "Code" / "User" / "globalStorage" / "saoudrizwan.claude-dev" / "settings"
    else:
        base = Path.home() / ".config" / "Code" / "User" / "globalStorage" / "saoudrizwan.claude-dev" / "settings"
    return base / "cline_mcp_settings.json"


def main():
    env = load_env()
    master_key = env.get("LITELLM_MASTER_KEY")
    if not master_key:
        print("LITELLM_MASTER_KEY not found in .env - set that up first.", file=sys.stderr)
        sys.exit(1)

    path = cline_settings_path()
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {"mcpServers": {}}
    data.setdefault("mcpServers", {})

    data["mcpServers"]["litellm-gateway"] = {
        "command": "npx",
        "args": [
            "-y", "mcp-remote", "http://127.0.0.1:4000/mcp",
            "--allow-http", "--header", "Authorization:${LITELLM_AUTH_HEADER}",
        ],
        "env": {"LITELLM_AUTH_HEADER": f"Bearer {master_key}"},
        "disabled": False,
        "autoApprove": [],
    }

    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        os.chmod(path, 0o600)  # this file now contains your master key -- owner-only where the OS honors it
    except OSError:
        pass
    print(f"Merged litellm-gateway into {path}")
    print("Existing MCP servers you already had configured were left untouched.")
    print("\nOne manual step left - see README.md for Cline's provider setup (Settings UI).")


if __name__ == "__main__":
    main()
