# Hermes Agent

[Hermes Agent](https://hermes-agent.nousresearch.com/) — Nous Research's
open-source (MIT) agent app, runs locally or in the cloud, with its own
desktop UI, terminal mode, and messaging-platform integrations (Telegram/
Discord/Slack/etc). Its own docs name **LiteLLM by name** as a supported
self-hosted provider, so this is a genuinely first-class fit, not a
stretch — and it's now **live-verified end to end** on this machine, not
just configured on paper.

## Important: two different things share the name "Hermes"

- **Hermes Agent** (this integration) — the app itself. Free, open
  source, no subscription. This is what gets wired up below.
- **Hermes-3/4** — Nous Research's own open-weight *models*, available
  via OpenRouter/DeepInfra. These are **not** used by default here, and
  deliberately so — see the caveat right below.

## Why the default model is `kilo-code`, not a Hermes model

Checked before writing anything (live against the real provider APIs,
not assumed):

| Model | Provider | $ in/out per 1M | Tool calling |
|---|---|---|---|
| `kilo-code` (DeepSeek-V4-Flash) | DeepInfra | $0.18 / $0.18 | ✅ Yes |
| Hermes-4-405B | OpenRouter | $1.00 / $3.00 | ❌ **No** (confirmed via OpenRouter's live `/api/v1/models`, `supported_parameters` excludes `tools`) |
| Hermes-3-70B | OpenRouter | $0.70 / $0.70 | ❌ No |
| Hermes-3-405B | OpenRouter | $1.00 / $1.00 | ❌ No |
| Hermes-3-405B | DeepInfra | $1.00 / $1.00 | ✅ Yes (per LiteLLM's price map) |
| Hermes-3-70B | DeepInfra | $0.70 / $0.70 | ⚠️ Unconfirmed |

A coding agent that can't reliably call tools can't edit files, run
commands, or use the MCP gateway — that's most of what this whole
project exists to do. None of the Hermes options above beat `kilo-code`
on both price and tool support at once on the 3 providers this project
uses. `install.py` sets Hermes Agent's `model.default` to `kilo-code`
for exactly this reason.

If you want to try a Hermes model anyway (for plain chat/exploration,
not agentic coding), switch it live with `hermes model` — DeepInfra's
Hermes-3-405B is the one confirmed to support tools if you do want
agentic use despite the higher price.

## Setup

```bash
python editors/hermes/install.py
```

Runs Hermes's **own** `hermes config set` CLI (not a hand-edited config
file — see why in `install.py`'s docstring: its real config.yaml is a
100KB+ reference file, and a first version of this script that tried to
merge into it directly, on the wrong path, is exactly the kind of mistake
this approach avoids) to set:

```
providers.litellm.api        = http://127.0.0.1:4000/v1
providers.litellm.key_env    = LITELLM_API_KEY
model.default                = kilo-code
model.provider                = custom:litellm
mcp_servers.litellm-gateway.url                    = http://127.0.0.1:4000/mcp
mcp_servers.litellm-gateway.headers.Authorization  = Bearer <your master key>
```

The master key goes into Hermes's own `.env` (path from `hermes config
env-path`) as `LITELLM_API_KEY`, never into `config.yaml` itself.

**Real path note**: Hermes's own docs describe `~/.hermes/config.yaml`,
which is Unix-only — on Windows it's actually
`%LOCALAPPDATA%\hermes\config.yaml` (confirmed live via `hermes config
path` on this machine). `install.py` asks Hermes itself for the paths
rather than hardcoding either.

## Verified live, this session, on this machine

Not just "config looks right" — a real round trip through the whole
chain:

```
$ hermes -z "reply with exactly the word pong" --provider litellm -m kilo-code
pong
```

And the MCP gateway:

```
$ hermes mcp test litellm-gateway
  Transport: HTTP -> http://127.0.0.1:4000/mcp
  [OK] Connected (17609ms)
  [OK] Tools discovered: 152
```

Both confirmed working end to end: Hermes Agent -> LiteLLM ->
`kilo-code` (DeepInfra) for chat, and Hermes Agent -> LiteLLM's MCP
gateway -> all 16 configured MCP servers for tools. This is the most
thoroughly live-tested of the newer editors added this session (more
than Tabby or Copilot Chat, which stopped at config verification).

## On "two configs" (vanilla vs. extended)

If you want a second profile that keeps Hermes's own native
providers/models available *alongside* LiteLLM rather than this one
fully swapping the default, that's a real, buildable ask — Hermes
supports multiple named provider profiles (see `hermes model`'s
provider picker). Say more about what the second one should actually
show or do and it'll get built properly rather than guessed at; nothing
in Hermes's own docs suggests a feature matching the VS Code balance
extension's status-bar display specifically, so that particular parity
isn't something to reproduce as-is.
