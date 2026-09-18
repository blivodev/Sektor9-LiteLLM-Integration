# Status, bugs found & fixed, potential upgrades

## Session 6 additions (this round)

Asked: "how do I point Goose or OpenCode at my setup?", then "also set up
OpenWork", then "install anything that brings some of them close to Claude
Desktop/Code -- desktop control, remote/SSH, file browsing". All three
editors are installed on this machine, so everything below was tested against
the real binaries, not just docs.

- **OpenCode** (`editors/opencode/`): `python editors/opencode/install.py`.
  The real finding: your existing config pointed straight at DeepInfra and
  OpenRouter, **bypassing LiteLLM entirely** (no fallbacks, no spend
  tracking). Now it has a `litellm` provider + the gateway MCP server, and the
  default model / `build` / `plan` / `general` / `explore` agents are bound to
  `kilo-code` / `kilo-code` / `kilo-plan` / `kilo-ask` / `kilo-ask`. Your old
  values (Claude Sonnet for `plan`, Gemini Flash for `general`) are kept in a
  header comment plus one `.bak-*` file; `claude`/`gemini` remain selectable
  models. Keys stay out of the file via OpenCode's `{env:LITELLM_API_KEY}`
  substitution (confirmed live). Verified on your real config: 3 MCP servers
  connected, `build · kilo-code` and `plan · kilo-plan` both answer.
- **OpenWork** (`editors/openwork/`): it is a desktop app that embeds an
  OpenCode engine per workspace and layers its own generated runtime config
  with each workspace's `opencode.jsonc`, so the installer writes the
  workspace file(s) (auto-detected from OpenWork's server state). Verified by
  hiding the global OpenCode config and layering OpenWork's real runtime
  config: the workspace file alone gave the engine the provider, all MCP
  servers, and a working `openwork · kilo-code` chat. **Not verified**:
  driving OpenWork's GUI itself.
- **Goose** (`editors/goose/`): custom-provider JSON + YAML extensions,
  sandboxed with `GOOSE_PATH_ROOT` for testing, then applied for real.
  Real chat, a real gateway tool call and a real whole-machine listing via
  desktop-commander all passed. Your real config (26 extensions after your
  own `goose configure` session) was diffed against its backup: every
  extension kept, no existing setting changed.
- **The "power pack"** (`editors/_common/common.py`): `desktop-commander`
  (whole-machine file browsing/search/edit, terminal, processes) and
  `windows-mcp` (Windows desktop control), as **local stdio servers** for
  OpenCode/OpenWork/Goose (+ Goose's built-in `computercontroller` enabled).
  Deliberately *not* gateway entries: `host.docker.internal` is this
  machine's LAN IP, so a host-side desktop-control server registered in the
  gateway would have to listen beyond loopback. Hermes was left alone (native
  `computer_use` + terminal/SSH backends); Cline/Kilo already had entries of
  their own; Zed/Aider/Tabby/OpenHands/Copilot were not given it because I
  couldn't verify it there. `ARCHITECTURE.md`'s old description of desktop
  control as a gateway "host-companion" was wrong for this design and is fixed.
- **Dashboard**: the API Keys page now re-runs every installer that embeds
  the master key (cline, zed, hermes, opencode, openwork, goose), the newer
  ones with `--no-rebind` so a key rotation never resets a model/agent choice.

### Bugs and dead ends found (in the order hit)

1. `windows-mcp` "Connection closed" in OpenCode: bare `windows-mcp` prints
   help and exits; it needs `windows-mcp serve --transport stdio`.
2. **Goose's native `streamable_http` extension does not send the
   `Authorization` header** (gateway replied `authentication_required`,
   Goose said "failed to initialize MCP client"). Confirmed the gateway
   accepts the header via curl. Fixed with the `mcp-remote` stdio bridge.
3. Trying to make that bridge read the key from the environment instead of
   Goose's `config.yaml` **hung** (unauthenticated `mcp-remote` waits on an
   OAuth flow), so the key is in the extension's `envs` -- same trade-off as
   Cline's settings.
4. A naive `//`-comment-stripping regex corrupted `"https://..."` strings (the
   same false alarm hit earlier on `kilo.jsonc`); the JSONC parser is now
   string-aware.
5. Re-running the OpenCode installer created a fresh backup every time and
   dropped its own "values this replaced" record. Now: one backup of the true
   original, record carried forward (tested across 3 runs).
6. **Goose looked configured but was still bypassing LiteLLM.** Goose 1.51's
   `active_provider` + `providers:` selection (written by `goose configure`)
   overrides the legacy `GOOSE_PROVIDER`/`GOOSE_MODEL` keys. The first
   installer passed on a fresh config and silently did nothing on yours
   (`active_provider: openrouter`); a "pong" from your real config had come
   via OpenRouter. Caught only because the session banner read `openrouter
   deepseek/deepseek-v4-flash`. Fixed: the installer sets both schemes and
   prints what it replaced; re-verified on a copy of the real result
   (banner `litellm kilo-code`). Lesson: check *which provider answered*, not
   just that something answered.
7. **Tool schemas dominate prompt size**: LiteLLM's spend log shows OpenCode
   sending ~60k prompt tokens for a one-word reply (all gateway + power-pack
   tool schemas on every request); Goose ~12k. Not a bug, but a real
   per-message cost of "everything switched on" -- documented in
   `editors/opencode/README.md` with the knobs to turn it down.
8. **Test-harness lesson**: a `timeout`-killed `goose run` piped through
   `grep | tail` printed nothing, because orphaned extension processes keep
   the pipe open -- it looked like Goose had hung. LiteLLM's spend log
   (`/spend/logs`) showed the request had actually succeeded in ~3s. When
   output goes missing, check the provider-side record before concluding the
   tool failed.
9. **Two side effects of testing on your live setup, for the record**: (a) I
   found a `goose configure` session of yours open and did not kill it; the
   Goose installer now refuses to run while one is open, since it rewrites
   `config.yaml` on exit. (b) My headless test of your real Goose config
   started the OAuth flow of your **existing `glif` extension** and tried to
   open a browser tab. Nothing was authorized; that extension is yours and I
   left it alone (later tests ran on a copy with OAuth extensions off).

## Session 5 additions

- **Fixed a real, self-inflicted production incident**: `OPENROUTER_API_KEY`
  in `.env` had been overwritten with the literal string `hacked` earlier
  in Session 4, when a CSRF test command was accidentally sent to a stale,
  unpatched dashboard process (before that session's CSRF fix had loaded)
  instead of erroring. This silently broke every OpenRouter-routed
  fallback (`kilo-code-fallback-1`, etc.) with `AuthenticationError:
  Missing Authentication header` -- the actual cause of "Kilo Code keeps
  halting, no visible error." Confirmed via the dashboard's own Balances
  page showing `OpenRouter: error: 'data'`. Fixed once the user supplied
  a fresh key; verified live: `kilo-code-fallback-1` now returns a real
  completion (`"pong"`, `finish_reason: stop`) and the dashboard shows a
  real balance again.
- **Fixed a second real bug found while investigating**: `scripts/
  start-litellm.ps1` (and this session's edits to it) had em-dash
  characters, the exact known PowerShell-5.1-can't-reliably-read-UTF-8
  issue already documented in this file's bug list (#13) -- caught via
  the script failing to parse at all when checked with PowerShell's own
  parser, not assumed. Replaced with plain ASCII throughout.
- **Dashboard made durable**: `scripts/start-litellm.ps1` (already
  auto-run on VS Code folder open via `.vscode/tasks.json`) now also
  starts the dashboard if it isn't already running, detached, logging to
  `dashboard/dashboard.log`/`.err.log` (gitignored). Idempotent -- a
  second run correctly detects it's already up rather than double-starting
  it. Verified live: killed the dashboard, ran the script, confirmed it
  came back up and answered HTTP 200; ran again, confirmed it correctly
  skipped starting a second instance.
- **Kilo Code's other built-in agent behaviors wired up**: Kilo Code ships
  more agents than the 5 originally accounted for (`architect`,
  `code-reviewer`, `code-simplifier`, `code-skeptic`, `data`,
  `docs-specialist`, `frontend-specialist`, plus `general`/`explore` for
  sub-agent delegation) -- confirmed directly from a real Settings
  screenshot, not assumed, after an earlier guess at their internal key
  names turned out to need correction from the user. `~/.config/kilo/
  kilo.jsonc`'s `agent` object accepts arbitrary keys (confirmed against
  Kilo's own published config schema), so each of the 7 new ones got a
  model binding reusing an existing `config.yaml` model_name (no new
  model_list entries) rather than silently falling through to whatever
  the UI's last-selected profile happens to be. See `docs/ARCHITECTURE.md`
  for the full mapping and reasoning per agent.
- **Added Hermes Agent as a fully live-tested 7th editor**
  (`editors/hermes/`) -- researched at the user's request, and unlike
  every other editor added this project, actually verified end-to-end
  with a real running installation on this machine, not just config
  review:
  - Real chat round-trip: `hermes -z "reply with exactly the word pong"
    --provider litellm -m kilo-code` -> `pong`.
  - Real MCP gateway test: `hermes mcp test litellm-gateway` -> connected,
    152 tools discovered across all 16 configured MCP servers.
  - **A real mistake made and then caught within the same session**: the
    first version of `install.py` merged directly into `~/.hermes/
    config.yaml` via `ruamel.yaml` -- which turned out to be flatly wrong
    on Windows, where Hermes actually reads `%LOCALAPPDATA%\hermes\
    config.yaml` (`~/.hermes/` is Unix-only, and Hermes's own docs say so,
    but only for the Unix path -- the Windows path was assumed rather
    than checked, and assuming instead of checking is exactly the mistake
    this project's own conventions exist to prevent). Caught via `hermes
    doctor` reporting a *different* active config path than the one just
    written to, not through guesswork. Rewritten to use Hermes's own
    `hermes config set <key> <value>` CLI instead of hand-editing its
    (100KB+, heavily-commented) real config file at all -- safer, and
    what Hermes's own docs recommend.
  - `model.default` deliberately set to `kilo-code`, not a Hermes-branded
    model: live-checked against OpenRouter's real `/api/v1/models` and
    LiteLLM's price map, every Hermes-3/4 variant on OpenRouter shows no
    tool-calling support, and the one DeepInfra variant that does support
    tools costs 5.5x more per token than `kilo-code`. A coding agent
    without reliable tool calls can't edit files or run commands -- see
    `editors/hermes/README.md` for the full comparison table.
- Considered building dashboard-equivalent UI directly inside every
  editor/extension a second time (user asked again, this session);
  descoped again at the user's own call in favor of continuing to expand
  the dashboard and the editor roster instead.

## Session 4 additions

- **Real root cause found for "Kilo Code hangs forever / can't reach
  LiteLLM or the dashboard": `localhost` resolves to `::1` (IPv6) first
  on this machine, and Docker Desktop's port publishing here doesn't
  answer on the IPv6 loopback** — only `127.0.0.1` (IPv4). Kilo Code's
  own global config (`~/.config/kilo/kilo.jsonc`, written by its Settings
  UI) had `"baseURL": "http://localhost:4000/v1"`, so every request from
  Kilo Code silently hung on a dead IPv6 connection attempt instead of
  erroring — same reason the LiteLLM Admin UI and the dashboard failed to
  load in a real browser. **Fixed** by changing that `baseURL` to
  `http://127.0.0.1:4000/v1`, and by replacing every `localhost:4000` /
  `localhost:8877` in this repo's own configs/docs/scripts with
  `127.0.0.1` for the same reason (grep for `127.0.0.1` if you add a new
  one yourself — don't reintroduce `localhost`).
  - **Honest note on how this was diagnosed**: for a good stretch of this
    session, curl run from this Bash tool against `http://localhost:4000`
    reliably returned nothing (`HTTP 000`), which was *wrongly* read as
    "LiteLLM itself is hung" — leading to disabling several MCP servers
    and adding `timeout:` to every entry, none of which actually did
    anything (all reverted). The same curl against `http://127.0.0.1:4000`
    at the *exact same moment* returned `200 OK` — proving the proxy was
    fine all along and the `localhost` lookup itself was the broken part,
    in this shell specifically. If LiteLLM (or the dashboard) ever again
    seems unreachable, check `127.0.0.1` before assuming anything is
    actually broken.
- **Dashboard now covers model-selection preference, custom per-mode
  routing, and a live model catalog** — no more running scripts by hand
  for these:
  - `/preference`: pick any of the 10 modes; anything but "custom"
    applies immediately (writes the preference, runs
    `refresh_models.py --restart` for real, restarts the container) in
    one click.
  - `/routing`: hand-edit exactly which model backs each mode
    (kilo-code/ask/debug/plan/orchestrator, claude, gemini), or add a
    brand-new mode/model slot. This is the mechanism behind the "custom"
    preference. Reads/writes `config.yaml` via `ruamel.yaml` (not plain
    PyYAML) specifically so the file's extensive comments survive the
    round-trip — confirmed live (61 comment lines intact after a real
    write) and tuned to match the original indent style so a one-field
    change produces close to a one-line diff, not a full reformat.
  - `/models` + `/api/models`: a searchable, live catalog of every model
    your keyed providers currently expose (723 real entries returned in
    testing), price-enriched via the same LiteLLM price map
    `refresh_models.py` uses, cached 5 minutes to avoid hammering
    provider APIs on every page load.
  - Note: adding a mode here only wires up the LiteLLM side (makes a
    `model_name` addressable). Pointing an editor's own custom-mode UI
    (e.g. Kilo Code's Settings → Modes) at that name is still a separate,
    manual step in that editor.
- **Fixed a second CSRF-adjacent bug from an automated review**: the
  Origin/Referer check added last session used `.startswith("http://
  localhost:8877")`, which a string like `"http://localhost:8877.evil.
  com"` also satisfies. Replaced with `urlparse()` + exact
  scheme/hostname/port comparison; verified against that exact bypass
  string plus several variants (all correctly denied) and the legitimate
  origin (still allowed).
- Considered building dashboard-equivalent UI directly inside every
  editor/extension; descoped at the user's call in favor of the one
  dashboard covering all of them, given it's already reachable from
  any editor via a browser link.
- **Added GitHub Copilot Chat as a bonus 6th `editors/` entry**
  (`editors/copilot/`), after verifying the real facts first rather than
  assuming: Copilot itself is a paid service, not open source, but its
  VS Code Chat extension supports custom OpenAI-compatible model
  providers, and there's a genuine open-source bridge extension
  (`vivswan.litellm-vscode-chat`) built for exactly this — confirmed via
  a direct fetch of its real docs (exact `settings.json` keys), not
  guessed. Its MCP connection uses VS Code's own native MCP client
  (`.vscode/mcp.json`, `"type": "http"`) rather than an `mcp-remote`
  bridge, confirmed against VS Code's own MCP configuration reference
  docs. `install.py`'s merge logic (chat-provider settings + workspace
  MCP config) was unit-tested against scratch copies: preserves unrelated
  settings and other server entries, idempotent on re-run, and never
  writes the master key into the workspace-tracked `mcp.json` (uses VS
  Code's `inputs` prompt instead, since that file could end up
  committed) — not installed end-to-end, since that needs a real
  signed-in Copilot subscription this session doesn't have. Kept out of
  the main editor comparison table since it needs that unrelated paid
  subscription just to function, unlike the rest.
- **Added Tabby ([TabbyML/tabby](https://github.com/TabbyML/tabby)) as a
  6th real editor entry** (`editors/tabby/`) — the genuinely open-source,
  no-subscription answer to "alternative to GitHub Copilot" the user
  actually asked for, as opposed to the Copilot bridge above (which still
  needs a paid Copilot account). Confirmed via real docs fetches before
  writing anything: 32k+ GitHub stars, actively maintained (a VS Code
  extension release in Dec 2025, a feature release in July 2025 — not
  stale like Void/Continue.dev/Roo Code), and its `config.toml` schema
  (`[model.chat.http]` / `[model.completion.http]`, `kind = "openai/
  chat"` / `"openai/completion"`) confirmed against Tabby's own
  documentation, not guessed.
  - **Structurally different from every other editor here**: Tabby is
    its own self-hosted server (`editors/tabby/docker-compose.yml`), not
    an IDE/extension — a separate IDE extension talks to Tabby, which
    talks to LiteLLM, one hop more than Cline/Zed/Copilot.
  - **Honest completion-quality caveat documented, not glossed over**:
    real inline "ghost text" completion wants a FIM (fill-in-the-middle)
    base model (StarCoder2/DeepSeek-Coder-Base/Qwen2.5-Coder-Base), not
    the chat/instruct models this project's `config.yaml` otherwise uses
    for agentic tool-calling. Pointing completion at `kilo-code` (the
    template's default) will work but likely won't match Copilot-quality
    ghost text — documented in `editors/tabby/README.md` with the actual
    fix (add a real FIM model as its own `config.yaml` entry) rather than
    silently shipping a config that under-delivers without saying so.
  - **`editors/tabby/setup.py` actually run for real** (not just
    reviewed): produced valid TOML, correctly substituted the real
    master key into both `[model.chat.http]` and
    `[model.completion.http]`, and confirmed the output file
    (`editors/tabby/data/config.toml`, which now holds that key) is
    correctly gitignored. The Docker Compose file was validated with
    `docker compose config` (resolves correctly) but the actual
    multi-GB Tabby server image was not pulled/started this session —
    same honesty line drawn for OpenHands.

## Session 3 additions

- **Fixed 3 real, security-review-flagged bugs in `dashboard/app.py`**, all
  live-tested with an actual curl probe before/after:
  1. **Reflected XSS + docker-argument-injection in `/logs`**: the `?c=`
     query param was echoed straight into the page's HTML *and* passed
     straight to `docker logs <c>` as an argv item, with no validation at
     all. Fixed with a hardcoded allowlist (`{"litellm_proxy", "litellm_db"}`)
     — anything else silently falls back to `litellm_proxy` — plus
     `html.escape()` on the one still-legitimate value. Verified live:
     `?c=<script>alert(1)</script>` now renders `Logs — litellm_proxy`.
  2. **CSRF on `/keys`'s POST** (writes `.env`, force-recreates the
     container — a state-changing endpoint with zero protection). Fixed
     with a per-session token (`secrets.token_hex`, stored via Flask's
     signed session cookie) embedded as a hidden field and checked with
     `secrets.compare_digest`, plus an Origin/Referer check as defense in
     depth. Verified live: an unauthenticated POST now gets `403`; a POST
     carrying the real page's token still gets `200`.
- **Added 4 new model-selection preference modes** (`scripts/set_preference.py`,
  `scripts/refresh_models.py`), bringing the total to 10 — see
  `docs/ARCHITECTURE.md` for the full table:
  - `free` — only picks a genuinely-$0 same-family candidate; verified
    live it correctly finds nothing when a family has no free variant,
    rather than falsely reporting one or reaching outside the family.
  - `local` / `local_cheapest` / `local_best` — deliberately promotes the
    local Ollama model (from `setup_ollama.py`) to PRIMARY for Code/Ask
    only, demoting the previous cloud primary to a fallback (same
    never-delete safety pattern as every other upgrade here); Debug/Plan/
    Orchestrator are never touched by this. If no local model is set up
    yet, it warns and falls back to that mode's plain cloud equivalent
    instead of silently no-op'ing. Verified with a scripted test against a
    deep-copied config (never the real one): promotion, fallback-chain
    ordering, idempotency (second call is a no-op), and confirmed the real
    `config.yaml` on disk was untouched by the test.

## Current status (2026-09-13, session 2)

| Area | Status |
|---|---|
| LiteLLM + Postgres containers | ✅ Up, healthy |
| 5 Kilo Code modes | ✅ All wired, all 17 model entries live-tested |
| MCP gateway | ✅ 13/16 servers healthy; 3 correctly inert pending API keys |
| Kilo Code VS Code integration | ✅ Working via global config (see "Bugs found" #10) |
| `litellm-provider-balance` extension | ✅ v0.0.2 — DeepInfra bug fixed, low-balance notifications added |
| Model auto-refresh | ✅ Preference-aware (auto/cheapest/most_accurate/custom), live-tested each mode |
| Local Ollama integration | ✅ Built, live-tested detection on this machine (found a real gap: AMD GPU missed by NVIDIA-only check, fixed) |
| 5 editors/agents beyond Kilo Code | ✅ Cline/Zed/Aider live-tested end-to-end; OpenHands researched only; 3 candidates rejected (see below) |
| Workflow dashboard | ✅ Built, live-tested all 5 routes including the real POST/apply path |
| Cross-platform setup script | ✅ Updated for all of the above, syntax-verified |
| Git repo | ✅ Pushed to [github.com/YOUR_USERNAME/litellm-setup](https://github.com/YOUR_USERNAME/litellm-setup) |
| Host-companion apps (Unity/Godot/Nuclear/Windows-control) | ⏳ Documented, not yet actually set up |

## Session 2 additions

- **Fixed a real DeepInfra bug**: the balance extension read `stripe_balance`/
  `limit`, which are a static auto-recharge ceiling setting that never
  changes — not a live balance. `recent` (usage in the current billing
  period) is what actually tracks spend; now computes `limit - recent`.
  Confirmed live: went from a frozen `$20.00` to a real, moving `$10.30`.
- **Low-balance notifications** added to the extension (6h cooldown per
  provider, clears once back above threshold).
- **Local Ollama integration** (`scripts/setup_ollama.py`): hardware-aware,
  opt-in, registers a zero-cost last-resort fallback for Code/Ask only.
  Caught two real bugs live: Windows' `wmic` is gone on recent builds (used
  `Get-CimInstance` instead), and NVIDIA-only GPU detection completely
  missed this machine's real AMD Radeon RX 9060 XT (added AMD detection,
  sorted by VRAM to avoid picking the integrated GPU over the dedicated one).
- **5 editors researched, 3 rejected with real evidence**: Void
  (development paused, repo archived), Continue.dev (acquired by Cursor
  June 2026, no longer maintained), Roo Code (shut down May 2026). Final
  5 — Kilo Code, Cline, Zed, Aider, OpenHands — see `editors/README.md`.
  Cline and Zed: live-tested MCP gateway connection via the `mcp-remote`
  bridge (confirmed "Connected to remote server"). Zed: caught a real bug
  where its schema requires `capabilities.images` on every model or it
  silently fails to load the *entire* settings file. Aider: live-tested
  LLM connectivity (real "pong" + token counts); confirmed (not assumed)
  it lacks MCP support after the docs page 404'd and `--help` showed no
  MCP flags — a web search claimed otherwise and was wrong.
- **Workflow dashboard** (`dashboard/app.py`, Flask, port 8877): status
  overview, balances, MCP health, log viewer, and an API-keys page that
  writes `.env` and re-runs the Cline/Zed install scripts automatically.
  Caught two real bugs live: a Windows console encoding crash in the log
  viewer (docker log output isn't valid cp1252; forced UTF-8 with
  replacement), and a `None + str` TypeError that followed from it.
- **Preference-aware model selection**: `scripts/set_preference.py` +
  `refresh_models.py` now support `auto`/`cheapest`/`most_accurate`/
  `performance`/`cheapest_from_best`/`custom`. Verified live: `most_accurate`
  genuinely picks a different (newer, not-cheapest) model than `auto` did
  for the same candidate set; `custom` verified to make zero changes.
- **Security review caught a real gap**: `editors/cline/install.py` and
  `editors/zed/install.py` wrote files containing the master key without
  restrictive permissions. Fixed with `os.chmod(path, 0o600)` (meaningful
  on POSIX; a no-op on Windows, where the per-user profile directory ACL
  already restricts access) — applied to the dashboard's `.env` write too.

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
