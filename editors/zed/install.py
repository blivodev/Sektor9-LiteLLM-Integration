#!/usr/bin/env python3
"""
Sets up Zed to use the LiteLLM proxy: merges language_models/context_servers
into Zed's real settings.json (without touching anything else already in
there), and sets the LITELLM_API_KEY environment variable Zed reads its key
from (Zed does NOT read API keys from settings.json on purpose -- see
editors/zed/README.md).
"""
import json
import os
import platform
import subprocess
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


def zed_settings_path() -> Path:
    system = platform.system()
    if system == "Windows":
        return Path(os.environ["APPDATA"]) / "Zed" / "settings.json"
    elif system == "Darwin":
        return Path.home() / ".config" / "zed" / "settings.json"
    else:
        return Path.home() / ".config" / "zed" / "settings.json"


def set_persistent_env_var(name: str, value: str):
    system = platform.system()
    if system == "Windows":
        subprocess.run(["setx", name, value], capture_output=True, text=True)
        print(f"Set {name} as a persistent Windows user environment variable (new terminals/apps will see it).")
    else:
        rc_file = Path.home() / (".zshrc" if os.environ.get("SHELL", "").endswith("zsh") else ".bashrc")
        line = f'\nexport {name}="{value}"\n'
        if not rc_file.exists() or line.strip() not in rc_file.read_text(encoding="utf-8"):
            with open(rc_file, "a", encoding="utf-8") as f:
                f.write(line)
        print(f"Added `export {name}=...` to {rc_file}. Restart your terminal (and Zed) to pick it up.")


def main():
    env = load_env()
    master_key = env.get("LITELLM_MASTER_KEY")
    if not master_key:
        print("LITELLM_MASTER_KEY not found in .env -- set that up first.", file=sys.stderr)
        sys.exit(1)

    template = json.loads((Path(__file__).parent / "settings.json.template").read_text(encoding="utf-8"))

    path = zed_settings_path()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"{path} isn't valid JSON -- leaving it untouched. Merge settings.json.template in by hand.")
            return
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {}

    data.setdefault("language_models", {}).setdefault("openai_compatible", {})["litellm"] = (
        template["language_models"]["openai_compatible"]["litellm"]
    )
    data.setdefault("context_servers", {})["litellm-gateway"] = template["context_servers"]["litellm-gateway"]
    data["context_servers"]["litellm-gateway"]["env"]["LITELLM_AUTH_HEADER"] = f"Bearer {master_key}"

    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        os.chmod(path, 0o600)  # this file now contains your master key -- owner-only where the OS honors it
    except OSError:
        pass
    print(f"Merged LiteLLM provider + MCP gateway into {path}")

    set_persistent_env_var("LITELLM_API_KEY", master_key)
    print("\nRestart Zed (fully quit, not just close the window) for the new API key env var to take effect.")


if __name__ == "__main__":
    main()
