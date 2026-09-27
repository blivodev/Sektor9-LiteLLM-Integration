"""
test_sektor9_auto.py - Verifies that the Sektor9 Auto router and models are registered and functioning.
ELI5: A quick tester script that pings LiteLLM and asks Sektor9 Auto to say hello.
"""
import urllib.request
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"

def load_master_key():
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    for l in lines:
        if l.startswith("LITELLM_MASTER_KEY="):
            return l.split("=", 1)[1].strip().strip('"').strip("'")
    raise ValueError("LITELLM_MASTER_KEY not found in .env")

def main():
    key = load_master_key()
    print("[1] Querying /v1/models...")
    req = urllib.request.Request("http://127.0.0.1:4000/v1/models", headers={"Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=10) as r:
        models_data = json.load(r)["data"]
    
    ids = [m["id"] for m in models_data]
    print(f"    Total models registered: {len(ids)}")
    assert "sektor9-auto" in ids, "sektor9-auto NOT in model list!"
    assert "sektor9-auto-fallback-provider" in ids, "sektor9-auto-fallback-provider NOT in model list!"
    assert "sektor9-auto-fallback-model" in ids, "sektor9-auto-fallback-model NOT in model list!"
    assert "sektor9-auto-fallback-hybrid" in ids, "sektor9-auto-fallback-hybrid NOT in model list!"
    print("    [+] Sektor9 Auto and all 3 Fallback tiers are present in LiteLLM!")

    print("[2] Testing chat completion via Sektor9 Auto...")
    req_body = json.dumps({
        "model": "sektor9-auto",
        "messages": [{"role": "user", "content": "Respond with the word 'SEKTOR9_ONLINE' only."}],
        "max_tokens": 15
    }).encode("utf-8")

    chat_req = urllib.request.Request(
        "http://127.0.0.1:4000/v1/chat/completions",
        data=req_body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    )
    with urllib.request.urlopen(chat_req, timeout=30) as r:
        res = json.load(r)
    
    msg = res["choices"][0]["message"]
    content = msg.get("content") or msg.get("reasoning_content") or str(msg)
    model_used = res.get("model", "unknown")
    print(f"    [+] Response received from model '{model_used}': {content}")
    print("\n>>> ALL TESTS PASSED! Sektor9 Auto router is operational! <<<")

if __name__ == "__main__":
    main()
