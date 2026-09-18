# 7 supported editors/agents (+1 subscription-gated bonus)

All 7 point at the same LiteLLM proxy and the same 16-server MCP gateway
— pick whichever fits how you like to work. Every candidate was checked
for real, current maintenance status before being included here (3 other
strong-looking candidates — **Void**, **Continue.dev**, and **Roo
Code** — were researched and rejected because they turned out to be
deprecated/archived/acquihired-and-unmaintained as of 2026; don't be
surprised if this list needs revisiting again down the line for the same
reason).

| Editor | Type | MCP transport | Verified this session |
|---|---|---|---|
| [Kilo Code](kilo-code/) | VS Code extension | native | ✅ Fully set up (the original integration) |
| [Cline](cline/) | VS Code extension | `mcp-remote` bridge | ✅ Live-tested — MCP gateway connection confirmed |
| [Zed](zed/) | Standalone editor (Rust) | `mcp-remote` bridge | ✅ Live-tested — config load confirmed, one real bug found & fixed |
| [Aider](aider/) | Terminal tool | **not supported** | ✅ Live-tested LLM connectivity; MCP confirmed absent (not assumed) |
| [OpenHands](openhands/) | Autonomous agent platform | native SHTTP | ⚠️ Researched, not personally installed/tested — heaviest install of the 5 |
| [Tabby](tabby/) | Self-hosted server + IDE extension | (Tabby has no MCP client of its own) | ⚠️ Config verified against real docs + `setup.py` actually run (valid output confirmed); the multi-GB server container itself not personally pulled/started |
| [Hermes Agent](hermes/) | Desktop/terminal agent app | native HTTP | ✅ Fully live-tested: real chat round-trip (`hermes -z "..." --provider litellm -m kilo-code` → real reply) and MCP gateway (`hermes mcp test` → 152 tools discovered) both confirmed working on this machine |

**Tabby** is the odd one structurally: it's not an editor or extension by
itself, it's its own self-hosted server that a thin IDE extension then
talks to (`IDE extension -> Tabby -> LiteLLM -> your providers`, one hop
more than the rest) — but it's genuinely free/open-source, no
subscription of any kind, unlike the Copilot bonus below. Its own
`README.md` has an important caveat about inline-completion quality with
this project's current (chat/instruct, not FIM) models.

**Hermes Agent** is genuinely free/open-source too, and its own docs
name LiteLLM as a supported provider by name. Its config defaults to
`kilo-code`, deliberately *not* a Hermes-branded model — Nous Research's
own Hermes-3/4 models show no tool-calling support on OpenRouter and are
pricier than `kilo-code` even on DeepInfra where tools do work (all
verified live against the real provider APIs, see `hermes/README.md` for
the full price/tool-support table). A coding agent that can't call tools
can't edit files or run commands, so the model default reflects that,
not the app's own branding.

Plus **[GitHub Copilot Chat](copilot/)** — not a free option (needs an
active, signed-in Copilot subscription just to unlock the extension
surface), so it's kept out of the table above, but documented and
scripted the same way for whoever already pays for Copilot and wants it
to reach LiteLLM's models/fallbacks too, via the open-source
`vivswan.litellm-vscode-chat` bridge extension plus VS Code's own native
MCP client (no `mcp-remote` bridge needed there, unlike Cline/Zed). Its
`install.py` merge logic was unit-tested against scratch copies this
session (preserves unrelated settings, idempotent re-runs, never writes
the master key into the workspace-tracked `.vscode/mcp.json`) — not
installed end-to-end, since that needs a real Copilot subscription.

## Why these editors

You asked for editors/tools other than "just Kilo Code + VS Code," using
open source software that's actively maintained so new features can be
absorbed without us hand-rolling everything ourselves. That maintenance
requirement turned out to matter in practice — see the rejected
candidates above.

## Common pattern

Every editor here needs two things pointed at LiteLLM:
1. **The model provider** — an OpenAI-compatible base URL
   (`http://127.0.0.1:4000/v1`) + your `LITELLM_MASTER_KEY`.
2. **The MCP gateway** — either natively (OpenHands) or via
   [`mcp-remote`](https://www.npmjs.com/package/mcp-remote) bridging
   `http://127.0.0.1:4000/mcp` into a local stdio process (everything
   else here).

Where a tool's provider settings aren't in a plain file (Cline, Kilo
Code), that's a one-time manual step in its own Settings UI — documented
per-editor, not something worth risking a script hacking a proprietary
internal state file to avoid.
