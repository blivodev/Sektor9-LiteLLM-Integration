# Architecture & Implementation

How every piece of this project fits together, and why it's built this way.

## System overview

```mermaid
flowchart TB
    subgraph Host["Your Windows machine"]
        VSCode["VS Code<br/>+ Kilo Code extension<br/>+ litellm-provider-balance extension"]
        Docker["Docker Desktop"]
        HostApps["Host-only apps (optional)<br/>Blender / Godot / Unity / Nuclear /<br/>Windows-MCP desktop control"]
        RefreshScript["scripts/refresh_models.py<br/>(runs on a schedule, host-side)"]
    end

    subgraph Container["litellm_proxy container"]
        LiteLLM["LiteLLM Proxy<br/>:4000"]
        MCPGateway["MCP Gateway<br/>16 registered servers"]
    end

    subgraph DBContainer["litellm_db container"]
        Postgres["Postgres 18<br/>:5432"]
    end

    subgraph Cloud["Model providers"]
        OR["OpenRouter"]
        DI["DeepInfra"]
        FW["Fireworks AI"]
        AN["Anthropic (optional)"]
        GE["Gemini (optional)"]
    end

    VSCode -- "OpenAI-compatible API<br/>+ master key" --> LiteLLM
    VSCode -- "MCP protocol" --> MCPGateway
    LiteLLM -- "spend/key data" --> Postgres
    LiteLLM -- "model_list routing +<br/>cross-provider fallback" --> OR & DI & FW & AN & GE
    MCPGateway -. "host.docker.internal<br/>(stdio bridges)" .-> HostApps
    RefreshScript -- "git commit +<br/>docker compose restart" --> Container
    RefreshScript -- "poll catalogs/pricing" --> OR & DI & FW & AN & GE
    Docker -.->|runs| Container
    Docker -.->|runs| DBContainer
```

## Why LiteLLM as the hub

Instead of each tool (Kilo Code, other IDEs, agents) holding its own copy of
every provider API key and its own retry/fallback logic, everything points
at one local LiteLLM proxy. LiteLLM then:

- Picks the actual model per request based on `model_list` in
  [`config.yaml`](../config.yaml).
- Retries across providers automatically on error (`router_settings.fallbacks`).
- Tracks spend/keys in Postgres.
- Doubles as an **MCP gateway** — one place to register MCP servers so any
  connected client gets all of them, instead of configuring each server in
  every tool separately.

## The 5 Kilo Code modes, and why each model was picked

| Mode | Primary | Why | Fallback chain |
|---|---|---|---|
| **Code** | DeepInfra `DeepSeek-V4-Flash-0731` | Highest call volume — cheapest model still strong at coding/agentic tool-use | → OpenRouter (same model) → Fireworks (same model) |
| **Ask** | DeepInfra `Llama-3.3-70B-Turbo` | Already the best price/capability pick for general Q&A | → OpenRouter → Fireworks (same model) |
| **Debug** | DeepInfra `DeepSeek-V4.1-Flash` | Debugging benefits from the pricier reasoning checkpoint over raw Code mode | → OpenRouter → Fireworks (same model) |
| **Plan** | Fireworks `GLM-5.3-Flash` | Confirmed cheapest real price for a capable planning model | → OpenRouter → DeepInfra (same family) |
| **Orchestrator** | OpenRouter `GPT-5.6-Luna` | Lowest volume, but mistakes cascade to every sub-agent — kept on the strongest model rather than optimized for cost | → Fireworks `Kimi-K3` → DeepInfra `Kimi-K3` |

Two extra models, `claude` and `gemini`, are configured but deliberately
**not** in any mode or fallback chain — manual escape hatches for when you
specifically want them, not part of the automatic coding pipeline.

Every fallback chain spans a **different provider per hop** on purpose: a
DeepInfra outage doesn't take down Code mode, because the fallback runs on
OpenRouter or Fireworks instead.

## The MCP gateway

`mcp_servers` in `config.yaml` registers 16 servers behind one endpoint.
Three categories:

1. **Fully containerized, no external app needed** — filesystem, memory,
   sequential-thinking, fetch, Playwright, OpenStreetMap, DBHub,
   Postgres-Pro, SSH, the LSP bridge, the ffmpeg audio/video tool, Tripo3D.
2. **Containerized but need your own API key** — Meshy (3D gen),
   ElevenLabs (voice), Suno via AceDataCloud (music) — sit inert until you
   add a key to `.env`.
3. **Host-companion** — Blender, Godot, Unity, Nuclear, Windows desktop
   control. These need their real application running on your machine;
   the container either reaches out to it (`host.docker.internal`) or a
   host-side process is registered as a remote MCP server. See
   [MAINTENANCE.md](MAINTENANCE.md) for exact setup per app.

## The Docker image

`Dockerfile` extends the official `ghcr.io/berriai/litellm` image (a
minimal "Wolfi" Linux with Node and Python but no package managers) with:
`npm`, `pip`, `uv`/`uvx`, `ffmpeg`, `git`, `go` (used to compile
`mcp-language-server` and `gopls` at build time), and a tiny local
`npx-shim` package (see "Bugs found" in [STATUS.md](STATUS.md) for why that
shim exists).

## Model auto-refresh

`scripts/refresh_models.py` runs on the host (not in the container, since
it needs `git` and `docker compose`) on a weekly schedule. See
[STATUS.md](STATUS.md) for its design and [MAINTENANCE.md](MAINTENANCE.md)
for running/scheduling it yourself.

```mermaid
flowchart LR
    A[Fetch LiteLLM's price map<br/>+ live provider catalogs] --> B{Same-family model,<br/>version >= current,<br/>context >= current?}
    B -- no --> Z[Skip, log nothing to apply]
    B -- yes --> C[Sort candidates by price<br/>ascending, version as tiebreak]
    C --> D[Live-test the cheapest one<br/>via the provider's real API]
    D -- fails --> Z
    D -- succeeds --> E[Promote to primary,<br/>demote old model to first fallback]
    E --> F[git commit + optional<br/>container restart]
```

## Repository layout

```
.
├── config.yaml              # LiteLLM: models, fallbacks, MCP servers
├── docker-compose.yaml      # Postgres + LiteLLM containers
├── Dockerfile               # Extends LiteLLM's image with MCP runtimes
├── kilo.jsonc / kilo.json   # Kilo Code project config (see STATUS.md re: what actually works)
├── .env                     # All secrets (gitignored)
├── scripts/
│   ├── refresh_models.py    # Model auto-refresh
│   ├── schedule_refresh.*   # Registers the weekly schedule
│   └── requirements.txt
├── setup/
│   ├── setup.ps1 / setup.sh # One-click reproduction on a new machine
│   └── README.md
├── vscode-extension/
│   └── litellm-provider-balance/  # Status bar credit/balance indicator
└── docs/                    # You are here
```
