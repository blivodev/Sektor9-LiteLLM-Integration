# Registers a weekly Windows Scheduled Task that runs refresh_models.py
# (see that file's docstring for exactly what it does and its safety net).
# Re-run this any time to update the schedule; safe to run repeatedly.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$scriptPath = Join-Path $root "scripts\refresh_models.py"
$taskName = "LiteLLM Model Refresh"

$pythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $pythonExe) { $pythonExe = (Get-Command python3 -ErrorAction SilentlyContinue).Source }
if (-not $pythonExe) {
    Write-Error "Python not found on PATH. Install Python 3 (python.org or 'winget install Python.Python.3'), then re-run this script."
    exit 1
}

$action = New-ScheduledTaskAction -Execute $pythonExe -Argument "`"$scriptPath`" --restart" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 9am
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings `
    -Description "Weekly check for cheaper/newer models at your configured LLM providers (scripts/refresh_models.py). Validates live before applying; old model kept as fallback; every change is a git commit." `
    -Force | Out-Null

Write-Host "Scheduled '$taskName' to run every Monday at 9am."
Write-Host "Run it manually any time with: python `"$scriptPath`" --dry-run"
Write-Host "View/edit/remove it in Task Scheduler (taskschd.msc), or: Unregister-ScheduledTask -TaskName '$taskName' -Confirm:`$false"
