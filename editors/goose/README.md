# Goose

[Goose](https://github.com/aaif-goose/goose) (formerly `block/goose`) —
open-source local agent with a CLI and a desktop app. **Fully live-verified**
with a real goose 1.51.0 (config sandboxed via `GOOSE_PATH_ROOT` while
testing, then applied to your real config).

## Setup

```bash
python editors/goose/install.py
```

Close any open `goose configure` first (the installer refuses to run
while one is open — it rewrites `config.yaml` when it finishes and would
undo this; `--force` overrides). Goose Desktop should be **restarted**
afterwards so it re-reads the config and the environment.

| | |
|---|---|
| **Provider** | `<config>/custom_providers/litellm.json`, engine `openai`, `base_url` `http://127.0.0.1:4000/v1/chat/completions` (Goose wants the *full* path), key from `LITELLM_API_KEY`. Models discovered live from the proxy. |
| **Defaults** | `GOOSE_PROVIDER: litellm`, `GOOSE_MODEL: kilo-code` **and**, if your config uses Goose's newer scheme, `active_provider: litellm` + `providers.litellm` (skip all switching with `--no-rebind`; it prints what it replaced) |
| **Extension `litellm-gateway`** | The 16-server MCP gateway, via the `mcp-remote` stdio bridge (see below). |
| **Power pack** | `desktop-commander` + `windows-mcp` extensions, and Goose's own built-in **`computercontroller`** turned on (it ships disabled). See [the power pack](../README.md#the-power-pack-closer-to-claude-desktop--code). Skip with `--no-power`. |

Config lives at `%APPDATA%\Block\goose\config\` on Windows (asked from
`goose info`, not hardcoded). Existing content is preserved: `config.yaml`
is edited with `ruamel.yaml`, and a one-time `config.yaml.bak-<timestamp>`
is written the first time. Verified against a copy of your real config: all
your original extensions kept, `developer` untouched.

## Why the gateway goes through `mcp-remote`

Goose's native `streamable_http` extension **did not send an
`Authorization` header** in testing — the gateway answered
`authentication_required` and Goose reported *"failed to initialize MCP
client"*. The gateway itself accepts the header fine (checked with curl), so
this uses the same `mcp-remote` stdio bridge Cline and Zed use. The trade-off
is that Goose's `config.yaml` then contains the master key (in the
extension's `envs`) — it lives in your user profile, not this repo. Trying
to inherit the key from the environment instead hung (an unauthenticated
`mcp-remote` waits on an OAuth flow), so that isn't used.

## Gotcha: `active_provider` beats `GOOSE_PROVIDER`

Goose 1.51's `goose configure` writes a **newer selection scheme** —
`active_provider: <name>` plus a `providers:` block — and that takes
precedence over the older `GOOSE_PROVIDER`/`GOOSE_MODEL` keys. The first
version of this installer only set the old keys: it passed every test on a
fresh config, but on your real config (which had `active_provider:
openrouter`) Goose kept talking **straight to OpenRouter, bypassing
LiteLLM**, while looking configured. It was caught only because the session
banner printed `openrouter deepseek/deepseek-v4-flash` instead of `litellm
kilo-code`. The installer now sets both schemes and prints the provider it
replaced (`openrouter (deepseek/deepseek-v4-flash) -> litellm (kilo-code)`);
your `openrouter` entry stays in `providers:` so you can switch back with
`goose configure`.

**Always check the banner** after `goose run` / opening a session: it should
say `litellm kilo-code`. A Goose Desktop that was open while this ran may
rewrite the file from memory — restart it after installing.

## Verify

```bash
goose doctor
goose run --no-session -t "say pong"
goose run --no-session -t "Use the memory read_graph tool once and say what it returned."
goose run --no-session -t "Use the desktop-commander list_directory tool on C:\\Users\\<you> and list the names."
```

Verified this session: a real chat (`litellm kilo-code` → `pong`), a real
gateway tool call (`memory-read_graph` → empty graph), and a real
whole-machine file listing through `desktop-commander`. The first run after
install can take ~20s while `npx`/`uvx` fetch the packages; Goose starts
every extension at session start.
