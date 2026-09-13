#!/usr/bin/env python3
"""
Sets up GitHub Copilot Chat (in VS Code) to route its model requests through
the LiteLLM proxy, via the open-source `vivswan.litellm-vscode-chat` bridge
extension -- and wires the LiteLLM MCP gateway into VS Code's own native MCP
client (the same one Copilot Chat's agent mode uses).

Requires an active, signed-in GitHub Copilot subscription -- this is NOT a
free replacement for Kilo Code, just an alternative front-end that can point
its model requests at your existing LiteLLM setup instead of GitHub's own
backend. See README.md in this folder for what that extension can and can't
do, and why the MCP gateway step still needs one manual prompt the first
time (a deliberate VS Code security choice, not something worth working
around by hardcoding your master key into a file this project might commit).
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


def vscode_user_settings_path() -> Path:
    system = platform.system()
    if system == "Windows":
        return Path(os.environ["APPDATA"]) / "Code" / "User" / "settings.json"
    elif system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "Code" / "User" / "settings.json"
    else:
        return Path.home() / ".config" / "Code" / "User" / "settings.json"


LABEL = "LiteLLM (local)"


def merge_chat_provider(master_key: str) -> Path:
    """litellm-vscode-chat reads its server list from this VS Code setting --
    same shape as its own "Manage Models..." UI would write."""
    path = vscode_user_settings_path()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"{path} isn't valid JSON -- leaving it untouched. Add the server by hand via "
                  "the chat model picker's \"Manage Models...\" instead.")
            return path
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {}

    servers = data.setdefault("litellm-vscode-chat.servers", [])
    servers[:] = [s for s in servers if s.get("label") != LABEL]  # idempotent re-run
    servers.append({
        "label": LABEL,
        "baseUrl": "http://127.0.0.1:4000",
        "auth": {"apiKey": master_key},
    })

    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        os.chmod(path, 0o600)  # this file now contains your master key -- owner-only where the OS honors it
    except OSError:
        pass
    return path


def merge_workspace_mcp() -> Path:
    """Workspace-level .vscode/mcp.json -- VS Code's own native MCP client,
    which Copilot Chat's agent mode reads directly. Uses an `inputs` prompt
    instead of hardcoding the master key, since this file lives inside the
    project and could end up committed -- VS Code stores what you type into
    that prompt in its own secret storage after the first time, not in this
    file."""
    path = ROOT / ".vscode" / "mcp.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"{path} isn't valid JSON -- leaving it untouched. Merge the block from "
                  "README.md in by hand instead.")
            return path
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {}

    inputs = data.setdefault("inputs", [])
    if not any(i.get("id") == "litellm-master-key" for i in inputs):
        inputs.append({
            "type": "promptString",
            "id": "litellm-master-key",
            "description": "LiteLLM master key (from .env's LITELLM_MASTER_KEY)",
            "password": True,
        })

    data.setdefault("servers", {})["litellm-gateway"] = {
        "type": "http",
        "url": "http://127.0.0.1:4000/mcp",
        "headers": {"Authorization": "Bearer ${input:litellm-master-key}"},
    }

    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def main():
    env = load_env()
    master_key = env.get("LITELLM_MASTER_KEY")
    if not master_key:
        print("LITELLM_MASTER_KEY not found in .env -- set that up first.", file=sys.stderr)
        sys.exit(1)

    settings_path = merge_chat_provider(master_key)
    print(f"Merged chat model provider '{LABEL}' into {settings_path}")

    mcp_path = merge_workspace_mcp()
    print(f"Merged litellm-gateway MCP server into {mcp_path}")

    print(
        "\nTwo things left, both one-time and both in VS Code itself:\n"
        "  1. Install the extensions if you haven't: GitHub.copilot-chat "
        "(needs an active Copilot subscription, signed in) and "
        "vivswan.litellm-vscode-chat.\n"
        "  2. Open the chat model picker -> the models above should already "
        "show up under 'LiteLLM (local)'. If the MCP server prompts you for "
        "the master key the first time it connects, that's expected -- "
        "paste it from .env's LITELLM_MASTER_KEY.\n"
        "See README.md in this folder for the full picture, including what "
        "this bridge extension can't do."
    )


if __name__ == "__main__":
    main()
