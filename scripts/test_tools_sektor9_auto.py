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

def test_tool_calling(model_name):
    key = load_master_key()
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get current temperature for a city",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string"}
                    },
                    "required": ["city"]
                }
            }
        }
    ]
    req_body = json.dumps({
        "model": model_name,
        "messages": [
            {"role": "user", "content": "What is the weather in Tokyo? Call the get_weather function."}
        ],
        "tools": tools,
        "tool_choice": "auto",
        "max_tokens": 100
    }).encode("utf-8")

    req = urllib.request.Request(
        "http://127.0.0.1:4000/v1/chat/completions",
        data=req_body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            res = json.load(r)
            choice = res["choices"][0]
            print(f"[{model_name}] finish_reason: {choice.get('finish_reason')}")
            print(f"[{model_name}] message: {choice.get('message')}")
            return choice
    except Exception as e:
        print(f"[{model_name}] ERROR: {e}")
        return None

if __name__ == "__main__":
    print("Testing sektor9-auto:")
    test_tool_calling("sektor9-auto")
    print("\nTesting autorouter (which was working yesterday):")
    test_tool_calling("autorouter")
