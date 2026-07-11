@echo off
REM Start the Next.js frontend.
cd /d "%~dp0..\frontend"

if not exist "node_modules" (
    echo Installing frontend dependencies...
    npm install
)

echo.
echo Frontend running on http://localhost:3000  (Ctrl+C to stop)
npm run dev
