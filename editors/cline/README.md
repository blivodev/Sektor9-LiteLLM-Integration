# Cline (VS Code)

[Cline](https://github.com/cline/cline) — open source, actively maintained,
supports 30+ providers including a generic "OpenAI Compatible" one, plus
native MCP support. Extension ID: `saoudrizwan.claude-dev`.

## Install

```bash
code --install-extension saoudrizwan.claude-dev
```

## 1. MCP gateway (scripted)

```bash
python editors/cline/install.py
```

This merges a `litellm-gateway` entry into Cline's real MCP config
(`%APPDATA%\Code\User\globalStorage\saoudrizwan.claude-dev\settings\cline_mcp_settings.json`
on Windows) using [`mcp-remote`](https://www.npmjs.com/package/mcp-remote)
to bridge Cline's stdio-based MCP client to LiteLLM's HTTP gateway —
**verified working live** (confirmed "Connected to remote server" /
"Proxy established successfully" before this was wired in). Any MCP
servers you already had configured are left untouched.

## 2. Model provider (manual — one time)

Cline's provider settings aren't in a plain file (same situation as Kilo
Code), so this is a UI step:

1. Open Cline's settings (gear icon in its panel).
2. **API Provider** → **OpenAI Compatible**.
3. **Base URL**: `http://localhost:4000/v1`
4. **API Key**: your `LITELLM_MASTER_KEY` from `.env`.
5. **Model ID**: any of `kilo-code` / `kilo-ask` / `kilo-debug` /
   `kilo-plan` / `kilo-orchestrator` / `claude` / `gemini` (same models
   config.yaml already defines for every other editor).

Cline doesn't have Kilo Code's 5-mode concept — it's one active
model/profile at a time. Create one **Configuration Profile** per model
above (Cline supports multiple named profiles) if you want to switch
between them the way Kilo Code's mode picker does.
