#!/usr/bin/env bash
# Start the FastAPI backend (macOS / Linux)
set -euo pipefail
cd "$(dirname "$0")/../backend"

if [ ! -d ".venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
# Playwright ships its own Chromium — install it once.
python -m playwright install chromium

if [ ! -f ".env" ]; then
  echo "WARNING: No .env found. Copy .env.example to .env and add your GEMINI_API_KEY." >&2
fi

exec uvicorn main:app --reload --port 8008
