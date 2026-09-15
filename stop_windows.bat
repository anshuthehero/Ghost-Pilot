@echo off
title Interview Assistant - Stop Engine
echo ===================================================
echo   Stopping Interview Assistant background processes...
echo ===================================================
echo.

REM 1. Terminate named engine console
taskkill /F /IM python.exe /FI "WINDOWTITLE eq Interview Assistant Engine*" >nul 2>&1
taskkill /F /IM python.exe /FI "WINDOWTITLE eq Ghost Copilot Engine*" >nul 2>&1

REM 2. Free port 9471 if any zombie process holds it
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":9471" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)

echo [OK] Interview Assistant engine stopped successfully.
timeout /t 1 /nobreak >nul 2>&1 || ping 127.0.0.1 -n 2 >nul
