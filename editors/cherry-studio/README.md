# Cherry Studio + LiteLLM Setup

[Cherry Studio](https://cherry-ai.com/) is a desktop AI workspace supporting multi-model chat, autonomous agents (powered by Claude Code agent SDK), and MCP servers.

This setup connects Cherry Studio directly to your local LiteLLM proxy (`http://localhost:4000/v1`) and MCP gateway (`http://localhost:4000/mcp`).

---

## 1. Quick Install Script

To configure or re-sync Cherry Studio's database with LiteLLM:

```bash
python editors/cherry-studio/install.py
```

This updates Cherry Studio's SQLite database (`%APPDATA%\CherryStudio\Data\cherrystudio.sqlite`):
1. **Model Provider**: Adds/enables `LiteLLM` with base URL `http://localhost:4000/v1` and your Master Key.
2. **Models**: Registers `kilo-code`, `kilo-ask`, `kilo-debug`, `kilo-plan`, `kilo-orchestrator`, `gemini`, and `claude`.
3. **MCP Server**: Configures `LiteLLM` gateway at `http://localhost:4000/mcp` (StreamableHTTP/SSE transport with Bearer token).
4. **Agents**: Configures `Cherry Support` and `Cherry Assistant` to use `kilo-code` (with `bypassPermissions` enabled).

---

## 2. Manual UI Configuration

If you prefer to configure or verify settings inside Cherry Studio's UI:

### A. Add LiteLLM Provider
1. Open **Settings** (gear icon in bottom left) → **Model Providers**.
2. Click **+ Add Provider** (or select custom OpenAI-compatible provider).
3. Set:
   - **Provider Name**: `LiteLLM`
   - **API Base URL**: `http://localhost:4000/v1`
   - **API Key**: `43vKvXhwTkGQAn0EJONjcAWQ` (your `LITELLM_MASTER_KEY` in `.env`)
4. Under Models, add:
   - `kilo-code` (Coding model - DeepSeek V4 Flash with OpenRouter/Fireworks fallbacks)
   - `kilo-ask` (Q&A - Llama 3.3 70B Turbo)
   - `kilo-debug` (Debug/Reasoning - DeepSeek V4.1 Flash)
   - `kilo-plan` (Architecture - GLM-5.3 Flash)
   - `kilo-orchestrator` (Flagship - GPT-5.6-luna)
   - `gemini` (Gemini 3.8 Flash - 1M context)
   - `claude` (Claude Sonnet 5)

### B. Add LiteLLM MCP Gateway
1. In **Settings** → **MCP Servers**.
2. Click **+ Add Server**.
3. Set:
   - **Name**: `LiteLLM`
   - **Type**: `Streamable HTTP` / `SSE`
   - **Server URL**: `http://localhost:4000/mcp`
   - **Headers**:
     ```json
     {
       "Authorization": "Bearer 43vKvXhwTkGQAn0EJONjcAWQ"
     }
     ```
4. Click **Connect / Save**.

### C. Configure Agents (Autonomous Coding without "Continue" halts)
1. Go to the **Agents** tab on the left sidebar.
2. Click on **Cherry Support** (or create a custom agent).
3. In Agent Settings:
   - **Model**: Select `LiteLLM` → `kilo-code` (or `gemini`).
   - **Permission Mode**: Set to **Bypass Permissions** (or "Always Allow").
   
---

## 3. Why It Was Stopping (The "Continue" Loop Bug Explained)

### The Problem
When running an Agent in Cherry Studio, the model repeatedly output XML tags like:
```xml
<｜DSML｜tool_calls>
<｜DSML｜invoke name="Bash">
<｜DSML｜parameter name="command" string="true">cd "..." && git status</｜DSML｜parameter>
</｜DSML｜invoke>
</｜DSML｜tool_calls>
```
...and then stopped immediately. Every time you typed `Continue`, it produced another tool call tag and stopped again.

### Why It Happened
1. **Raw Model Dialect vs. Agent Protocol**: Cherry Studio's agents run on Claude Code agent SDK, which communicates using Anthropic's Messages protocol (`tools` and `tool_use` events).
2. Direct endpoints (like DeepInfra with Qwen3-Coder or raw DeepSeek) do not translate Anthropic `tools` into OpenAI function calls and back into Anthropic `tool_use` blocks. Instead, the model outputs raw text tokens `<｜DSML｜tool_calls>`.
3. Because Claude Code received text instead of a native `tool_use` event, it marked `stop_reason: "end_turn"`, assumed the assistant was done speaking, never ran the bash/read/edit tool, and yielded control back to the user.
4. When the user typed `Continue`, the exact same loop occurred.
5. In addition, if `permission_mode` is set to `acceptEdits` instead of `bypassPermissions`, the engine halts on every file edit or command execution waiting for user confirmation.

### How LiteLLM Fixes This
- **Protocol Translation**: When Cherry Studio calls LiteLLM with tools, LiteLLM translates tool schemas to the provider's function calling API, receives the function call, and maps it back into a native Anthropic `tool_use` block with `stop_reason: "tool_use"`.
- Claude Code detects `tool_use`, executes the command or file edit locally, returns the output to the model, and loops continuously until the goal is finished.
- Router timeout was also increased from 60s to 180s in `config.yaml` to ensure long agent tool generations don't prematurely time out.
