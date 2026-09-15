@echo off
title Interview Assistant - Windows 7 Fix & Setup
echo ====================================================================
echo   Interview Assistant - Windows 7 Compatibility Helper
echo ====================================================================
echo.
echo This helper fixes common Windows 7 compatibility issues:
echo   1. Missing Microsoft Universal C Runtime (api-ms-win-crt-runtime-l1-1-0.dll)
echo   2. Architecture setup (64-bit vs 32-bit)
echo.

cd /d "%~dp0"

REM Detect architecture
if "%PROCESSOR_ARCHITECTURE%"=="AMD64" (
    set "ARCH=x64"
    set "VC_URL=https://aka.ms/vs/17/release/vc_redist.x64.exe"
    set "PY_URL=https://www.python.org/ftp/python/3.8.10/python-3.8.10-embed-amd64.zip"
) else if "%PROCESSOR_ARCHITEW6432%"=="AMD64" (
    set "ARCH=x64"
    set "VC_URL=https://aka.ms/vs/17/release/vc_redist.x64.exe"
    set "PY_URL=https://www.python.org/ftp/python/3.8.10/python-3.8.10-embed-amd64.zip"
) else (
    set "ARCH=x86"
    set "VC_URL=https://aka.ms/vs/17/release/vc_redist.x86.exe"
    set "PY_URL=https://www.python.org/ftp/python/3.8.10/python-3.8.10-embed-win32.zip"
)

echo [*] Detected System Architecture: %ARCH%
echo.

REM 1. Test existing bundled python
if exist "runtime\python.exe" (
    runtime\python.exe -c "import sys" >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        echo [OK] Python runtime is already working properly on your system!
        echo You can run InterviewAssistant.vbs or start_windows.bat directly.
        echo.
        pause
        exit /b 0
    )
)

echo [*] Python engine cannot start yet. Applying Windows 7 fixes...
echo.

REM 2. If 32-bit Windows 7, replace 64-bit runtime with 32-bit portable Python
if "%ARCH%"=="x86" (
    echo [*] Detected 32-bit Windows. Downloading 32-bit portable Python 3.8.10...
    powershell -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object System.Net.WebClient).DownloadFile('%PY_URL%', 'python_win32.zip')" >nul 2>&1
    if exist "python_win32.zip" (
        echo [*] Extracting 32-bit Python into runtime folder...
        powershell -NoProfile -Command "Expand-Archive -Path 'python_win32.zip' -DestinationPath 'runtime' -Force" >nul 2>&1
        del /q "python_win32.zip" >nul 2>&1
    )
)

REM 3. Download and install Microsoft Visual C++ 2015-2022 Redistributable (provides UCRT)
echo [*] Downloading Microsoft Visual C++ Redistributable (%ARCH%)...
powershell -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object System.Net.WebClient).DownloadFile('%VC_URL%', 'vc_redist.exe')" >nul 2>&1

if exist "vc_redist.exe" (
    echo [*] Installing Microsoft Visual C++ Redistributable...
    echo (Please click 'Yes' if prompted for Administrator permission)
    vc_redist.exe /passive /norestart
    del /q "vc_redist.exe" >nul 2>&1
    echo [OK] VC++ Redistributable installation finished.
) else (
    echo.
    echo [!] Could not download vc_redist automatically.
    echo Please open this URL in your web browser:
    echo   %VC_URL%
    echo Download and run it, then press any key to continue...
    pause
)

echo.
echo [*] Testing Python runtime...
if exist "runtime\python.exe" (
    runtime\python.exe -c "import sys" >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        echo.
        echo ====================================================================
        echo   [SUCCESS] Windows 7 compatibility fix applied successfully!
        echo   You can now run InterviewAssistant.vbs or start_windows.bat.
        echo ====================================================================
    ) else (
        echo.
        echo ====================================================================
        echo   [!] Additional Step Needed for Older Windows 7 (SP1):
        echo --------------------------------------------------------------------
        echo If Python still gives a SetDefaultDllDirectories error:
        echo Install Windows Update KB2533623 from Microsoft:
        echo https://www.catalog.update.microsoft.com/Search.aspx?q=KB2533623
        echo ====================================================================
    )
)

echo.
pause
