import urllib.request
import json
from pathlib import Path

lines = Path(".env").read_text(encoding="utf-8").splitlines()
key = [l.split("=", 1)[1].strip().strip("\"'") for l in lines if l.startswith("LITELLM_MASTER_KEY=")][0]

print("Testing http://localhost:4000/mcp ...")
req = urllib.request.Request(
    "http://127.0.0.1:4000/mcp",
    headers={"Authorization": f"Bearer {key}", "Accept": "text/event-stream"}
)
try:
    with urllib.request.urlopen(req, timeout=10) as r:
        print("Status:", r.status)
        print("Content-Type:", r.headers.get("content-type"))
except Exception as e:
    print("Error:", e)
