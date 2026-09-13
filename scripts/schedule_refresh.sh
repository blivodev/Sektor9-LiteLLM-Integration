#!/usr/bin/env bash
# Installs a weekly cron entry that runs refresh_models.py (see that file's
# docstring for exactly what it does and its safety net). Safe to re-run —
# replaces any previous entry for this script rather than duplicating it.

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$ROOT/scripts/refresh_models.py"

PYTHON=$(command -v python3 || command -v python || true)
if [ -z "$PYTHON" ]; then
  echo "Python not found on PATH. Install Python 3, then re-run this script." >&2
  exit 1
fi

CRON_LINE="0 9 * * 1 cd \"$ROOT\" && \"$PYTHON\" \"$SCRIPT\" --restart >> \"$ROOT/scripts/refresh_models.cron.log\" 2>&1"
( crontab -l 2>/dev/null | grep -vF "$SCRIPT" || true; echo "$CRON_LINE" ) | crontab -

echo "Installed a weekly (Monday 9am) cron job for model refresh."
echo "Run it manually any time with: $PYTHON \"$SCRIPT\" --dry-run"
echo "View with: crontab -l   |   Remove with: crontab -e (delete the line)"
