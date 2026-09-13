# OpenHands

[OpenHands](https://github.com/All-Hands-AI/OpenHands) — open source,
actively developed (shipped releases mid-August 2026), focused on
autonomous multi-step workflows (browsing, editing, testing, retrying),
not just inline suggestions. Runs as its own service (normally via
Docker) with a web UI, rather than living inside an existing editor.

⚠️ **Honesty note**: unlike Cline, Zed, and Aider above (all live-tested
end-to-end this session), this one is documented from research, not
personally verified against a running instance — it's the heaviest of
the 5 to install. Treat [`config.toml.template`](config.toml.template) as
a strong starting point, not a guarantee.

## Install (typical path)

```bash
docker pull docker.all-hands.dev/all-hands-ai/openhands:latest
```
Follow [OpenHands' own quickstart](https://docs.openhands.dev/) for the
full run command — it needs a workspace volume mount and a few flags
beyond what's relevant here.

## Configuration

Copy [`config.toml.template`](config.toml.template) into your OpenHands
working directory as `config.toml`, fill in your `LITELLM_MASTER_KEY`
twice (LLM section + MCP section). Per OpenHands' docs, its `[mcp]`
config supports SHTTP (Streamable HTTP) servers **natively** — pointing
straight at `http://localhost:4000/mcp` with an `api_key`, no
`mcp-remote` bridge needed (unlike Cline/Zed, which lack a native remote
MCP transport).
