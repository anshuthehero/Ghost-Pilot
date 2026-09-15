@echo off
title Interview Assistant - Portable Python Setup
echo ====================================================================
echo   Interview Assistant - Portable Python (Zero Installation)
echo ====================================================================
echo.

cd /d "%~dp0"

if exist "python\python.exe" (
    echo [OK] Portable Python is already present in %~dp0python\
    echo You can directly run start_windows.bat!
    echo.
    pause
    exit /b 0
)

REM Detect architecture
if "%PROCESSOR_ARCHITECTURE%"=="x86" (
    set "PY_URL=https://www.python.org/ftp/python/3.8.10/python-3.8.10-embed-win32.zip"
    echo [*] Detected 32-bit Windows architecture.
) else (
    set "PY_URL=https://www.python.org/ftp/python/3.8.10/python-3.8.10-embed-amd64.zip"
    echo [*] Detected 64-bit Windows architecture.
)

echo [*] Downloading official portable Python 3.8.10 (8.7 MB)...
powershell -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object System.Net.WebClient).DownloadFile('%PY_URL%', 'python_portable.zip')" >nul 2>&1

if not exist "python_portable.zip" (
    echo.
    echo [!] Automatic download failed or machine is offline.
    echo.
    echo Please download it in your browser:
    echo 1. Open: %PY_URL%
    echo 2. Save it here and extract into a folder named "python".
    echo.
    pause
    exit /b 1
)

echo [*] Extracting portable Python into "python" folder...
powershell -NoProfile -Command "Expand-Archive -Path 'python_portable.zip' -DestinationPath 'python' -Force" >nul 2>&1

if not exist "python\python.exe" (
    cscript //nologo //e:jscript -e "var zip = '%~dp0python_portable.zip'; var dest = '%~dp0python'; try { new ActiveXObject('Scripting.FileSystemObject').CreateFolder(dest); } catch(e){} var sh = new ActiveXObject('Shell.Application'); sh.Namespace(dest).CopyHere(sh.Namespace(zip).Items(), 16);" >nul 2>&1
)

if exist "python\python.exe" (
    del /q "python_portable.zip" >nul 2>&1
    echo.
    echo ====================================================================
    echo   [SUCCESS] Portable Python is ready!
    echo   Zero system installation was performed.
    echo   You can now double-click start_windows.bat to run Interview Assistant!
    echo ====================================================================
) else (
    echo [!] Extraction failed. Please right-click "python_portable.zip"
    echo     and extract it into a folder named "python".
)

echo.
pause
