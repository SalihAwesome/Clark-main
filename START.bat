@echo off
REM ===================================================================
REM  Clark Agent - one-click launcher (no PowerShell policy issues)
REM  Double-click this file. It starts backend + frontend.
REM ===================================================================
setlocal
cd /d "%~dp0"

REM --- First-run: make sure the API key is set ---
if not exist "backend\.env" (
    copy "backend\.env.example" "backend\.env" >nul
    echo.
    echo  ------------------------------------------------------------
    echo   Created backend\.env
    echo   Opening it now - paste your GEMINI_API_KEY, SAVE, then
    echo   run START.bat again.
    echo  ------------------------------------------------------------
    echo.
    notepad "backend\.env"
    pause
    exit /b
)

echo.
echo  Starting Clark...
echo   1/2 backend  (http://localhost:8008)
echo   2/2 frontend (http://localhost:3000)
echo.

start "Clark Backend"  cmd /k "%~dp0scripts\start-backend.bat"
start "Clark Frontend" cmd /k "%~dp0scripts\start-frontend.bat"

echo.
echo  Two windows opened. Close them to stop everything.
echo.
exit /b
