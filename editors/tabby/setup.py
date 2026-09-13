#!/usr/bin/env python3
"""
Prepares editors/tabby/data/config.toml (Tabby's model config, HTTP-only --
no local model download) from config.toml.template, with the LiteLLM master
key filled in. Doesn't start anything -- see README.md for the docker
compose command once this has run.

Safe to re-run any time (e.g. after rotating the master key); overwrites
only the generated config.toml, never anything else you've put in data/.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent


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


def main():
    env = load_env()
    master_key = env.get("LITELLM_MASTER_KEY")
    if not master_key:
        print("LITELLM_MASTER_KEY not found in .env -- set that up first.", file=sys.stderr)
        sys.exit(1)

    template = (HERE / "config.toml.template").read_text(encoding="utf-8")
    rendered = template.replace("{{LITELLM_MASTER_KEY}}", master_key)

    data_dir = HERE / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    out_path = data_dir / "config.toml"
    out_path.write_text(rendered, encoding="utf-8")
    try:
        import os
        os.chmod(out_path, 0o600)  # this file now contains your master key -- owner-only where the OS honors it
    except OSError:
        pass

    print(f"Wrote {out_path}")
    print(
        "\nNext:\n"
        "  docker compose -f editors/tabby/docker-compose.yml up -d\n"
        "  -> http://127.0.0.1:8080 once it's up (first pull is a large image, give it a few minutes)\n"
        "Read the completion-model caveat at the bottom of config.toml.template before "
        "expecting Copilot-quality inline completions -- chat works well as-is."
    )


if __name__ == "__main__":
    main()
