import urllib.request
import json
from pathlib import Path

lines = Path('.env').read_text().splitlines()
key = [l.split('=', 1)[1].strip('"\' ') for l in lines if l.startswith('LITELLM_MASTER_KEY=')][0]

models = ['sektor9-autorouter', 'autorouter', 'auto-router', 'sektor9-auto']
for m in models:
    try:
        # Test Anthropic /v1/messages
        req = urllib.request.Request(
            'http://127.0.0.1:4000/v1/messages',
            data=json.dumps({
                'model': m,
                'messages': [{'role': 'user', 'content': 'Say OK'}],
                'max_tokens': 50
            }).encode('utf-8'),
            headers={
                'Authorization': f'Bearer {key}',
                'x-api-key': key,
                'anthropic-version': '2023-06-01',
                'Content-Type': 'application/json'
            }
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            res = json.load(r)
            text = res.get('content', [{}])[0].get('text', '')
            print(f"[Anthropic /v1/messages] {m:20} -> text: {text.strip()!r:10} stop_reason: {res.get('stop_reason')}")
    except Exception as e:
        print(f"[Anthropic /v1/messages] {m:20} -> ERROR: {e}")

    try:
        # Test OpenAI /v1/chat/completions
        req_oa = urllib.request.Request(
            'http://127.0.0.1:4000/v1/chat/completions',
            data=json.dumps({
                'model': m,
                'messages': [{'role': 'user', 'content': 'Say OK'}],
                'max_tokens': 50
            }).encode('utf-8'),
            headers={
                'Authorization': f'Bearer {key}',
                'Content-Type': 'application/json'
            }
        )
        with urllib.request.urlopen(req_oa, timeout=15) as r:
            res_oa = json.load(r)
            content = res_oa['choices'][0]['message']['content']
            print(f"[OpenAI /v1/chat/completions] {m:16} -> content: {content.strip()!r}")
    except Exception as e:
        print(f"[OpenAI /v1/chat/completions] {m:16} -> ERROR: {e}")
