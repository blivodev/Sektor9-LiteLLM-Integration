# Tabby — genuinely open-source, self-hosted Copilot alternative

Unlike GitHub Copilot Chat (`editors/copilot/`), **Tabby needs no
subscription of any kind** — it's [TabbyML/tabby](https://github.com/TabbyML/tabby)
on GitHub, 32k+ stars, actively maintained (confirmed this session: a VS
Code extension release in Dec 2025, a feature release in July 2025 — not
a stale project like Void/Continue.dev/Roo Code, the 3 candidates
rejected elsewhere in `editors/README.md`). It's the real, currently-alive
answer to "open source alternative to GitHub Copilot."

**Structurally different from every other editor here**: Tabby is not
an IDE or an IDE extension by itself — it's its own self-hosted *server*
(a Docker container, in this setup) that a lightweight IDE extension
(VS Code, JetBrains, Vim/Neovim) then talks to. So the chain here is
`IDE extension -> Tabby server -> LiteLLM -> your providers`, one extra
hop compared to Cline/Zed/Copilot, which each talk to LiteLLM directly.

## What you get

- Inline "ghost text" code completion (Tabby's original core feature).
- A chat panel and an agent mode ("Pochi").
- Runs entirely on your own machine — Tabby's own server has no
  license check, no phone-home requirement, no account.

## Read this before expecting Copilot-level completions

Real inline completion is normally driven by a **FIM (fill-in-the-middle)
base model** (StarCoder2, DeepSeek-Coder-Base, CodeLlama,
Qwen2.5-Coder-Base) — trained on `<PRE>/<SUF>/<MID>`-style prompts, not
an instruct/chat model. Every model already in this project's
`config.yaml` (`kilo-code` included) was picked for agentic tool-use, not
FIM completion. Pointing Tabby's completion at `kilo-code` (the default
in the template below) will work — you'll get responses — but the
ghost-text quality likely won't match Copilot's until you either accept
that tradeoff or add a real FIM-capable model of your own (a
DeepSeek-Coder-Base/Qwen2.5-Coder-Base checkpoint from
DeepInfra/Fireworks/OpenRouter, or a local one via
`scripts/setup_ollama.py`) as its own `config.yaml` entry and point
completion at that instead. Not done automatically here — picking the
actual cheapest-capable FIM model deserves the same live-tested
treatment `refresh_models.py` gives every other model, not a guess in a
README. Tabby's **chat** panel has no such caveat — it uses the same
instruct/chat models as every other editor here and works the same way.

## Setup

```bash
python editors/tabby/setup.py
```
Writes `editors/tabby/data/config.toml` from `config.toml.template` with
your `LITELLM_MASTER_KEY` filled in (gitignored — that file now holds
your master key, same as the Cline/Zed installers' targets).

```bash
docker compose -f editors/tabby/docker-compose.yml up -d
```
Starts Tabby's own container at `http://127.0.0.1:8080`, reaching
LiteLLM via `host.docker.internal:4000` (same pattern as Blender/Ollama
elsewhere in this project). First start pulls a multi-GB image — give it
a few minutes. No GPU/local-model flags are set: both chat and
completion route through LiteLLM over HTTP, so Tabby itself never loads
a model.

Then install the IDE-side extension for whichever editor you use (search
"Tabby" in VS Code's/your IDE's extension marketplace) and point it at
`http://127.0.0.1:8080` — that part is the extension's own one-time UI
step, the same category as Cline/Kilo Code's provider setup.

## Status

Config syntax (`config.toml`'s `[model.chat.http]` /
`[model.completion.http]`, `kind = "openai/chat"` /
`"openai/completion"`) and the Docker image/run pattern were confirmed
against Tabby's real documentation this session, not guessed — and
`editors/tabby/setup.py` was actually run for real (valid TOML produced,
master key correctly substituted, file correctly gitignored). **Not**
personally pulled/started the Tabby container itself or tested a live
completion/chat round-trip — that's a genuinely heavy, multi-GB install,
same honesty line drawn for `editors/openhands/README.md`. Worth doing
before trusting this blindly.
