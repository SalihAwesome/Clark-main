@echo off
REM Start the FastAPI backend (no PowerShell execution-policy issues).
cd /d "%~dp0..\backend"

if not exist ".venv" (
    echo Creating Python virtual environment...
    python -m venv .venv
)
call ".venv\Scripts\activate.bat"

echo Installing/updating backend dependencies...
python -m pip install --upgrade pip >nul 2>&1
pip install -r requirements.txt
echo Ensuring Playwright Chromium is installed (one-time)...
python -m playwright install chromium

if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo.
    echo  *** Created backend\.env - open it, add your GEMINI_API_KEY, then re-run. ***
    echo.
    notepad ".env"
    pause
    exit /b
)

echo.
echo Backend running on http://localhost:8008  (Ctrl+C to stop)
python -m uvicorn main:app --reload --port 8008
