# Start the Next.js frontend (Windows PowerShell)
# Usage:  ./scripts/run_frontend.ps1
$ErrorActionPreference = "Stop"
Set-Location "$PSScriptRoot/../frontend"

if (-not (Test-Path "node_modules")) {
    Write-Host "Installing frontend dependencies..."
    npm install
}
npm run dev
