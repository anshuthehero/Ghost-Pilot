@echo off
title Interview Assistant
echo ===================================================
echo   Starting Interview Assistant on Windows...
echo ===================================================
echo.

cd /d "%~dp0"

REM 1. Locate Python executable (bundled zero-install runtime -> virtualenv -> system PATH)
if exist "runtime\python.exe" (
    set "PYTHON_EXE=runtime\python.exe"
    echo [OK] Using Bundled Standalone Engine (Zero installation required).
) else if exist "python\python.exe" (
    set "PYTHON_EXE=python\python.exe"
    echo [OK] Using Portable Python from local folder.
) else if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
    call .venv\Scripts\activate.bat
) else (
    python --version >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        set "PYTHON_EXE=python"
    ) else (
        py --version >nul 2>&1
        if %ERRORLEVEL% EQU 0 (
            set "PYTHON_EXE=py"
        ) else (
            echo [X] Python was not found on your system!
            echo.
            echo ====================================================================
            echo   ZERO-INSTALLATION OPTION (No installer or admin rights needed!):
            echo ====================================================================
            echo 1. Download official portable Python 3.8 (only 8 MB):
            echo    https://www.python.org/ftp/python/3.8.10/python-3.8.10-embed-amd64.zip
            echo 2. Extract the contents of that zip into a "python" folder here:
            echo    %~dp0python\
            echo 3. Double-click start_windows.bat again.
            echo ====================================================================
            echo.
            pause
            exit /b 1
        )
    )
)

REM 1b. Verify Python executable can execute on this Windows version (Windows 7 check)
"%PYTHON_EXE%" -c "import sys" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ====================================================================
    echo   [!] WINDOWS COMPATIBILITY ISSUE DETECTED
    echo ====================================================================
    echo The bundled Python engine cannot start on your Windows configuration.
    echo.
    echo Detailed error output from your system:
    "%PYTHON_EXE%" -c "import sys"
    echo.
    echo --------------------------------------------------------------------
    echo HOW TO FIX ON WINDOWS 7:
    echo --------------------------------------------------------------------
    echo Option A (Automated):
    echo   Double-click "fix_windows7.bat" in this folder to apply fixes.
    echo.
    echo Option B (Manual):
    echo   1. Missing api-ms-win-crt-runtime-l1-1-0.dll:
    echo      Install Microsoft Visual C++ 2015-2022 Redistributable:
    echo      https://aka.ms/vs/17/release/vc_redist.x64.exe (64-bit)
    echo      https://aka.ms/vs/17/release/vc_redist.x86.exe (32-bit)
    echo.
    echo   2. Missing SetDefaultDllDirectories in KERNEL32.dll:
    echo      Install Windows 7 Update KB2533623 from Microsoft:
    echo      https://www.catalog.update.microsoft.com/Search.aspx?q=KB2533623
    echo.
    echo   3. 32-bit (x86) Windows 7:
    echo      Run "setup_portable_python.bat" to download the 32-bit portable runtime.
    echo ====================================================================
    echo.
    pause
    exit /b 1
)

REM 2. Verify .env exists and has Groq API key configured
if not exist ".env" (
    if exist ".env.example" (
        copy .env.example .env >nul
        echo [*] Created .env from template.
    ) else (
        echo GROQ_API_KEY=> .env
        echo [*] Created basic .env file.
    )
    echo [!] Notice: Please configure your GROQ_API_KEY in .env before running.
    start notepad .env
    pause
    exit /b 1
)

REM 3. Terminate any previous daemon instances
taskkill /F /IM python.exe /FI "WINDOWTITLE eq Interview Assistant Engine*" >nul 2>&1
taskkill /F /IM python.exe /FI "WINDOWTITLE eq Ghost Copilot Engine*" >nul 2>&1
timeout /t 1 /nobreak >nul 2>&1 || ping 127.0.0.1 -n 2 >nul

REM 4. Start local AI engine in background
echo [*] Starting Interview Assistant Engine on http://127.0.0.1:9471...
start "Interview Assistant Engine" /min "%PYTHON_EXE%" app.py

REM 5. Wait for engine startup
timeout /t 2 /nobreak >nul 2>&1 || ping 127.0.0.1 -n 3 >nul

REM 6. Install PyQt6 if missing, then launch the native stealth HUD
echo [*] Checking for native display engine (PyQt6)...
"%PYTHON_EXE%" -c "import PyQt6" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [*] Installing native display engine — one-time setup, please wait...
    "%PYTHON_EXE%" -m pip install --quiet --upgrade PyQt6 PyQt6-WebEngine
    if %ERRORLEVEL% NEQ 0 (
        echo.
        echo [!] Could not install PyQt6 automatically.
        echo     Please run once in a terminal:  pip install PyQt6 PyQt6-WebEngine
        echo     Then double-click start_windows.bat again.
        echo.
        pause
        exit /b 1
    )
    echo [OK] Display engine ready.
)

echo [*] Launching Ghost Copilot stealth window...
"%PYTHON_EXE%" -m client.platform.windows.client

REM 7. Clean shutdown when client window closes
echo.
echo [*] Stopping background engine...
call stop_windows.bat >nul 2>&1
echo [OK] Interview Assistant session closed.
