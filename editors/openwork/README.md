# OpenWork

[OpenWork](https://github.com/different-ai/openwork) — the open-source
alternative to Claude Cowork: a desktop app for running agent workflows,
**powered by OpenCode**. Installed on this machine, so this was checked
against the real app, not just docs.

## How it actually works (why this is configured the way it is)

OpenWork embeds an OpenCode engine per *workspace* (a folder). It layers its
own generated runtime config (`%APPDATA%\openwork\runtime-opencode-config.json`
— don't edit that, the app regenerates it), then the workspace's
`opencode.jsonc`. So the right place to point it at LiteLLM is the
**workspace file**, which is also OpenWork's documented mechanism.

## Setup

```bash
python editors/openwork/install.py
```

Finds your OpenWork workspaces from its server state (Windows; pass
`--workspace DIR` for others) and writes the LiteLLM provider, the gateway
MCP server, the [power pack](../README.md#the-power-pack-closer-to-claude-desktop--code)
and a default model (`litellm/sektor9-autorouter`) into each workspace's
`opencode.jsonc` (backed up first). It deliberately does **not** rebind
agents — OpenWork ships its own `openwork` agent — and does not touch the
global OpenCode config (run `editors/opencode/install.py` for that).

**Restart the workspace/app afterwards**, and make sure OpenWork is started
*after* `LITELLM_API_KEY` exists in your environment (the config uses
`{env:LITELLM_API_KEY}`, so no key sits in the file): open OpenWork from a
new login/terminal the first time.

## Verified live

With the global OpenCode config *hidden* (`XDG_CONFIG_HOME` pointed at an
empty folder) and OpenWork's real runtime config layered in, a workspace
file written by this installer alone was enough for the embedded engine to:

- see the provider and connect `litellm-gateway`, `desktop-commander` and
  `windows-mcp` (3× connected), and
- answer as `openwork · kilo-code` (`pong`).

Not verified: clicking through the OpenWork GUI itself — driving another
app's UI headlessly wasn't possible here. The engine layer it delegates to
was tested with the app's own runtime config.

## Note for a "Cowork"-style app

The power pack gives an agent real desktop control and machine-wide file
access. That's the point (and what you asked for), but read the
[security note](../README.md#security-what-the-power-pack-can-do) once.
`--no-power` gives you OpenWork with just LiteLLM + the gateway.
