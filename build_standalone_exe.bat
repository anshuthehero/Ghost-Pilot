@echo off
title Interview Assistant - Build Standalone Windows Executable (.exe)
echo ====================================================================
echo   Interview Assistant - Standalone Windows Executable Builder (.exe)
echo   Generates a 100%% self-contained application for your end users
echo ====================================================================
echo.

cd /d "%~dp0"

REM 1. Identify Python compiler environment
if exist ".venv\Scripts\python.exe" (
    set "BUILD_PY=.venv\Scripts\python.exe"
) else if exist "python\python.exe" (
    set "BUILD_PY=python\python.exe"
) else (
    python --version >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        set "BUILD_PY=python"
    ) else (
        echo [X] Python was not detected to compile the binary.
        echo Please ensure Python is available to build the .exe.
        pause
        exit /b 1
    )
)

echo [OK] Using Python compiler:
"%BUILD_PY%" --version
echo.

REM 2. Ensure PyInstaller is installed in builder environment
echo [*] Checking PyInstaller compiler tool...
"%BUILD_PY%" -m pip install pyinstaller >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [*] Installing PyInstaller...
    "%BUILD_PY%" -m pip install pyinstaller
)

REM 3. Compile Standalone Application
echo.
echo [*] Compiling Ghost Copilot into standalone binary...
echo (This packages Python, standard libraries, and all code into GhostCopilot.exe)
"%BUILD_PY%" -m PyInstaller packaging\windows\ghost_copilot.spec --clean --noconfirm

if exist "dist\GhostCopilot\GhostCopilot.exe" (
    echo.
    echo ====================================================================
    echo   [SUCCESS] Standalone Executable Created!
    echo ====================================================================
    echo Output directory: %~dp0dist\GhostCopilot\
    echo Main application: %~dp0dist\GhostCopilot\GhostCopilot.exe
    echo.
    echo WHAT TO DISTRIBUTE TO YOUR END USERS:
    echo - You can zip the "dist\GhostCopilot" folder and distribute it!
    echo - Your users just double-click "GhostCopilot.exe".
    echo - Your users NEVER need to install Python, see Python, or install anything!
    echo ====================================================================
    
    REM Optional: Compile Inno Setup single installer if iscc exists
    where iscc >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        echo.
        echo [*] Compiling Inno Setup single-file installer (.exe)...
        iscc packaging\windows\installer.iss
        if exist "dist\installer\GhostCopilot-Setup-v3.0.0.exe" (
            echo [PASS] Single installer created at: dist\installer\GhostCopilot-Setup-v3.0.0.exe
        )
    )
) else (
    echo.
    echo [X] Build did not produce GhostCopilot.exe. Please check the compiler errors above.
)

echo.
pause
