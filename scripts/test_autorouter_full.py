import urllib.request
import json
from pathlib import Path

lines = Path('.env').read_text().splitlines()
key = [l.split('=', 1)[1].strip('\"\' ') for l in lines if l.startswith('LITELLM_MASTER_KEY=')][0]

def test_chat():
    print("--- 1. Testing Chat Completion for sektor9-autorouter ---")
    body = {
        "model": "sektor9-autorouter",
        "messages": [{"role": "user", "content": "What is 2+2? Answer with just the number."}],
        "max_tokens": 50
    }
    req = urllib.request.Request(
        "http://127.0.0.1:4000/v1/chat/completions",
        data=json.dumps(body).encode('utf-8'),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            res = json.load(r)
            print("Status: 200")
            print("Response model:", res.get("model"))
            choice = res["choices"][0]
            print("Choice message:", choice["message"])
    except Exception as e:
        print("Error:", e)

def test_stream():
    print("\n--- 2. Testing Streaming Chat for sektor9-autorouter ---")
    body = {
        "model": "sektor9-autorouter",
        "messages": [{"role": "user", "content": "Count from 1 to 5."}],
        "max_tokens": 100,
        "stream": True
    }
    req = urllib.request.Request(
        "http://127.0.0.1:4000/v1/chat/completions",
        data=json.dumps(body).encode('utf-8'),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            content_chunks = []
            reasoning_chunks = []
            for line in r:
                line_str = line.decode('utf-8').strip()
                if line_str.startswith('data: ') and line_str != 'data: [DONE]':
                    d = json.loads(line_str[6:])
                    delta = d['choices'][0].get('delta', {})
                    if delta.get('content'):
                        content_chunks.append(delta['content'])
                    if delta.get('reasoning_content') or delta.get('reasoning'):
                        reasoning_chunks.append(delta.get('reasoning_content') or delta.get('reasoning'))
            print("Content chunks received:", len(content_chunks), f"Text: {''.join(content_chunks)}")
            print("Reasoning chunks received:", len(reasoning_chunks))
    except Exception as e:
        print("Error:", e)

def test_tools():
    print("\n--- 3. Testing Tool Calling for sektor9-autorouter ---")
    tools = [{
        "type": "function",
        "function": {
            "name": "lookup_user",
            "description": "Look up user info",
            "parameters": {
                "type": "object",
                "properties": {"username": {"type": "string"}},
                "required": ["username"]
            }
        }
    }]
    body = {
        "model": "sektor9-autorouter",
        "messages": [{"role": "user", "content": "Look up username 'alice'"}],
        "tools": tools,
        "max_tokens": 100
    }
    req = urllib.request.Request(
        "http://127.0.0.1:4000/v1/chat/completions",
        data=json.dumps(body).encode('utf-8'),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            res = json.load(r)
            choice = res["choices"][0]
            print("Finish reason:", choice.get("finish_reason"))
            print("Tool calls:", choice["message"].get("tool_calls"))
            print("Content:", choice["message"].get("content"))
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    test_chat()
    test_stream()
    test_tools()
