# OpenCode

[OpenCode](https://opencode.ai) — open-source terminal/desktop coding agent
(Kilo Code is a fork of it, which is why its config looks so familiar).
**Fully live-verified on this machine**, using the real `opencode` binary.

## Setup

```bash
python editors/opencode/install.py
```

Edits your real global config (`~/.config/opencode/opencode.jsonc`, same
path on Windows). Your old file is backed up first
(`opencode.jsonc.bak-<timestamp>`) and every value the installer changed is
recorded in a comment at the top of the new one.

What it adds/changes:

| | |
|---|---|
| **Provider `litellm`** | OpenAI-compatible, `http://127.0.0.1:4000/v1`. Models are discovered live from the proxy, so a mode you add on the dashboard's *Custom Routing* page shows up after a re-run. |
| **MCP `litellm-gateway`** | The whole 16-server gateway, as a remote MCP server. |
| **Power pack** (MCP, local) | `desktop-commander` + `windows-mcp` — see [the power pack](../README.md#the-power-pack-closer-to-claude-desktop--code). Skip with `--no-power`. |
| **Default `model` / `small_model`** | `litellm/kilo-code` / `litellm/kilo-ask` |
| **Agents** | `build`→`kilo-code`, `plan`→`kilo-plan`, `general` and `explore`→`kilo-ask` |

Pass `--no-rebind` to only *add* things and leave your own model/agent
choices alone. Nothing secret is written to the file: the provider and the
MCP header use OpenCode's `{env:LITELLM_API_KEY}` substitution (confirmed
live), and the installer sets that variable persistently for your user.
**Open a new terminal (or restart apps) after the first install** so they
see it.

### Your previous setup

Your config pointed straight at DeepInfra/OpenRouter (Claude Sonnet for
`plan`, Gemini Flash for `general`), which bypasses LiteLLM — no fallbacks,
no spend tracking. Those exact values are preserved in the header comment.
`claude` and `gemini` are still available through LiteLLM as models you can
pick (`/models` in OpenCode) — they just aren't the automatic defaults,
because the automatic modes are the ones with cross-provider fallback
chains.

## Verify

```bash
opencode mcp list                                   # 3x "connected"
opencode run "say pong"                             # > build · kilo-code
opencode run --agent plan "say pong"                # > plan · kilo-plan
```

Verified this session against the installer's real output: all three MCP
servers connected, `build` answered via `kilo-code`, `plan` via `kilo-plan`.

## Cost of having every tool switched on

Measured from LiteLLM's own spend log: a trivial `say pong` in OpenCode
carried **~60,000 prompt tokens** (`build` 62,123, `plan` 60,012), because
OpenCode sends the schema of every tool it can see — ~150 from the gateway
plus the power pack — with every request. Goose sent ~12k for the same
thing — probably because your Goose has its "Code Mode" extension enabled, which routes tool calls through code to save tokens (a guess, not verified). At kilo-code's price that is roughly
a cent per message (less when the provider caches the repeated prefix), so it
isn't alarming, but it adds up over a long agent session and slows first
responses. If you don't need all of it: `--no-power`, or disable individual
MCP servers (`"enabled": false`) — the gateway's 16 servers are the bulk.

## Gotchas found while testing

- `windows-mcp` must be started as `windows-mcp serve --transport stdio`.
  Bare `windows-mcp` prints help and exits, which OpenCode shows as
  *"MCP error -32000: Connection closed"* — that looks like a broken server
  but is just a missing subcommand. The installer uses the right form.
- The JSONC parser is string-aware on purpose: a naive `//`-comment regex
  chops `"https://..."` values in half.
