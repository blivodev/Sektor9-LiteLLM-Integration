#!/usr/bin/env python3
"""
Points OpenWork (https://openworklabs.com, github.com/different-ai/openwork
-- the open-source Claude Cowork alternative) at this project's LiteLLM proxy
and MCP gateway, plus the desktop-control/file-system "power pack".

How OpenWork works (confirmed against this machine's real install, not
assumed): it's a desktop app that embeds an OpenCode engine per workspace.
It layers its own generated runtime config, then each workspace's
`opencode.jsonc`. So the right place to configure it is the WORKSPACE file
(its documented mechanism) -- this script writes the LiteLLM provider, the
gateway + power-pack MCP servers and a default model into every OpenWork
workspace it can find. Verified live: with the global OpenCode config hidden
and OpenWork's real runtime config layered in, a workspace file written by
this script alone gave OpenCode the provider, all three MCP servers and a
working `openwork` agent chat on kilo-code.

It does NOT rebind agents (OpenWork ships its own `openwork` agent) and does
NOT touch ~/.config/opencode -- run editors/opencode/install.py for that.

Workspaces are auto-detected from OpenWork's server state on Windows; pass
--workspace DIR (repeatable) for others or on other platforms.

Restart the workspace (or the app) afterwards: OpenWork's engine reads the
file at start.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "_common"))
import common  # noqa: E402


def load_opencode_installer():
    spec = importlib.util.spec_from_file_location("opencode_install", HERE.parent / "opencode" / "install.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def detect_workspaces() -> list[Path]:
    if platform.system() != "Windows":
        return []
    state = Path(os.environ.get("APPDATA", "")) / "com.differentai.openwork" / "openwork-server-state.json"
    if not state.exists():
        return []
    try:
        ports = json.loads(state.read_text(encoding="utf-8")).get("workspacePorts", {})
    except (OSError, json.JSONDecodeError):
        return []
    found = []
    for raw in ports:  # keys are lower-cased paths like "c:/Users/USER/openwork chat"
        p = Path(raw)
        if p.is_dir():
            found.append(p)
    return found


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--workspace", action="append", default=[], metavar="DIR",
                    help="Extra OpenWork workspace folder(s) to configure (repeatable).")
    ap.add_argument("--no-rebind", action="store_true",
                    help="Refresh provider/MCP only; leave each workspace's default model as you set it.")
    ap.add_argument("--no-power", action="store_true", help="Skip the desktop-commander / windows-mcp power pack.")
    ap.add_argument("--skip-env", action="store_true", help="Don't set LITELLM_API_KEY persistently.")
    args = ap.parse_args()

    oc = load_opencode_installer()
    master_key = common.require_master_key()
    models = common.litellm_models(master_key)

    workspaces = detect_workspaces() + [Path(w).expanduser() for w in args.workspace]
    seen, unique = set(), []
    for w in workspaces:
        key = str(w.resolve()).lower()
        if key not in seen:
            seen.add(key)
            unique.append(w)
    if not unique:
        print("No OpenWork workspaces found. Open OpenWork once (or pass --workspace DIR), then re-run.", file=sys.stderr)
        sys.exit(1)

    for ws in unique:
        path = ws / "opencode.jsonc"
        print(f"OpenWork workspace: {path}")
        # rebind=True here only sets the default model/small_model (agents=False keeps
        # OpenWork's own `openwork` agent untouched).
        oc.apply_to_file(path, models, rebind=not args.no_rebind, agents=False, power=not args.no_power)

    if not args.skip_env:
        common.set_persistent_env_var("LITELLM_API_KEY", master_key)
    print("\nRestart the workspace (or OpenWork) to pick this up. The app must be started AFTER "
          "LITELLM_API_KEY exists in your environment (open a fresh terminal/log in again if it was just set).")


if __name__ == "__main__":
    main()
