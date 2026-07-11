# Start the Clark Agent stack: backend + frontend (PowerShell launcher).
# NOTE: named "desktop" for historical reasons — the Electron desktop shell was
# removed. This launches the web-based stack (backend + frontend) in two windows.
# Usage:  ./scripts/run_desktop.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent

Write-Host "→ Starting backend (FastAPI, port 8008)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-File", "$PSScriptRoot/run_backend.ps1"

Write-Host "→ Starting frontend (Next.js, port 3000)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-File", "$PSScriptRoot/run_frontend.ps1"

Write-Host "→ Waiting for the UI on http://localhost:3000 ..." -ForegroundColor Cyan
$ready = $false
for ($i = 0; $i -lt 60; $i++) {
    try {
        Invoke-WebRequest -Uri "http://localhost:3000" -UseBasicParsing -TimeoutSec 2 | Out-Null
        $ready = $true; break
    } catch { Start-Sleep -Seconds 2 }
}
if (-not $ready) { Write-Warning "UI did not come up in time." }

Write-Host "→ Clark running at http://localhost:3000" -ForegroundColor Green
