#!/usr/bin/env python3
"""
Points OpenCode (https://opencode.ai) at this project's LiteLLM proxy and
MCP gateway, and adds the "power pack" (desktop control + whole-machine
file/terminal access) that brings it closer to Claude Desktop/Code.

What it does to OpenCode's real global config (~/.config/opencode/
opencode.jsonc -- the same path on Windows, confirmed live):
  * adds a `litellm` provider (OpenAI-compatible, models discovered live
    from the proxy so any mode you add on the dashboard shows up too)
  * adds the `litellm-gateway` remote MCP server
  * adds the power pack as local MCP servers (see _common/common.py);
    skip with --no-power
  * re-binds `model`, `small_model` and the build/plan/general/explore
    agents to LiteLLM model names, so they get cross-provider fallbacks and
    spend tracking instead of hitting one provider directly. Pass
    --no-rebind to skip this and only ADD things.

The master key is never written into the config: both the provider and the
MCP header use OpenCode's `{env:LITELLM_API_KEY}` substitution (confirmed
live), and the variable is set persistently for your user the same way
editors/zed/install.py does it.

Your existing config is backed up first, and anything this changes is
recorded in a comment at the top of the new file so nothing is lost.
(JSONC comments inside the old file can't survive a parse/rewrite; the
backup keeps them.)

Also used by editors/openwork/install.py (OpenWork embeds OpenCode).
Safe to re-run any time.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_common"))
import common  # noqa: E402

# OpenCode agent -> LiteLLM model, mirroring the Kilo Code mapping in
# docs/ARCHITECTURE.md (cheap tier for exploration/general, planner for plan).
AGENT_BINDINGS = {
    "build": "kilo-code",
    "plan": "kilo-plan",
    "general": "kilo-ask",
    "explore": "kilo-ask",
}


# ───────────────────────── JSONC (string-aware) ───────────────────────────

def strip_jsonc(text: str) -> str:
    """Remove // and /* */ comments and trailing commas without touching
    string contents (a naive regex breaks on "https://..." values)."""
    out, i, n = [], 0, len(text)
    in_str = False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            out.append(c)
            i += 1
        elif c == "/" and text[i:i + 2] == "//":
            while i < n and text[i] != "\n":
                i += 1
        elif c == "/" and text[i:i + 2] == "/*":
            end = text.find("*/", i + 2)
            i = n if end == -1 else end + 2
        else:
            out.append(c)
            i += 1
    cleaned = "".join(out)
    res, in_str, i = [], False, 0  # trailing commas before } or ]
    while i < len(cleaned):
        c = cleaned[i]
        if in_str:
            res.append(c)
            if c == "\\" and i + 1 < len(cleaned):
                res.append(cleaned[i + 1])
                i += 2
                continue
            if c == '"':
                in_str = False
        elif c == '"':
            in_str = True
            res.append(c)
        elif c == ",":
            j = i + 1
            while j < len(cleaned) and cleaned[j] in " \t\r\n":
                j += 1
            if j < len(cleaned) and cleaned[j] in "}]":
                i += 1
                continue
            res.append(c)
        else:
            res.append(c)
        i += 1
    return "".join(res)


def parse_jsonc(text: str) -> dict:
    stripped = strip_jsonc(text).strip()
    return json.loads(stripped) if stripped else {}


# ───────────────────────── config merge ───────────────────────────────────

def build_provider(models: list[str]) -> dict:
    return {
        "npm": "@ai-sdk/openai-compatible",
        "name": "LiteLLM",
        "options": {"baseURL": f"{common.GATEWAY}/v1", "apiKey": "{env:LITELLM_API_KEY}"},
        "models": {m: {"name": m} for m in models},
    }


def build_gateway_mcp() -> dict:
    return {
        "type": "remote",
        "url": f"{common.GATEWAY}/mcp",
        "headers": {"Authorization": "Bearer {env:LITELLM_API_KEY}"},
        "enabled": True,
        "timeout": 60000,  # the gateway starts 16 MCP servers; first tool listing can be slow
    }


def build_local_mcp(argv: list[str]) -> dict:
    return {"type": "local", "command": argv, "enabled": True, "timeout": 180000}  # first run downloads packages


def merge_config(cfg: dict, models: list[str], rebind: bool, agents: bool, power: bool) -> list[str]:
    """Mutates cfg; returns human-readable notes about anything REPLACED."""
    notes = []
    cfg.setdefault("provider", {})["litellm"] = build_provider(models)
    mcp = cfg.setdefault("mcp", {})
    mcp["litellm-gateway"] = build_gateway_mcp()
    if power:
        for name, argv in common.power_pack().items():
            mcp[name] = build_local_mcp(argv)
    if not rebind:
        return notes

    def set_val(container: dict, key: str, value: str, label: str):
        old = container.get(key)
        if old and old != value:
            notes.append(f"{label}: {old}  ->  {value}")
        container[key] = value

    set_val(cfg, "model", "litellm/kilo-code", "model")
    set_val(cfg, "small_model", "litellm/kilo-ask", "small_model")
    if agents:
        agent_cfg = cfg.setdefault("agent", {})
        for agent, model in AGENT_BINDINGS.items():
            entry = agent_cfg.setdefault(agent, {})
            set_val(entry, "model", f"litellm/{model}", f"agent.{agent}.model")
    return notes


def write_config(path: Path, cfg: dict, notes: list[str]):
    header = ["// Managed in part by editors/opencode/install.py in the litellm-setup repo:",
              "// the `litellm` provider, `litellm-gateway` MCP server and the local power-pack",
              "// servers below are (re)written by it. Re-running the installer is safe.",
              "// Keys are never stored here -- {env:LITELLM_API_KEY} is read from your environment."]
    if notes:
        header.append("// Values this replaced (kept here so nothing is lost; your full previous file,")
        header.append("// comments included, is in the .bak-* file next to this one):")
        header += [f"//   {n}" for n in notes]
    path.write_text("\n".join(header) + "\n" + json.dumps(cfg, indent=2) + "\n", encoding="utf-8")


MARKER = "Managed in part by editors/opencode/install.py"


def previous_notes(original: str) -> list[str]:
    """'Values this replaced' lines from an earlier run's header, so a re-run
    doesn't erase that record."""
    return [ln[5:] for ln in original.splitlines() if ln.startswith("//   ")]


def apply_to_file(path: Path, models: list[str], rebind: bool, agents: bool, power: bool) -> list[str]:
    carried: list[str] = []
    if path.exists():
        original = path.read_text(encoding="utf-8")
        cfg = parse_jsonc(original)
        if MARKER in original:
            # Already ours: the first-ever backup holds the true original, and
            # backing up our own output on every re-run would just be clutter.
            carried = previous_notes(original)
        else:
            backup = path.with_name(f"{path.name}.bak-{time.strftime('%Y%m%d-%H%M%S')}")
            backup.write_text(original, encoding="utf-8")
            print(f"  backup: {backup}")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        cfg = {"$schema": "https://opencode.ai/config.json"}
    cfg.setdefault("$schema", "https://opencode.ai/config.json")
    notes = merge_config(cfg, models, rebind, agents, power)
    write_config(path, cfg, carried + [n for n in notes if n not in carried])
    return notes


def global_config_path() -> Path:
    base = Path.home() / ".config" / "opencode"
    for name in ("opencode.jsonc", "opencode.json"):
        if (base / name).exists():
            return base / name
    return base / "opencode.jsonc"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--no-rebind", action="store_true",
                    help="Only add things; leave your model/agent choices alone.")
    ap.add_argument("--no-power", action="store_true",
                    help="Skip the desktop-commander / windows-mcp power pack.")
    ap.add_argument("--workspace", action="append", default=[], metavar="DIR",
                    help="Also apply (provider + MCP + default model) to DIR/opencode.jsonc. Repeatable.")
    ap.add_argument("--skip-global", action="store_true", help="Don't touch ~/.config/opencode.")
    ap.add_argument("--skip-env", action="store_true", help="Don't set LITELLM_API_KEY persistently.")
    args = ap.parse_args()

    master_key = common.require_master_key()
    models = common.litellm_models(master_key)
    print(f"Models exposed to OpenCode: {', '.join(models)}")
    power = not args.no_power

    if not args.skip_global:
        path = global_config_path()
        print(f"Global config: {path}")
        for n in apply_to_file(path, models, rebind=not args.no_rebind, agents=True, power=power):
            print(f"  replaced {n}")
    for ws in args.workspace:
        p = Path(ws).expanduser() / "opencode.jsonc"
        print(f"Workspace config: {p}")
        apply_to_file(p, models, rebind=not args.no_rebind, agents=False, power=power)

    if not args.skip_env:
        common.set_persistent_env_var("LITELLM_API_KEY", master_key)
    print("\nVerify: opencode mcp list   |   opencode run -m litellm/kilo-code \"say pong\"")
    print("(Open a NEW terminal first if this is the first time LITELLM_API_KEY was set.)")


if __name__ == "__main__":
    main()
