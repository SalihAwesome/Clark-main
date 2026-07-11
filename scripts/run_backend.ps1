# Start the FastAPI backend (Windows PowerShell)
# Usage:  ./scripts/run_backend.ps1
$ErrorActionPreference = "Stop"
Set-Location "$PSScriptRoot/../backend"

if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment..."
    python -m venv .venv
}
& ".venv/Scripts/python.exe" -m pip install --quiet --upgrade pip
& ".venv/Scripts/python.exe" -m pip install --quiet -r requirements.txt
# Playwright ships its own Chromium — install it once.
& ".venv/Scripts/python.exe" -m playwright install chromium

if (-not (Test-Path ".env")) {
    Write-Warning "No .env found. Copy .env.example to .env and add your GEMINI_API_KEY."
}

& ".venv/Scripts/python.exe" -m uvicorn main:app --reload --port 8008
