import sqlite3
import os
import json
import shutil
import time
from pathlib import Path

# 1. Back up database
db_path = Path(os.environ['APPDATA']) / 'CherryStudio' / 'Data' / 'cherrystudio.sqlite'
timestamp = int(time.time())
backup_db = db_path.parent / f"cherrystudio.sqlite.backup_{timestamp}"
shutil.copy2(db_path, backup_db)
print(f"[+] Backed up DB to: {backup_db}")

# 2. Back up and update Task 21
task_file = Path(os.environ['APPDATA']) / 'CherryStudio' / 'Data' / 'Agents' / '.claude' / 'tasks' / '95da3d1c-9efb-4277-bd82-cc54a95379f9' / '21.json'
if task_file.exists():
    shutil.copy2(task_file, task_file.parent / "21.json.bak")
    task_data = json.loads(task_file.read_text(encoding='utf-8'))
    print(f"[+] Task 21 previous status: {task_data.get('status')}")
    task_data["status"] = "completed"
    task_file.write_text(json.dumps(task_data, indent=2), encoding='utf-8')
    print("[+] Task 21 updated to status: 'completed'")

# 3. Clean up stuck messages in cherrystudio.sqlite
conn = sqlite3.connect(db_path)
cur = conn.cursor()

session_id = 'e25ce007-e668-4197-814f-920be8ca98b1'

# Set previous finished assistant message status to 'success'
finished_assistant_id = '01a0e140-77ac-72a7-a8b3-28aa1f7d0605'
cur.execute("UPDATE agent_session_message SET status = 'success' WHERE id = ?", (finished_assistant_id,))
print(f"[+] Marked {finished_assistant_id} as 'success'")

# IDs to delete (the stuck empty assistant messages and redundant user 'Continue' clicks)
stuck_ids = [
    '01a0e2ca-f6c9-772d-8bc6-fb2445460057', # assistant paused (0 parts)
    '01a0e2ca-f6c8-76e5-8acf-7518d14c3244', # user Continue
    '01a0e2c9-768a-7139-be17-c4825836bcaa', # assistant paused (0 parts)
    '01a0e2c9-768a-7139-be17-c33cbc2595f5', # user Continue
    '01a0e2c7-a5c8-721b-9a3f-7ca51d420663', # user Continue
    '01a0e2be-1bc3-73f6-b821-1dcffc1c7017'  # assistant paused (0 parts)
]

for mid in stuck_ids:
    cur.execute("DELETE FROM agent_session_message WHERE id = ?", (mid,))
    print(f"[-] Deleted stuck message: {mid}")

conn.commit()

# Verify remaining messages
rows = cur.execute("SELECT id, role, status, searchable_text FROM agent_session_message WHERE session_id = ? ORDER BY created_at DESC LIMIT 5", (session_id,)).fetchall()
print("\n[+] Remaining messages in session (most recent first):")
for r in rows:
    print(f"  ID: {r[0]} | Role: {r[1]} | Status: {r[2]} | Text: {r[3][:60]}")

conn.close()
print("\n>>> Cherry Studio Database and Task State Cleaned Successfully! <<<")
