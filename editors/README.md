# 5 supported editors/agents

All 5 point at the same LiteLLM proxy and the same 16-server MCP gateway
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

## Why these 5

You asked for editors/tools other than "just Kilo Code + VS Code," using
open source software that's actively maintained so new features can be
absorbed without us hand-rolling everything ourselves. That maintenance
requirement turned out to matter in practice — see the rejected
candidates above.

## Common pattern

Every editor here needs two things pointed at LiteLLM:
1. **The model provider** — an OpenAI-compatible base URL
   (`http://localhost:4000/v1`) + your `LITELLM_MASTER_KEY`.
2. **The MCP gateway** — either natively (OpenHands) or via
   [`mcp-remote`](https://www.npmjs.com/package/mcp-remote) bridging
   `http://localhost:4000/mcp` into a local stdio process (everything
   else here).

Where a tool's provider settings aren't in a plain file (Cline, Kilo
Code), that's a one-time manual step in its own Settings UI — documented
per-editor, not something worth risking a script hacking a proprietary
internal state file to avoid.
