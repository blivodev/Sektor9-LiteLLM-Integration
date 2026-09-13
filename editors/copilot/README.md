# GitHub Copilot Chat (VS Code)

**Read this before installing**: GitHub Copilot itself is a paid,
GitHub-hosted service — it is *not* open source and this doesn't make it
free. What *is* real and open source is a bridge extension that lets
Copilot Chat's model picker send requests to your own LiteLLM server
instead of GitHub's backend. You still need an active Copilot
subscription, signed in, for the extension to work at all — this is an
alternative front-end for people who already pay for Copilot and want to
also reach LiteLLM's models/fallbacks from inside it, not a 6th free
option. If you don't already have Copilot, one of the other 5 editors in
`editors/` gets you the same LiteLLM-backed workflow for less setup.

**Status**: researched and its docs verified via direct fetch (exact
settings keys, exact MCP config schema below are copied from real
documentation, not guessed) — not personally installed/tested end-to-end
this session, since that needs a real signed-in Copilot subscription.
Same honesty bar as `editors/openhands/README.md`.

## What you need

- VS Code 1.136 or newer.
- The `GitHub.copilot-chat` extension, installed and **signed in** to an
  active Copilot subscription.
- The `vivswan.litellm-vscode-chat` extension — open source
  ([github.com/Vivswan/litellm-vscode-chat](https://github.com/Vivswan/litellm-vscode-chat)),
  MIT-style, built specifically to bridge Copilot Chat to a LiteLLM
  server. Supports 100+ models, multi-server aggregation, and automatic
  cheapest/fastest provider selection on its own — genuinely useful even
  outside this project.

```bash
code --install-extension GitHub.copilot-chat
code --install-extension vivswan.litellm-vscode-chat
```

## 1. Model provider (scripted)

```bash
python editors/copilot/install.py
```

Merges a `litellm-vscode-chat.servers` entry into VS Code's real
`settings.json` — same shape the extension's own "Manage Models..." UI
writes, so nothing else you've configured there is touched:

```json
"litellm-vscode-chat.servers": [
  { "label": "LiteLLM (local)", "baseUrl": "http://127.0.0.1:4000", "auth": { "apiKey": "<your master key>" } }
]
```

Open the chat panel (`Ctrl+Alt+I`) → model picker → your `kilo-code` /
`kilo-ask` / `kilo-debug` / `kilo-plan` / `kilo-orchestrator` / `claude` /
`gemini` models should already be listed under "LiteLLM (local)".

## 2. MCP gateway (scripted, one manual prompt)

The same script also merges a `litellm-gateway` entry into this
project's **workspace** `.vscode/mcp.json` — this is VS Code's own native
MCP client, the one Copilot Chat's agent mode reads directly, so **no
`mcp-remote` bridge is needed here** (unlike Cline/Zed, which only speak
stdio):

```json
{
  "inputs": [
    { "type": "promptString", "id": "litellm-master-key", "description": "LiteLLM master key", "password": true }
  ],
  "servers": {
    "litellm-gateway": {
      "type": "http",
      "url": "http://127.0.0.1:4000/mcp",
      "headers": { "Authorization": "Bearer ${input:litellm-master-key}" }
    }
  }
}
```

Deliberately **not** hardcoding the master key here, the way Cline/Zed's
installers do for their own settings files: those live in your user
profile, outside this repo; `.vscode/mcp.json` lives *inside* the
project and could end up committed. VS Code prompts you for the key the
first time the server connects and keeps it in its own secret storage
after that — one extra click, in exchange for never risking the key
landing in git history.

## Why this isn't in the main 5-editor comparison table

It's a legitimate option, but a different category from the other 5:
every one of those works standalone with just an API key for the
providers you choose. This one requires an unrelated paid subscription
just to unlock the extension surface that then talks to LiteLLM — worth
having documented for whoever already has Copilot, not worth presenting
as an equal, no-extra-cost alternative.
