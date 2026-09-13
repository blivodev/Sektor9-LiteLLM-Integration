# Ensures the LiteLLM + Postgres docker-compose stack is up.
# Invoked automatically by .vscode/tasks.json on folder open, but safe to
# run by hand any time: powershell -File scripts/start-litellm.ps1

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

function Write-Log($msg) {
    Write-Host "[litellm-startup] $msg"
}

# 1. Make sure the Docker engine is responding; start Docker Desktop if not.
function Test-DockerReady {
    try {
        docker info *> $null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

$dockerReady = Test-DockerReady

if (-not $dockerReady) {
    Write-Log "Docker engine not responding — attempting to start Docker Desktop..."
    $dockerDesktop = Join-Path $Env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
    if (Test-Path $dockerDesktop) {
        Start-Process -FilePath $dockerDesktop
    } else {
        Write-Log "Could not find Docker Desktop at '$dockerDesktop'. Start it manually, then re-run this script."
    }

    $attempts = 0
    while (-not $dockerReady -and $attempts -lt 60) {
        Start-Sleep -Seconds 2
        $attempts++
        $dockerReady = Test-DockerReady
    }
}

if (-not $dockerReady) {
    Write-Log "Docker did not become ready after ~2 minutes. Aborting — start Docker Desktop and re-run this task."
    exit 1
}

Write-Log "Docker engine is up."

# 2. Bring the stack up (no-op if the containers are already running).
docker compose up -d
if ($LASTEXITCODE -ne 0) {
    Write-Log "docker compose up failed — see output above."
    exit 1
}

# 3. Wait for LiteLLM's liveness endpoint (cheap check: is the process up,
# without pinging every configured model/provider).
$healthy = $false
$attempts = 0
while (-not $healthy -and $attempts -lt 30) {
    try {
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:4000/health/liveliness" -UseBasicParsing -TimeoutSec 3
        if ($resp.StatusCode -eq 200) { $healthy = $true }
    } catch {}
    if (-not $healthy) {
        Start-Sleep -Seconds 2
        $attempts++
    }
}

if ($healthy) {
    Write-Log "LiteLLM proxy is up at http://127.0.0.1:4000"
} else {
    Write-Log "LiteLLM did not report healthy yet. Check with: docker compose logs litellm"
}
