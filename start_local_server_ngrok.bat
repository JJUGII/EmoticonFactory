@echo off
setlocal
cd /d "%~dp0"
title KakaoEmoticonFactory Local API + ngrok

echo.
echo [INFO] Starting local FastAPI + ngrok tunnel
echo [INFO] Free plan: random URL each run (leave NGROK_DOMAIN empty)
echo [INFO] Paid plan: set NGROK_DOMAIN in .env - see README_NGROK.md
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_local_server_ngrok.ps1"
set EXITCODE=%ERRORLEVEL%

if not "%EXITCODE%"=="0" (
  echo.
  echo [ERROR] start_local_server_ngrok.ps1 failed with exit code %EXITCODE%
  pause
  exit /b %EXITCODE%
)

exit /b 0
