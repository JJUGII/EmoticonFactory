@echo off
setlocal
cd /d "%~dp0"
title KakaoEmoticonFactory Local API

echo.
echo [INFO] Starting local FastAPI + Cloudflare Tunnel
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_local_server.ps1"
set EXITCODE=%ERRORLEVEL%

if not "%EXITCODE%"=="0" (
  echo.
  echo [ERROR] start_local_server.ps1 failed with exit code %EXITCODE%
  pause
  exit /b %EXITCODE%
)

exit /b 0
