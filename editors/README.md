# 11 supported editors/agents (+1 subscription-gated bonus)

All 11 point at the same LiteLLM proxy and the same 16-server MCP gateway
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
| [OpenCode](opencode/) | Terminal/desktop coding agent | native remote MCP | ✅ Fully live-tested with the real binary: chat via `build`/`plan` agents, all 3 MCP servers connected |
| [OpenWork](openwork/) | Desktop "Claude Cowork" alternative (embeds OpenCode) | native remote MCP | ✅ Engine layer live-tested with OpenWork's own runtime config; GUI itself not driven |
| [Goose](goose/) | CLI + desktop agent | `mcp-remote` bridge | ✅ Fully live-tested: chat, a gateway tool call, and a whole-machine file listing via desktop-commander |
| [Cherry Studio](cherry-studio/) | Desktop AI Workspace & Agent | native SHTTP/SSE | ✅ Fully set up & live-tested with LiteLLM models and agents |

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

## The power pack (closer to Claude Desktop / Code)

The newest editors (OpenCode, OpenWork, Goose) additionally get two local
MCP servers, so they can do things the LiteLLM gateway (a container with no
view of your machine) can't:

| Server | Gives the agent | Verified |
|---|---|---|
| [`desktop-commander`](https://github.com/wonderwhy-er/DesktopCommanderMCP) | File browsing/search/edit **anywhere on the machine** (the gateway's filesystem server only sees the mounted `/workspace`), terminal sessions, process management | ✅ connects in OpenCode; real file-listing call through Goose |
| [`windows-mcp`](https://github.com/CursorTouch/Windows-MCP) (Windows only) | **Desktop control**: screenshots, clicking, typing, window/app control | ✅ starts and connects in OpenCode and Goose; GUI actions themselves not exercised |

Goose also gets its own built-in `computercontroller` extension switched on.
Everything else Claude Desktop/Code-like already comes through the gateway
for **every** editor: Playwright (browser), SSH (`SSH_HOST`/`SSH_USERNAME`/
`SSH_PASSWORD` on the dashboard's API Keys page), databases, audio/video,
memory, sequential thinking, an LSP bridge.

Not every editor gets the pack, on purpose: **Hermes** ships its own native
`computer_use` toolset and terminal/SSH backends (`hermes tools`), so adding
these would duplicate it; **Cline and Kilo Code** already have entries for
`desktop-commander`, `darbot-windows-mcp` and `ssh-mcp` in your own
settings (Kilo's desktop-commander/darbot ones are currently switched
off — flip `enabled` in `~/.config/kilo/kilo.jsonc` if you want them); **Zed, Aider, Tabby, OpenHands, Copilot** weren't given it because
I couldn't verify it there and didn't want to ship untested config. Each
installer takes `--no-power` if you'd rather not have it.

### Why these are local, not in the LiteLLM gateway

Desktop control over a network port would be a remote-control hole.
`host.docker.internal` resolves to your **LAN IP** on this machine, so a
gateway-registered host server would have to listen beyond loopback. (Even
`windows-mcp` itself refuses non-loopback binding without an auth key.)
Local stdio servers have no port at all.

### Security: what the power pack can do

`desktop-commander` + `windows-mcp` let a model read/write any file you can,
run commands, and click and type in any window. That is the feature — but it
means **prompt injection becomes serious**: a web page, document or tool
result the agent reads could try to steer it. Sensible habits: don't point
these agents at untrusted content while the pack is on; keep secrets out of
files the agent can browse; use `--no-power` for agents you run
unattended; and `windows-mcp serve --exclude-tools ...` can remove
individual tools (e.g. `PowerShell,Registry`) if you want a narrower pack.

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
