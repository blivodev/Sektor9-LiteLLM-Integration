# One-click setup

Reproduces this whole stack (LiteLLM + Postgres + the MCP gateway + the
provider-balance VS Code extension) on a fresh machine — Windows or Linux.

## Before you run it

This script needs the rest of the project alongside it — get the whole
`LiteLLM` folder onto the new machine first (git clone from a remote if
you've pushed one, a zip copy, cloud sync, USB drive, whatever). There's
nothing to download separately; everything it needs is already in this repo.

## Usage

**Windows** (PowerShell):
```powershell
powershell -ExecutionPolicy Bypass -File setup\setup.ps1
```

**Linux / macOS**:
```bash
chmod +x setup/setup.sh
./setup/setup.sh
```

## What it does automatically

1. Checks Docker is installed and running (offers to install it on Windows
   via winget; points you at the official install script on Linux).
2. Generates a fresh `.env` — prompts for each provider API key
   (OpenRouter, DeepInfra, Fireworks, Anthropic, Gemini) and each
   credentialed MCP server (SSH target, Meshy, Tripo3D, ElevenLabs,
   AceDataCloud), skippable if you don't have them yet. The Postgres
   password and LiteLLM master key are freshly randomly generated —
   never reused from another machine.
3. Builds the LiteLLM image (adds Node/Python/Go/ffmpeg for the MCP
   servers) and starts the stack.
4. Waits for LiteLLM to report healthy.
5. Installs the provider-balance status bar extension into VS Code, if
   the `code` CLI is on your PATH.

## What it prints instructions for instead of automating

- **Kilo Code's provider wiring** — its config isn't reliably settable by
  dropping a file in (we learned this the hard way); it's a two-minute UI
  flow the script walks you through instead.
- **Host-side companion MCP servers** (Blender, Godot, Unity, Nuclear) —
  these need their real application running on that machine, not something
  a container can substitute for. The script prints exactly what to
  install/run for whichever ones you use.
- **Desktop control** is *not* a gateway companion any more: it's a local
  per-editor "power pack" (`desktop-commander` + `windows-mcp`) installed by
  the OpenCode/OpenWork/Goose installers, so it never listens on a network
  port — see `editors/README.md`.

## Re-running it

Safe to re-run any time — it'll ask before overwriting an existing `.env`,
and `docker compose up -d` is a no-op if the stack's already running with
the same config.
