# Zed

[Zed](https://zed.dev) — open source (Apache/GPL), Rust-based, hit 1.0
stable in April 2026 and is under active development (v1.19 by September
2026), native Windows/Mac/Linux. A genuinely different codebase from
VS Code, not a fork.

## Install

```powershell
winget install -e --id ZedIndustries.Zed
```

## Setup (scripted, live-tested)

```bash
python editors/zed/install.py
```

This merges [`settings.json.template`](settings.json.template)'s
`language_models.openai_compatible.litellm` (all 7 LiteLLM models) and
`context_servers.litellm-gateway` (the whole MCP gateway, via the same
`mcp-remote` bridge used for Cline) into Zed's real settings — confirmed
live: launched Zed with this exact config and verified no settings-load
error in `%LOCALAPPDATA%\Zed\logs\Zed.log` (one real bug was caught and
fixed this way: Zed's schema requires a `capabilities.images` field on
every model or it silently fails to load the *entire* settings file).

Zed reads API keys from environment variables only, never from
settings.json — the script also sets `LITELLM_API_KEY` (the naming
convention Zed derives from the provider id `litellm`) as a persistent
env var. **Fully quit and restart Zed** afterward — a plain window reload
won't pick up a new env var.

## Known limitation

Zed's `context_servers` only supports `"source": "custom"` (a local stdio
command) — no native remote/URL MCP type, so the `mcp-remote` bridge is
necessary here too, same as Cline.
