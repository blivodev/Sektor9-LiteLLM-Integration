#!/usr/bin/env python3
"""
install.py - Automatically configure Cherry Studio to use the local LiteLLM proxy, Sektor9 agents, autoRouter, and MCP gateway.
"""

import os
import sys
import json
import sqlite3
import shutil
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_PATH = REPO_ROOT / ".env"
APPDATA = os.environ.get("APPDATA")
if not APPDATA:
    print("Error: %APPDATA% environment variable not found.", file=sys.stderr)
    sys.exit(1)

DB_PATH = Path(APPDATA) / "CherryStudio" / "Data" / "cherrystudio.sqlite"

def read_master_key():
    if not ENV_PATH.exists():
        return "43vKvXhwTkGQAn0EJONjcAWQ"
    with open(ENV_PATH, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if line.startswith("LITELLM_MASTER_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return "43vKvXhwTkGQAn0EJONjcAWQ"

def main():
    if not DB_PATH.exists():
        print(f"Error: Cherry Studio database not found at {DB_PATH}.", file=sys.stderr)
        sys.exit(1)

    master_key = read_master_key()
    backup_path = DB_PATH.with_suffix(".sqlite.bak")
    print(f"Backing up database to {backup_path}...")
    shutil.copy2(DB_PATH, backup_path)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    now = int(time.time() * 1000)
    provider_id = "litellm-provider"

    print("Registering LiteLLM provider...")
    provider_row = (
        provider_id,
        None,
        "LiteLLM (Sektor9 Gateway)",
        None,
        json.dumps({"openai-chat-completions": {"baseUrl": "http://localhost:4000/v1"}}),
        "openai-chat-completions",
        json.dumps([{"id": "litellm-master-key", "key": master_key, "isEnabled": True}]),
        json.dumps({"type": "api-key"}),
        None,
        1,
        "b05",
        now,
        now
    )

    cur.execute("""
    INSERT OR REPLACE INTO user_provider 
    (provider_id, preset_provider_id, name, logo_key, endpoint_configs, default_chat_endpoint,
     api_keys, auth_config, provider_settings, is_enabled, order_key, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, provider_row)

    print("Registering Sektor9 & AutoRouter models...")
    # 👶 ELI5:
    # This list defines every model card that will show up inside Cherry Studio's
    # model selector dropdown. Each entry specifies the model's internal ID,
    # display name, and context limits (token window).
    models = [
        # Sektor9 Auto (Universal Smart Router with 3-Tier Fallbacks)
        {"model_id": "sektor9-auto", "name": "Sektor9 Auto (Universal Router & Fallbacks)", "context": 1048576, "in": 1048576, "out": 131072, "order": "a00"},
        # Sektor9 AutoRouter (Legacy Cheapest-Pick)
        {"model_id": "sektor9-autorouter", "name": "Sektor9 AutoRouter (Best & Cheapest)", "context": 1048576, "in": 1048576, "out": 131072, "order": "a01"},
        {"model_id": "autorouter", "name": "AutoRouter (LiteLLM)", "context": 1048576, "in": 1048576, "out": 131072, "order": "a02"},
        # Sektor9 Core Agents
        {"model_id": "sektor9-code", "name": "Sektor9 Code (DeepSeek V4 Flash)", "context": 1048576, "in": 1048576, "out": 131072, "order": "a03"},
        {"model_id": "sektor9-ask", "name": "Sektor9 Ask (Llama 3.3 70B Turbo)", "context": 131072, "in": 131072, "out": 131072, "order": "a04"},
        {"model_id": "sektor9-debug", "name": "Sektor9 Debug (DeepSeek V4.1 Flash)", "context": 1048576, "in": 1048576, "out": 393216, "order": "a05"},
        {"model_id": "sektor9-plan", "name": "Sektor9 Plan (GLM-5.3 Flash)", "context": 1048576, "in": 1048576, "out": 131072, "order": "a06"},
        {"model_id": "sektor9-orchestrator", "name": "Sektor9 Orchestrator (GPT-5.6-luna)", "context": 1050000, "in": 1050000, "out": 128000, "order": "a07"},
        # Specialized Agents
        {"model_id": "sektor9-review", "name": "Sektor9 Review (Code Review & Audit)", "context": 1048576, "in": 1048576, "out": 393216, "order": "a08"},
        {"model_id": "sektor9-refactor", "name": "Sektor9 Refactor (Optimization & Clean Code)", "context": 1048576, "in": 1048576, "out": 131072, "order": "a09"},
        {"model_id": "sektor9-test", "name": "Sektor9 Test (Unit & E2E Testing)", "context": 1048576, "in": 1048576, "out": 131072, "order": "a10"},
        {"model_id": "sektor9-docs", "name": "Sektor9 Docs (Documentation & Specs)", "context": 131072, "in": 131072, "out": 131072, "order": "a11"},
        {"model_id": "sektor9-sql", "name": "Sektor9 SQL (Database & Migrations)", "context": 1048576, "in": 1048576, "out": 131072, "order": "a12"},
        {"model_id": "sektor9-devops", "name": "Sektor9 DevOps (Docker & CI/CD)", "context": 1048576, "in": 1048576, "out": 131072, "order": "a13"},
        {"model_id": "sektor9-creative", "name": "Sektor9 Creative (Design & Copy)", "context": 131072, "in": 131072, "out": 131072, "order": "a14"},
        # Flagship & Fallbacks
        {"model_id": "claude", "name": "Claude Sonnet 5", "context": 1000000, "in": 1000000, "out": 128000, "order": "a15"},
        {"model_id": "gemini", "name": "Gemini 3.8 Flash", "context": 1048576, "in": 1048576, "out": 65536, "order": "a16"},
        {"model_id": "kilo-code", "name": "Kilo Code (Legacy Alias)", "context": 1048576, "in": 1048576, "out": 131072, "order": "a17"}
    ]

    for m in models:
        model_pk = f"{provider_id}::{m['model_id']}"
        cur.execute("""
        INSERT OR REPLACE INTO user_model
        (id, provider_id, model_id, preset_model_id, name, description, `group`, capabilities,
         input_modalities, output_modalities, endpoint_types, context_window, max_input_tokens,
         max_output_tokens, supports_streaming, reasoning, parameters, pricing, is_enabled,
         is_hidden, is_deprecated, order_key, notes, created_at, updated_at, input_modalities_explicit)
        VALUES (?, ?, ?, NULL, ?, NULL, 'Sektor9', '["chat","function-call","reasoning"]',
                NULL, NULL, NULL, ?, ?, ?, 1, NULL, NULL, NULL, 1, 0, 0, ?, NULL, ?, ?, 0)
        """, (model_pk, provider_id, m["model_id"], m["name"], m["context"], m["in"], m["out"], m["order"], now, now))

    print("Configuring MCP server...")
    # 👶 ELI5: Points Cherry Studio to LiteLLM's unified MCP gateway.
    # When enabled, Cherry Studio gets all 16 MCP tools automatically!
    cur.execute("""
    UPDATE mcp_server 
    SET base_url = 'http://localhost:4000/mcp',
        type = 'streamableHttp',
        headers = ?,
        is_active = 1,
        updated_at = ?
    WHERE name = 'LiteLLM'
    """, (json.dumps({"Authorization": f"Bearer {master_key}"}), now))

    print("Configuring Agents with sektor9-auto and bypassPermissions...")
    # 👶 ELI5:
    # Here we bind Cherry Studio's built-in agents to "sektor9-auto",
    # so they automatically enjoy cost routing + 3-tier fallback protection!
    auto_model_id = f"{provider_id}::sektor9-auto"
    cur.execute("""
    UPDATE agent 
    SET model = ?,
        configuration = json_set(configuration, '$.permission_mode', 'bypassPermissions'),
        updated_at = ?
    WHERE id = 'cherry-support'
    """, (auto_model_id, now))

    cur.execute("""
    UPDATE agent 
    SET model = ?,
        configuration = json_set(configuration, '$.permission_mode', 'bypassPermissions'),
        updated_at = ?
    WHERE id = '67955c22-a54d-4cb8-a261-97e9a6e62fe2'
    """, (auto_model_id, now))

    print("Setting default assistant model to Sektor9 Auto...")
    cur.execute("""
    UPDATE assistant 
    SET model_id = ?,
        updated_at = ?
    WHERE id = 'fc0c944b-3ce6-44af-8360-e8d30925da48'
    """, (auto_model_id, now))

    conn.commit()
    conn.close()
    print("[+] Cherry Studio successfully updated with Sektor9 Auto & full agent suite!")

if __name__ == "__main__":
    main()
