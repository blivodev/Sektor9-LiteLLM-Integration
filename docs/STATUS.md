# Status, bugs found & fixed, potential upgrades

## Current status (2026-09-13)

| Area | Status |
|---|---|
| LiteLLM + Postgres containers | ✅ Up, healthy |
| 5 Kilo Code modes | ✅ All wired, all 17 model entries live-tested |
| MCP gateway | ✅ 13/16 servers healthy; 3 correctly inert pending API keys |
| Kilo Code VS Code integration | ✅ Working via global config (see "Bugs found" #10) |
| `litellm-provider-balance` extension | ✅ Installed as a real `.vsix`, status bar live |
| Model auto-refresh | ✅ Built, live-tested (`--dry-run`), not yet run for real |
| Cross-platform setup script | ✅ Written, syntax-verified, not yet run end-to-end on a fresh machine |
| Git repo | ✅ Pushed to [github.com/YOUR_USERNAME/litellm-setup](https://github.com/YOUR_USERNAME/litellm-setup) |
| Host-companion apps (Unity/Godot/Nuclear/Windows-control) | ⏳ Documented, not yet actually set up |

## Bugs found and fixed (in the order discovered — useful if something similar recurs)

1. **Postgres 18+ changed its volume-mount convention.** The image now
   expects a single mount at `/var/lib/postgresql` (it places
   version-specific subdirectories itself); mounting at
   `/var/lib/postgresql/data` directly breaks it with a confusing
   "unused mount/volume" error.
2. **`DATABASE_URL` pointed at `localhost` instead of the `postgres`
   service name.** Inside the `litellm` container, `localhost` means
   itself, not the Postgres container — they're reachable by service name
   over the Docker Compose network.
3. **MCP server names can't contain a hyphen.** `sequential-thinking`
   crashed LiteLLM's *entire* startup (not just that one server) with
   `Server name cannot contain '-'`. Renamed to `sequential_thinking`.
4. **LiteLLM's stdio MCP launcher only reliably registers
   `command: npx` or `command: uvx`.** A direct binary path
   (`mcp-language-server`), bare `uv`, and `sh -c "..."` all failed to
   register with *zero log output at all* — not even an error — while the
   exact same binaries worked fine run by hand. Worked around with a tiny
   local `npx-shim` npm package (`Dockerfile` + `/opt/npx-shim`) that lets
   any real command masquerade as an `npx` one. This looks like a genuine
   LiteLLM limitation/bug, not a config mistake — worth a GitHub issue on
   `BerriAI/litellm` if it matters to you.
5. **`os.environ/VAR` substitution works in `mcp_servers.<name>.env`
   values, but NOT in `args` list items.** Confirmed by direct log
   evidence: an `args` entry literally received the string
   `"os.environ/DATABASE_URL"` instead of the resolved value. Fix: put
   secrets in `env:`, never in `args`.
6. **LiteLLM auto-appends its own Prisma connection-pool query
   parameters** (`connection_limit`, `pool_timeout`, ...) whenever it
   resolves `os.environ/DATABASE_URL` *specifically* — that variable name
   is "magic" to it, since it's also LiteLLM's own DB config key. A
   stricter client (`postgres-mcp`) rejected the unrecognized params. Fix:
   a dedicated `MCP_POSTGRES_DSN` variable in `.env`, same value, different
   (non-magic) name.
7. **Several `uvx`-run Python MCP servers crashed with
   `ModuleNotFoundError: mcp.server.fastmcp`.** `uvx` resolves the newest
   `mcp` SDK (v2, which renamed `FastMCP`→`MCPServer`) by default, but
   most published servers are still pinned to v1's API. Fix:
   `uvx --with "mcp<2" <package>`.
8. **Pre-existing MCP entries added via the LiteLLM UI referenced
   fictional packages** (`@anthropic/mcp-server-google-calendar`,
   `-browserbase`, `-redis`, `-docker`, `-mysql`) — confirmed via real
   `npm 404` errors. Whatever "quick add" catalog suggested those names
   was wrong; deleted all five.
9. **The official `@modelcontextprotocol/server-postgres` has an
   unpatched SQL injection vulnerability** and was archived without a fix
   (confirmed via research, not used anywhere in this repo). Use `DBHub`
   or `postgres-mcp` instead.
10. **Kilo Code did not pick up the project-root `kilo.jsonc` automatically**,
    despite that being the documented behavior. The config that actually
    took effect lives at the **global** `~/.config/kilo/kilo.jsonc`,
    written by Kilo Code's own Settings UI (Providers → Custom provider →
    Connect). The project file is kept as a reference/fallback only.
11. **Kilo Code silently blocks all shell/bash commands if a project-root
    `kilo.json` (separate from `kilo.jsonc`) exists but is empty or invalid
    JSON** — even with workspace trust and Auto-Approve set correctly. Fix:
    keep it valid, e.g. `{"$schema": "...", "permission": {"bash": "allow"}}`.
12. **A manually-dropped VS Code extension folder isn't recognized by
    modern VS Code** (`code --list-extensions` won't show it) without a
    matching entry in the extensions folder's own `extensions.json`
    manifest. The reliable fix is packaging a real `.vsix`
    (`npx @vscode/vsce package`) and installing it via
    `code --install-extension`.
13. **Windows PowerShell 5.1 doesn't reliably read UTF-8 without a BOM.**
    Em-dash characters in a `.ps1` file corrupted mid-parse into a cascade
    of unrelated-looking syntax errors. Fix: stick to plain ASCII in
    PowerShell scripts.
14. **Fireworks' current serverless catalog has no Llama model of any
    kind** (verified live against `/v1/models`) — a fallback originally
    planned for Llama 3.3 70B was swapped to GLM-5.3-Flash instead.
15. **Providers' catalog APIs mostly don't expose per-model pricing**
    (confirmed: DeepInfra and Fireworks return none at all via their own
    `/models` endpoints). Fixed in `refresh_models.py` by using
    [LiteLLM's own community-maintained price map](https://github.com/BerriAI/litellm/blob/main/model_prices_and_context_window.json)
    as the primary pricing source instead.

## Known open items

- **`language_server_go` and `video_audio` MCP servers** needed the same
  `npx-shim` workaround as bug #4 above — now healthy, but the underlying
  LiteLLM limitation is unreported upstream. Worth filing if you rely on
  many non-npx/uvx MCP servers going forward.
- **Gemini escape-hatch key** (`gemini` model) has an unusual format
  (`AQ.…`, resembling a Google OAuth access token rather than an AI Studio
  key `AIzaSy…`). It worked when tested (routed through Vertex AI), but
  access tokens like that typically expire in about an hour — if `gemini`
  stops working, get a durable AI Studio key instead.
- **Anthropic escape-hatch key** (`claude` model) authenticates
  successfully but the account has **insufficient credit** — add funds at
  [console.anthropic.com/settings/billing](https://console.anthropic.com/settings/billing).
- **`meshy_3d`, `elevenlabs`, `suno_music`** MCP servers need their own
  API keys added to `.env` (blank placeholders are already there).
- **Host-companion apps** (Blender, Godot, Unity, Nuclear, Windows desktop
  control) are documented in [`setup/README.md`](../setup/README.md) and
  wired into `setup.ps1`/`setup.sh`'s printed instructions, but none have
  actually been installed/run yet.

## Potential upgrades (not started)

- Add OpenRouter's per-backend-provider pricing endpoint
  (`GET /api/v1/models/{author}/{slug}/endpoints`, confirmed real and
  public) to `refresh_models.py` for finer-grained comparison within
  OpenRouter itself, on top of the cross-provider comparison it already does.
- Mobile development MCP servers (`mobile-mcp`, `xcode-mcp`) were deferred
  — they need Android SDK/Xcode installed on whatever machine runs them,
  same host-companion pattern as Blender/Godot/Unity.
- 2D creative tools (Aseprite/Krita MCP servers) were deferred for the
  same reason — they need the actual desktop app installed and running.
- Run `setup.ps1`/`setup.sh` end-to-end on a genuinely fresh machine to
  confirm the whole one-click flow works, not just each piece individually.
- Real UI screenshots for `docs/USER_GUIDE.md` — see
  [`docs/images/README.md`](images/README.md) for exactly what's needed.
