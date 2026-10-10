# Sektor9 LiteLLM Integration

A unified local LiteLLM proxy and gateway (backed by Postgres) powering Sektor9 coding agents, editors, and tools. Each Sektor9 mode maps to its own specialized agent, supported by an intelligent **AutoRouter** (best & cheapest dynamic model routing), an automated 2-deep fallback chain across OpenRouter, DeepInfra, and Fireworks AI, Repomix codebase packaging, and a 16-server MCP gateway.

**New here, or just want the full picture?** See [`docs/`](docs/) —
a plain-language user guide, the architecture in detail, every bug found
and fixed along the way, and how-to recipes for changing things yourself.

All 5 provider keys (OpenRouter, DeepInfra, Fireworks, Anthropic, Gemini)
are filled in and tested working.

## What's new in Sektor9 LiteLLM Integration

- **Sektor9 Agent Suite & AutoRouter** — Specialized agents for every workflow:
  - `sektor9-autorouter` (or `autorouter`): dynamically routes requests to the lowest-cost, highest-performance model available across all providers with live cost-based load balancing.
  - `sektor9-code`: Fast, cost-efficient implementation agent (DeepSeek V4 Flash).
  - `sektor9-ask`: Architecture queries and documentation (Llama 3.3 70B Turbo).
  - `sektor9-debug`: Root-cause diagnosis and stack traces (DeepSeek V4.1 Flash).
  - `sektor9-plan`: Step-by-step breakdown and system design (GLM-5.3 Flash).
  - `sektor9-orchestrator`: Multi-agent coordination and high-level strategy (GPT-5.6).
  - Specialized agents: `sektor9-review`, `sektor9-refactor`, `sektor9-test`, `sektor9-docs`, `sektor9-sql`, `sektor9-devops`, `sektor9-creative`.
  - Full backward compatibility for `kilo-*` legacy model aliases.
- **[Repomix](docs/repomix.md) Codebase Packaging** — Pack entire repositories into token-efficient XML or Markdown context files for LLM agents using `scripts/repomix_pack.py` and `scripts/repomix_pack.ps1`.
- **Cherry Studio Native Integration** — One-click configuration script (`editors/cherry-studio/install.py`) registering all Sektor9 models, AutoRouter, and LiteLLM MCP gateway directly into Cherry Studio, configured with `bypassPermissions` for uninterrupted agent execution.
- **11+ Supported Editors & Agents** — Kilo Code, Cherry Studio, Cline, Zed, Aider, OpenHands, Tabby, Hermes Agent, OpenCode, OpenWork, Goose, and GitHub Copilot Chat.
- **[`dashboard/app.py`](dashboard/app.py)** — Web dashboard at http://127.0.0.1:8877 for container health, provider balances, logs, live preferences, and model catalogs.

- **[`dashboard/app.py`](dashboard/app.py)** — one page for everything:
  container/MCP health, provider balances, a unified log viewer, an
  API-keys page that writes `.env` and re-propagates to every configured
  editor automatically, plus **Preference** (change the model-selection
  mode and apply it live), **Custom Routing** (hand-pick each mode's
  model), and **Models** (a searchable, live, price-annotated catalog).
  Starts automatically now alongside the containers (`scripts/start-litellm.ps1`,
  already run on VS Code folder open) — http://127.0.0.1:8877 any time.
  Live-tested end to end, including bugs found and fixed along the way —
  see `docs/STATUS.md`.
- **[`editors/`](editors/)** — 10 editors/agents beyond Kilo Code+VS Code,
  all pointed at this same proxy+gateway: Cline, Zed, Aider, OpenHands,
  Tabby, Hermes Agent, OpenCode, OpenWork, Goose. OpenCode/OpenWork/Goose
  also get a "power pack" (desktop control + whole-machine file access) that
  brings them closer to Claude Desktop/Code. 3 other strong-looking candidates (Void,
  Continue.dev, Roo Code) were checked and rejected as no longer
  maintained — see
  `editors/README.md`. GitHub Copilot Chat is also there as a
  subscription-gated bonus, for anyone who already pays for Copilot.
- **[`scripts/setup_ollama.py`](scripts/setup_ollama.py)** — optional,
  hardware-aware local model via Ollama, registered as a zero-cost
  last-resort fallback for Code/Ask modes only if it's actually worth it
  on your hardware.
- **[`scripts/set_preference.py`](scripts/set_preference.py)** — tells
  `refresh_models.py` whether to optimize for cheapest, most-accurate, or
  a blend of both.

## Setting this up on another machine

See [`setup/README.md`](setup/README.md) — one script (`setup/setup.ps1` on
Windows, `setup/setup.sh` on Linux/macOS) reproduces the whole stack: prompts
for your provider keys, builds and starts the containers, installs the VS
Code extension, and walks you through the couple of things that genuinely
can't be automated (Kilo Code's provider wiring, host-side companion MCP
servers like Blender/Godot/Unity).

## MCP gateway

This LiteLLM instance also acts as a centralized MCP server gateway — see
`mcp_servers` in [`config.yaml`](config.yaml). 16 servers are registered
(databases, filesystem, browser automation, 3D/audio AI generation, SSH,
and more); most are healthy and tested, a few are intentionally inert until
you add their credentials to `.env`, and a couple (Blender, Godot, Unity,
Nuclear) need their real application running on
your machine rather than in the container — see `setup/README.md` for those.

## Model auto-refresh

[`scripts/refresh_models.py`](scripts/refresh_models.py) periodically checks
whether your configured providers now offer a cheaper/newer model in the
same family as one you're already running, and if so, upgrades it — so you
don't have to manually revisit `config.yaml` every time a provider ships a
new checkpoint. It's built to never silently break anything:

- Every candidate is **live-tested** (a real request through the provider's
  own API) before `config.yaml` is touched at all.
- The **old model is kept**, demoted to be the new first fallback for that
  slot — if the "upgrade" is worse in practice, the proxy just falls back.
- Every applied change is its **own git commit** with the price/context
  comparison in the message.
- A summary is appended to `MODEL_REFRESH_LOG.md` on every run, whether or
  not anything changed.
- Picks the **cheapest** model that's at least as new a version and at
  least as large a context window as what's running — not the newest one
  that happens to be no pricier. Recency only breaks ties on equal price.

Real pricing/context comes primarily from
[LiteLLM's own community-maintained price map](https://github.com/BerriAI/litellm/blob/main/model_prices_and_context_window.json)
(covers every provider, including DeepInfra and Fireworks, whose own APIs
don't expose per-model pricing at all) — live provider catalogs are only
used to know what currently exists, since that map can lag a few days
behind a brand-new release. It's still heuristic (price + context length +
version number — no provider exposes a real "quality" score), which is
exactly why the safety net above exists.

```bash
python scripts/refresh_models.py --dry-run   # see candidates, change nothing
python scripts/refresh_models.py --restart   # apply validated upgrades + restart the container
```

`setup/setup.ps1` / `setup/setup.sh` offer to schedule this weekly for you
(Windows Task Scheduler / cron) — see `scripts/schedule_refresh.ps1`/`.sh`
to set that up later if you skipped it.

After editing `.env`, restart the stack so the container picks it up:

```bash
docker compose restart litellm
```

## What's in this repo

| File | Purpose |
|---|---|
| [`docker-compose.yaml`](docker-compose.yaml) | Postgres 18 + the LiteLLM proxy container |
| [`config.yaml`](config.yaml) | LiteLLM's model list, per-mode fallback chains, DB/master-key config |
| [`.env`](.env) | All secrets (git-ignored) — DB creds, LiteLLM master key, provider API keys |
| [`kilo.jsonc`](kilo.jsonc) | Points Kilo Code's 5 agent modes at the LiteLLM proxy |
| [`.vscode/tasks.json`](.vscode/tasks.json) | Auto-starts the stack when you open this folder in VS Code |
| [`scripts/start-litellm.ps1`](scripts/start-litellm.ps1) | The script that task runs: starts Docker Desktop if needed, `docker compose up -d`, waits for LiteLLM to be live |
| [`.vscode/extensions.json`](.vscode/extensions.json) | Recommends the Kilo Code extension |
| [`vscode-extension/litellm-provider-balance/`](vscode-extension/litellm-provider-balance/) | A small local (unpublished) VS Code extension: status bar credit/balance indicator for all 5 providers |

## Escape-hatch models: Claude & Gemini

Two extra entries, `claude` (`anthropic/claude-sonnet-5`) and `gemini`
(`gemini/gemini-3.8-flash`), are configured but deliberately **not** wired
into any of the 5 modes or their fallback chains — you use OpenRouter/
DeepInfra/Fireworks for coding, and can manually pick `claude` or `gemini`
in Kilo Code whenever you specifically want one of them. Two open items:

- **Anthropic**: the key is genuine and authenticates, but the account has
  **insufficient credit** ("Your credit balance is too low"). A Claude
  subscription doesn't include API credit — add some at
  [console.anthropic.com/settings/billing](https://console.anthropic.com/settings/billing)
  before `claude` will actually respond.
- **Gemini**: works right now, but LiteLLM routed it through **Vertex AI**
  based on the key's shape (`AQ.…`, which looks like a Google OAuth access
  token, not a stable AI Studio key like `AIzaSy…`). OAuth access tokens
  typically expire in about an hour — if `gemini` suddenly starts failing,
  that's almost certainly why; you'd want a proper AI Studio API key instead.

## Model routing

**`routing_strategy: cost-based-routing`** — for each mode, the same model is
deployed on multiple providers with explicit `input_cost_per_token` /
`output_cost_per_token`. LiteLLM automatically routes to the **cheapest healthy
provider** for that model, with failover to the next-cheapest on error (verified
live: with OpenRouter budget-capped and Fireworks suspended, `sektor9-code`
routes to DeepInfra).

Current per-model pricing (per 1M tokens, input/output):

| Mode | Model | DeepInfra | OpenRouter | Fireworks |
|---|---|---|---|---|
| **Code / Debug / Review / Refactor** | DeepSeek V4.1 Flash | $0.30/$1.20 (picked) | $0.30/$1.20 | $0.30/$1.20 |
| **Test / SQL** | DeepSeek V4 Flash 0731 | $0.08/$0.18 (picked) | $0.0175/$1.28 | $0.22/$0.66 |
| **Ask / Docs / DevOps** | Llama-3.3-70B | $0.10/$0.32 (picked) | $0.22/$0.50 | — |
| **Plan** | GLM-5.3 Flash | (full GLM-5.3 fb) | $0.15/$0.50 | $0.15/$0.50 |
| **Orchestrator** | GPT-5.6 Luna / Kimi | Kimi-K3 (fb2) | GPT-5.6 (primary) | kimi-k3 (fb1) |
| **Creative** | GPT-5.6 Luna / Llama | Llama-3.3 (fb) | GPT-5.6 (primary) | — |

OpenRouter is **not** forced to be last — the router picks whichever provider is
genuinely cheapest for that model. Where OpenRouter is tied (DeepSeek V4.1) or
pricier (Llama-3.3), it is naturally deprioritized; where it's the only option
(GPT-5.6, GLM-5.3 via z-ai), it is primary. Every chain still spans 2-3
different providers so no single one is a single point of failure.

**Kilo aliases were removed** — the gateway is Sektor9-only now.

## Verifying it works

```bash
curl http://127.0.0.1:4000/health/liveliness
```

Call any mode directly (swap `kilo-code` for `kilo-ask` / `kilo-debug` /
`kilo-plan` / `kilo-orchestrator`, or any of the `*-fallback-1` / `*-fallback-2`
names from `config.yaml` to test a specific fallback leg):

```bash
curl http://127.0.0.1:4000/v1/chat/completions \
  -H "Authorization: Bearer $(grep LITELLM_MASTER_KEY .env | cut -d= -f2)" \
  -H "Content-Type: application/json" \
  -d '{"model":"kilo-code","messages":[{"role":"user","content":"say hi"}]}'
```

## Kilo Code setup

`kilo.jsonc` in the project root is kept as a reference, but in practice
**this didn't get picked up automatically** by the installed Kilo Code
version — configure it once through the UI instead (this is what actually
worked):

1. Gear icon → **Providers** → **Custom provider** → **+ Connect**
   - Base URL: `http://127.0.0.1:4000/v1`
   - API key: your `LITELLM_MASTER_KEY` from `.env`
   - It should auto-discover all the `kilo-*` models — select at least the
     5 primaries.
2. Gear icon → **Models** → **"Model per Mode"** → set Code/Ask/Debug/Plan/
   Orchestrator to their matching `kilo-*` model.

This writes to Kilo's **global** config (`~/.config/kilo/kilo.jsonc` on
Windows: `%USERPROFILE%\.config\kilo\kilo.jsonc`), not this project's file.

## Auto-start on VS Code open

`.vscode/tasks.json` defines a `runOn: folderOpen` task that runs
`scripts/start-litellm.ps1`, which:
1. Checks `docker info`; if the engine isn't responding, launches Docker
   Desktop and waits (up to ~2 min) for it to come up.
2. Runs `docker compose up -d` (no-op if containers are already running).
3. Polls `/health/liveliness` until LiteLLM responds.

**First time you open this folder**, VS Code will prompt *"This workspace
wants to run a task automatically"* — allow it, or the stack won't
auto-start (this is a VS Code security prompt, not something we can or
should bypass). It only asks once per workspace.

## Provider balance status bar

[`vscode-extension/litellm-provider-balance/`](vscode-extension/litellm-provider-balance/)
(v0.0.2, installed as a real `.vsix` via `code --install-extension`) shows
a status bar segment per provider, colored 🟢/🟡/🔴 by how much of its
budget is left, plus a low-balance warning popup (once per provider per
6h, cleared once you're back above the threshold). OpenRouter and
DeepInfra are fully automatic (real balance APIs on both sides — DeepInfra's
"never updates" bug is fixed, see `docs/STATUS.md`); the rest need
one-time manual setup via the status bar item's click menu:

- **Fireworks**: click → "Configure Fireworks tracking" → account ID
  **`YOUR_USERNAME`** (already confirmed against their API), then enter whatever
  $ you've currently topped up (check your Fireworks billing dashboard —
  the account was just created today, so this is likely close to $0 or a
  small free-trial amount). Spend going forward is tracked automatically.
- **Anthropic / Gemini**: fully manual — no usage API for a normal key.
  Click → "Update \[Anthropic/Gemini\] budget & spent-so-far" and type in
  whatever you see on their console periodically. See the extension's own
  [README](vscode-extension/litellm-provider-balance/README.md) for details.

## Notes on secrets

Everything sensitive (DB password, LiteLLM master key, provider API keys)
lives in `.env`, which is git-ignored. `config.yaml` and `docker-compose.yaml`
reference it via `os.environ/VAR_NAME` / `env_file`, so nothing is duplicated
in plaintext across files anymore. `kilo.jsonc` still has the master key
literal, since Kilo Code runs on the host (not in a container) and can't read
`.env` — if you later put this folder under version control, either add
`kilo.jsonc` to `.gitignore` too or switch its `apiKey` to Kilo's `{env:VAR}`
syntax backed by a machine-level environment variable.
