# Aider (terminal)

[Aider](https://github.com/Aider-AI/aider) — open source, actively
developed (25k+ GitHub stars), terminal-based rather than an IDE. Pairs
with whatever editor you already use; you drive it from a terminal (VS
Code's integrated terminal works fine).

## Install

```bash
pip install aider-install
aider-install
```
(Installs the `aider` executable to `~/.local/bin` — make sure that's on
your PATH, the installer will tell you if it isn't.)

## Model connectivity — verified working

Aider is built on LiteLLM's own Python SDK internally, so our proxy is
just "another LiteLLM-compatible endpoint" to it. Copy
[`aider.conf.yml.template`](aider.conf.yml.template) to `~/.aider.conf.yml`,
fill in your real `LITELLM_MASTER_KEY`, and every model in `config.yaml` is
available as `openai/<model-name>` (e.g. `openai/kilo-code`).

**Live-tested**: got a real `pong` response with real token counts back
through the proxy using this exact config, both via environment variables
and via the config file.

## MCP — not supported (confirmed, not assumed)

Unlike the other 4 editors here, **Aider does not have native MCP client
support** — checked directly (`aider --help` has no MCP flags, and
`aider.chat/docs/config/mcp.html` 404s), not just taken from a
docs page. Open GitHub issues requesting it
([#2525](https://github.com/Aider-AI/aider/issues/2525),
[#3314](https://github.com/Aider-AI/aider/issues/3314)) are still open.
Third-party wrapper projects exist that expose *Aider itself* as an MCP
server (the reverse direction — letting Claude/other MCP clients drive
Aider), which isn't what we want here. If this changes in a future
release, revisit this file.
