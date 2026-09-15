@echo off
title Interview Assistant - Windows Setup
echo ===================================================
echo   Interview Assistant - Windows Automatic Setup
echo ===================================================
echo.

cd /d "%~dp0"

REM 1. Verify Python installation (check portable folder first, then system PATH)
if exist "python\python.exe" (
    set "PYTHON_CMD=python\python.exe"
    echo [OK] Using Portable Python from local folder.
) else if exist "runtime\python.exe" (
    set "PYTHON_CMD=runtime\python.exe"
    echo [OK] Using Portable Python from runtime folder.
) else (
    python --version >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        set "PYTHON_CMD=python"
    ) else (
        py --version >nul 2>&1
        if %ERRORLEVEL% EQU 0 (
            set "PYTHON_CMD=py"
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
            echo 3. Double-click start_windows.bat to launch immediately!
            echo ====================================================================
            echo.
            pause
            exit /b 1
        )
    )
)

echo [OK] Python detected:
%PYTHON_CMD% --version
echo.

REM 2. Create Python virtual environment if missing
if not exist ".venv" (
    echo [*] Creating virtual environment (.venv)...
    %PYTHON_CMD% -m venv .venv
)
call .venv\Scripts\activate.bat

REM 3. Install required desktop dependencies
echo [*] Installing GUI dependencies...
if exist ".venv\Scripts\python.exe" (
    set "RUN_PY=.venv\Scripts\python.exe"
) else (
    set "RUN_PY=%PYTHON_CMD%"
)
"%RUN_PY%" -m pip install --upgrade pip

REM Try PyQt6 first (Windows 10/11), then PyQt5 (Windows 7/8)
"%RUN_PY%" -m pip install PyQt6 PyQt6-WebEngine >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [*] PyQt6 not compatible with this OS/Python version. Installing PyQt5 for Windows 7 / 8...
    "%RUN_PY%" -m pip install PyQt5 PyQtWebEngine requests
    if %ERRORLEVEL% NEQ 0 (
        echo [!] Notice: Native Qt window could not be installed.
        echo [*] No problem: Ghost Copilot will run with zero packages and open directly in your web browser!
    ) else (
        echo [OK] PyQt5 installed successfully for Windows 7 / 8.
    )
) else (
    echo [OK] PyQt6 installed successfully.
)

REM 4. Check for FFmpeg
ffmpeg -version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [*] Checking for WinGet package manager...
    where winget >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        echo [*] Attempting automated FFmpeg install via WinGet...
        winget install -e --id Gyan.FFmpeg
    ) else (
        echo [!] Notice: FFmpeg was not detected in PATH.
        echo For audio capture, download ffmpeg.exe (essentials build) from:
        echo https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip
        echo Extract ffmpeg.exe and place it in this folder or in your Windows PATH.
    )
) else (
    echo [OK] FFmpeg is already installed and ready.
)

REM 5. Setup .env configuration file
if not exist ".env" (
    if exist ".env.example" (
        copy .env.example .env >nul
        echo [OK] Created .env file from template.
    ) else (
        echo GROQ_API_KEY=> .env
        echo [OK] Created basic .env file.
    )
    echo.
    echo [!] IMPORTANT: Please edit the .env file and paste your GROQ_API_KEY!
    start notepad .env
)

echo.
echo ===================================================
echo   Setup Complete! You can now run start_windows.bat
echo ===================================================
echo.
pause
