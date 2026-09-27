#!/usr/bin/env python3
"""
Points Goose (https://github.com/aaif-goose/goose, formerly block/goose) at
this project's LiteLLM proxy and MCP gateway, plus the "power pack"
(desktop control + whole-machine file/terminal access).

What it does (all verified live against a real goose 1.51.0, in a sandboxed
config root, before this was written):
  * writes a custom provider file  <config>/custom_providers/litellm.json
    (engine "openai", models discovered live from the proxy)
  * sets GOOSE_PROVIDER=litellm / GOOSE_MODEL=kilo-code in config.yaml
    (skip with --no-rebind)
  * adds the `litellm-gateway` extension. Goose's native streamable_http
    extension did NOT send an Authorization header in testing (the gateway
    replied "authentication_required"), so this uses the same `mcp-remote`
    stdio bridge Cline/Zed use here.
  * adds the power-pack extensions and turns on Goose's built-in
    `computercontroller` extension (skip with --no-power)

The provider reads its key from the LITELLM_API_KEY environment variable
(set persistently for your user, same as editors/zed/install.py). The MCP
bridge needs the bearer value in the extension's `envs`, so config.yaml does
contain the master key -- same trade-off as Cline's settings file; both live
in your user profile, not this repo.

Edits config.yaml with ruamel.yaml so Goose's own content and comments
survive. Refuses to run while `goose configure` is open (two writers on the
same file would clobber each other) unless you pass --force.

Safe to re-run any time.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_common"))
import common  # noqa: E402

try:
    from ruamel.yaml import YAML
except ImportError:
    print("Missing dependency. Install with:\n  pip install -r dashboard/requirements.txt   (adds ruamel.yaml)",
          file=sys.stderr)
    sys.exit(1)


def find_goose() -> str | None:
    import shutil
    found = shutil.which("goose") or shutil.which("goose.exe")
    if found:
        return found
    cand = Path.home() / ".local" / "bin" / ("goose.exe" if platform.system() == "Windows" else "goose")
    return str(cand) if cand.exists() else None


def config_dir(goose: str | None) -> Path:
    """Ask goose itself where its config lives (honours GOOSE_PATH_ROOT etc.)."""
    if goose:
        r = subprocess.run([goose, "info"], capture_output=True, text=True, encoding="utf-8", errors="replace")
        m = re.search(r"^Config dir:\s*(.+?)\s*(?:missing.*)?$", r.stdout, re.MULTILINE)
        if m:
            return Path(m.group(1).strip())
    if platform.system() == "Windows":
        return Path(os.environ["APPDATA"]) / "Block" / "goose" / "config"
    return Path.home() / ".config" / "goose"


def goose_configure_running() -> bool:
    """True if an interactive `goose configure` is open (Windows check)."""
    if platform.system() != "Windows":
        return False
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process -Filter \"Name='goose.exe'\" | ForEach-Object { $_.CommandLine }"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    return any(re.search(r"goose(\.exe)?\"?\s+configure", line) for line in r.stdout.splitlines())


def write_provider(cfg_dir: Path, models: list[str]) -> Path:
    prov_dir = cfg_dir / "custom_providers"
    prov_dir.mkdir(parents=True, exist_ok=True)
    path = prov_dir / "litellm.json"
    path.write_text(json.dumps({
        "name": "litellm",
        "engine": "openai",
        "display_name": "LiteLLM (local)",
        "description": "Local LiteLLM proxy: cross-provider fallbacks + spend tracking",
        "api_key_env": "LITELLM_API_KEY",
        # Goose wants the FULL chat-completions path here, not just /v1
        "base_url": f"{common.GATEWAY}/v1/chat/completions",
        "models": [{"name": m, "context_limit": 128000} for m in models],
        "supports_streaming": True,
        "requires_auth": True,
    }, indent=2) + "\n", encoding="utf-8")
    return path


def stdio_ext(name: str, cmd: str, args: list[str], description: str, envs: dict | None = None, timeout: int = 300) -> dict:
    return {
        "name": name, "type": "stdio", "cmd": cmd, "args": args, "envs": envs or {},
        "enabled": True, "timeout": timeout, "description": description, "bundled": None,
    }


def merge_config(y: "YAML", path: Path, master_key: str, rebind: bool, power: bool):
    if path.exists():
        original = path.read_text(encoding="utf-8")
        data = y.load(original) or {}
        if "litellm-gateway" not in original:  # first time: keep a copy of the untouched original
            backup = path.with_name(f"{path.name}.bak-{time.strftime('%Y%m%d-%H%M%S')}")
            backup.write_text(original, encoding="utf-8")
            print(f"  backup: {backup}")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {}
    if rebind:
        # 👶 ELI5: Bind Goose to Sektor9 Auto for cost-based routing and 3-tier fallbacks!
        data["GOOSE_PROVIDER"] = "litellm"   # legacy selection, still read by older Goose / fresh configs
        data["GOOSE_MODEL"] = "sektor9-auto"
    # Goose 1.51's `goose configure` writes a NEWER selection scheme
    # (`active_provider` + a `providers:` block) that takes PRECEDENCE over the
    # GOOSE_PROVIDER keys above.
    if "active_provider" in data or "providers" in data:
        providers = data.setdefault("providers", {})
        entry = providers.setdefault("litellm", {})
        entry["enabled"] = True
        entry["configured"] = True
        if rebind or "model" not in entry:
            entry["model"] = "sektor9-auto"
        if rebind:
            prev = data.get("active_provider")
            if prev and prev != "litellm":
                prev_model = (providers.get(prev) or {}).get("model", "?")
                print(f"  active provider: {prev} ({prev_model})  ->  litellm (sektor9-auto)")
            data["active_provider"] = "litellm"
    exts = data.setdefault("extensions", {})
    exts["litellm-gateway"] = stdio_ext(
        "litellm-gateway", "npx",
        ["-y", "mcp-remote", f"{common.GATEWAY}/mcp", "--allow-http", "--header", "Authorization:${LITELLM_AUTH_HEADER}"],
        "LiteLLM MCP gateway: database, browser, SSH, audio/video, 3D and more, behind one endpoint",
        envs={"LITELLM_AUTH_HEADER": f"Bearer {master_key}"},
    )
    if power:
        descriptions = {
            "desktop-commander": "Whole-machine file browsing/search/edit, terminal sessions and process control",
            "windows-mcp": "Windows desktop control: screenshots, clicking, typing, window and app control",
        }
        for name, argv in common.power_pack().items():
            exts[name] = stdio_ext(name, argv[0], argv[1:], descriptions.get(name, name), timeout=300)
        if "computercontroller" in exts:  # Goose's own built-in, shipped disabled
            exts["computercontroller"]["enabled"] = True
    with open(path, "w", encoding="utf-8") as f:
        y.dump(data, f)
    try:
        os.chmod(path, 0o600)  # holds the master key -- owner-only where the OS honors it
    except OSError:
        pass


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--no-rebind", action="store_true", help="Add the provider/extensions but keep your default provider+model.")
    ap.add_argument("--no-power", action="store_true", help="Skip desktop-commander / windows-mcp / computercontroller.")
    ap.add_argument("--skip-env", action="store_true", help="Don't set LITELLM_API_KEY persistently.")
    ap.add_argument("--force", action="store_true", help="Run even if `goose configure` is open.")
    args = ap.parse_args()

    if goose_configure_running() and not args.force:
        print("`goose configure` is open in another terminal. Finish or exit it first (it rewrites config.yaml "
              "when it finishes and would undo this), then re-run. Use --force to override.", file=sys.stderr)
        sys.exit(1)

    master_key = common.require_master_key()
    models = common.litellm_models(master_key)
    goose = find_goose()
    cfg_dir = config_dir(goose)
    print(f"Goose config dir: {cfg_dir}")

    print(f"Wrote provider: {write_provider(cfg_dir, models)}")
    y = YAML()
    y.preserve_quotes = True
    y.indent(mapping=2, sequence=4, offset=2)
    merge_config(y, cfg_dir / "config.yaml", master_key, rebind=not args.no_rebind, power=not args.no_power)
    print(f"Updated: {cfg_dir / 'config.yaml'}")

    if not args.skip_env:
        common.set_persistent_env_var("LITELLM_API_KEY", master_key)
    print("\nVerify: goose doctor   |   goose run --no-session -t \"say pong\"")
    print("Goose Desktop: restart it so it re-reads the environment and config.")


if __name__ == "__main__":
    main()
