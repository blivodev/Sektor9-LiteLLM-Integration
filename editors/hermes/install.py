#!/usr/bin/env python3
"""
Wires Hermes Agent (https://hermes-agent.nousresearch.com/) to this
project's LiteLLM proxy, using Hermes's own `hermes config set` /
`hermes mcp` CLI -- NOT by hand-editing its config file directly.

Why: Hermes's real config.yaml is a large (100KB+), heavily-commented
reference file, and a first version of this script tried to merge into
it directly (and initially even guessed the wrong path entirely --
~/.hermes/ is Unix-only; Windows really uses %LOCALAPPDATA%\\hermes\\).
`hermes config set <key> <value>` is Hermes's own supported way to
change one setting without touching anything else in that file, confirmed
correct this session via `hermes config get` after each set, and the
whole flow verified with a real, live chat round-trip (see README.md).

Safe to re-run any time (e.g. after rotating the master key) -- every
`config set` call here is idempotent (re-setting the same key to the
same value is a no-op in effect).
"""
import argparse
import platform
import shutil
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


def find_hermes() -> str | None:
    found = shutil.which("hermes") or shutil.which("hermes.exe")
    if found:
        return found
    # Known default install location when it isn't on PATH (confirmed on
    # this Windows machine -- adjust here if your install differs).
    if platform.system() == "Windows":
        candidate = Path.home() / "AppData" / "Local" / "hermes" / "bin" / "hermes.exe"
        if candidate.exists():
            return str(candidate)
    return None


def run(hermes: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([hermes, *args], capture_output=True, text=True, encoding="utf-8", errors="replace")


def safe_print(text: str):
    # hermes.exe's own output uses UTF-8 symbols (checkmarks etc.) that
    # Windows' default console codepage (cp1252) can't encode back out --
    # same class of bug documented elsewhere in this project. Fall back to
    # ASCII-safe substitution rather than crashing on a cosmetic checkmark.
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", errors="replace").decode("ascii"))


def config_env_path(hermes: str) -> Path:
    r = run(hermes, "config", "env-path")
    return Path(r.stdout.strip())


def merge_dotenv(env_path: Path, master_key: str):
    lines = []
    seen = False
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("LITELLM_API_KEY="):
                lines.append(f"LITELLM_API_KEY={master_key}")
                seen = True
            else:
                lines.append(line)
    if not seen:
        lines.append(f"LITELLM_API_KEY={master_key}")
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        import os
        os.chmod(env_path, 0o600)  # this file now holds your master key -- owner-only where the OS honors it
    except OSError:
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-rebind", action="store_true",
                    help="Refresh the provider/MCP/key only; leave model.default/provider as you set them.")
    args = ap.parse_args()

    env = load_env()
    master_key = env.get("LITELLM_MASTER_KEY")
    if not master_key:
        print("LITELLM_MASTER_KEY not found in .env -- set that up first.", file=sys.stderr)
        sys.exit(1)

    hermes = find_hermes()
    if not hermes:
        print(
            "Couldn't find the hermes executable on PATH or in the default install "
            "location. Install Hermes Agent first: https://hermes-agent.nousresearch.com/",
            file=sys.stderr,
        )
        sys.exit(1)

    settings = [
        ("providers.litellm.api", "http://127.0.0.1:4000/v1"),
        ("providers.litellm.key_env", "LITELLM_API_KEY"),
        ("model.default", "sektor9-autorouter"),
        ("model.provider", "custom:litellm"),
        ("mcp_servers.litellm-gateway.url", "http://127.0.0.1:4000/mcp"),
        ("mcp_servers.litellm-gateway.headers.Authorization", f"Bearer {master_key}"),
    ]
    if args.no_rebind:
        settings = [s for s in settings if s[0] not in ("model.default", "model.provider")]
    for key, value in settings:
        r = run(hermes, "config", "set", key, value)
        if r.returncode != 0:
            print(f"[warn] `hermes config set {key} ...` failed: {r.stderr.strip()}", file=sys.stderr)
        else:
            safe_print(r.stdout.strip())

    # A leftover model.base_url from Hermes's own default provider setup
    # (e.g. if you'd already run `hermes model` and picked OpenRouter)
    # would otherwise shadow providers.litellm.api. Harmless to unset even
    # if it was never set.
    if not args.no_rebind:
        run(hermes, "config", "unset", "model.base_url")

    env_path = config_env_path(hermes)
    merge_dotenv(env_path, master_key)
    print(f"Wrote LITELLM_API_KEY into {env_path}")

    print(
        "\nVerify any time with:\n"
        "  hermes doctor\n"
        "  hermes mcp test litellm-gateway\n"
        "  hermes -z \"say pong\" --provider litellm -m sektor9-autorouter\n"
        "Switch models live with `hermes model` (sektor9-code, kilo-ask, kilo-debug, kilo-plan, "
        "kilo-orchestrator, claude, gemini are all available the same way)."
    )


if __name__ == "__main__":
    main()
