# Making changes yourself

Concrete recipes for the things you'll actually want to do. Read
[STATUS.md](STATUS.md)'s "Bugs found" section first if something behaves
unexpectedly — there's a good chance it's already a documented quirk.

## Restarting things

```powershell
cd D:\Projects\LiteLLM

# Just restart (config.yaml/.env changes need this to take effect)
docker compose restart litellm

# Full recreate (needed after editing Dockerfile, or if restart alone doesn't help)
docker compose up -d --force-recreate litellm

# View logs
docker logs litellm_proxy --tail 100
docker logs litellm_proxy -f   # follow live
```

## Changing which model a mode uses

Edit the relevant entry's `litellm_params.model` in `config.yaml`, e.g. to
switch Code mode's primary model:

```yaml
- model_name: kilo-code
  litellm_params:
    model: deepinfra/some-other-model   # <- change this
    api_key: os.environ/DEEPINFRA_API_KEY
```

Then `docker compose restart litellm`. Test it directly before trusting it:

```bash
curl http://127.0.0.1:4000/v1/chat/completions \
  -H "Authorization: Bearer <your LITELLM_MASTER_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"model":"kilo-code","messages":[{"role":"user","content":"say hi"}]}'
```

## Adding a new model / fallback leg

Same shape as any existing entry — add to `model_list`, and if it's a
fallback, add or extend its mode's line in `router_settings.fallbacks`:

```yaml
- model_name: kilo-code-fallback-3
  litellm_params:
    model: openrouter/some/model
    api_key: os.environ/OPENROUTER_API_KEY
```
```yaml
fallbacks:
  - { "kilo-code": ["kilo-code-fallback-1", "kilo-code-fallback-2", "kilo-code-fallback-3"] }
```

## Adding a new MCP server (runs entirely in the container)

Add an entry under `mcp_servers` in `config.yaml`:

```yaml
mcp_servers:
  my_new_server:
    transport: stdio
    command: npx        # MUST be npx or uvx -- see STATUS.md bug #4
    args: ["-y", "@some/mcp-package"]
    env:
      SOME_API_KEY: os.environ/SOME_API_KEY   # only works in env:, not args: -- bug #5
```

**Before adding it**, confirm the package is real (many AI-suggested MCP
package names don't exist — bug #8 in STATUS.md). Check it on npmjs.com or
pypi.org yourself, or ask an AI assistant to verify via a live web search,
not just "does this sound plausible."

**Rules that will save you a debugging cycle** (all found the hard way,
see STATUS.md):
- `command` must be literally `npx` or `uvx` — nothing else registers.
  If the tool you want is a compiled binary, a Python script without a
  console-script entry point, or anything else, route it through
  `/opt/npx-shim` (see the `language_server_go`/`video_audio` entries in
  `config.yaml` for the exact pattern).
- Secrets go in `env:` (where `os.environ/VAR` really does substitute),
  never in `args:` (where it's passed through literally, unresolved).
- Server names can't contain a hyphen — use underscores.
- If a Python server crashes with `ModuleNotFoundError: mcp.server.fastmcp`,
  add `"--with", "mcp<2"` to its `uvx` args.

After adding, rebuild if you touched the `Dockerfile` too
(`docker compose build litellm`), then restart, then check:

```bash
curl http://127.0.0.1:4000/v1/mcp/server/health -H "Authorization: Bearer <master key>"
curl http://127.0.0.1:4000/v1/mcp/server -H "Authorization: Bearer <master key>"
```

## Adding a host-companion MCP server (Blender, Godot, Unity, etc.)

These need their real app running on your machine, not the container. Two
patterns:

**Pattern A — container reaches out to your host** (like Blender):
```yaml
blender:
  transport: stdio
  command: uvx
  args: ["blender-mcp"]
  env:
    BLENDER_HOST: host.docker.internal   # not "localhost" -- see below
    BLENDER_PORT: "9876"
```
`host.docker.internal` is Docker's special hostname meaning "the machine
running Docker" — plain `localhost` from inside a container means the
container itself, not your PC.

**Pattern B — a process on your host, registered as remote** (like Godot):
Run the tool's own server on your machine with `--host 0.0.0.0 --port N`,
then in `config.yaml`:
```yaml
godot:
  transport: http
  url: "http://host.docker.internal:9090/mcp"
```

Either way, expect it to show "unhealthy" until you've actually got the
companion app open and its MCP feature turned on — that's expected, not a
bug.

## Updating an API key

Just edit `.env` — no restart needed for the value itself to be read fresh
next time that specific MCP server subprocess launches, but for **model**
API keys (used by every request, not just MCP), restart the container:

```powershell
notepad D:\Projects\LiteLLM\.env
docker compose restart litellm
```

## Running the model auto-refresh

```bash
python scripts/refresh_models.py --dry-run    # see what it would do, changes nothing
python scripts/refresh_models.py --restart    # actually apply + restart the container
```

It's already scheduled weekly if you said yes during setup. To
(re)schedule, change the schedule, or check it:
```powershell
# Windows
powershell -File scripts\schedule_refresh.ps1
Get-ScheduledTask -TaskName "LiteLLM Model Refresh"
```
```bash
# Linux/macOS
bash scripts/schedule_refresh.sh
crontab -l
```

Every change it makes is its own git commit — see the next section to
review or undo one.

## Reviewing / undoing changes

Everything here is tracked in git. To see recent history:
```bash
git log --oneline -20
```
To undo a specific change without losing anything else that happened
after it:
```bash
git revert <commit-id>
docker compose up -d --force-recreate litellm   # if it touched config.yaml/Dockerfile
```

## Using the dashboard

```bash
pip install -r dashboard/requirements.txt   # first time only (adds ruamel.yaml)
python dashboard/app.py     # -> http://127.0.0.1:8877
```
Always open it as `http://127.0.0.1:8877`, not `http://localhost:8877` --
see the `localhost`-vs-`127.0.0.1` note in STATUS.md's Session 4 section
if that ever seems to matter again.

Overview / Balances / MCP Servers / Logs are read-only. **API Keys**
writes `.env`, restarts the container, and re-runs `editors/cline/install.py`
+ `editors/zed/install.py` — leave a field blank to keep its current value.
**Preference** picks the model-selection mode (same 10 as
`set_preference.py`) and, for anything but "custom", applies it for real
in one click. **Custom routing** hand-assigns each mode's model (the
"custom" preference's mechanism) and can add a whole new mode/model slot.
**Models** is a searchable, live, price-annotated list of every model
your keyed providers currently expose — click "Refresh from providers" to
bypass its 5-minute cache.

## Setting up a 6th editor

Follow the pattern in `editors/`: point its model provider at
`http://127.0.0.1:4000/v1` + your master key, and its MCP client at either
`http://127.0.0.1:4000/mcp` directly (if it has a native remote/HTTP MCP
transport) or via `npx -y mcp-remote http://127.0.0.1:4000/mcp --allow-http
--header "Authorization:Bearer <master key>"` piped into a stdio MCP slot
(if it doesn't). Check its *current* maintenance status first — 3 of the
5 candidates researched for this project turned out to be
deprecated/unmaintained despite looking active at a glance.

## Adjusting model-selection preference

```bash
python scripts/set_preference.py
```
Changes whether `refresh_models.py` optimizes for cost, capability, free
tiers, or your local Ollama model — 10 modes, see `docs/ARCHITECTURE.md`
for the full table. Stored in `.model_preferences.json` (gitignored). If
you pick one of the three `local*` modes before running
`scripts/setup_ollama.py`, `refresh_models.py` will say so and use that
mode's cloud equivalent instead of doing nothing — run
`setup_ollama.py` first, then re-run `refresh_models.py`, to actually get
local routing.

## Setting up local Ollama

```bash
python scripts/setup_ollama.py --check    # see the hardware read, change nothing
python scripts/setup_ollama.py            # full setup, asks before doing anything
python scripts/setup_ollama.py --remove   # undo it
```

## Pushing your own changes

```bash
git add -A
git commit -m "describe what you changed and why"
git push
```

If you're not comfortable with git conflicts/rebasing, just ask an AI
assistant to handle a specific push for you — the whole point of keeping
this in git is that nothing here is ever truly unrecoverable.
