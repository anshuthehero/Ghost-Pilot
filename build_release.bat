@echo off
:: Build Ghost Copilot Windows EXE using PyInstaller
:: Run this on Windows to produce dist\GhostCopilot\GhostCopilot.exe
:: Then zip it and attach to a GitHub Release.

title Ghost Copilot — Windows Build
color 0A

echo.
echo   Ghost Copilot — Windows Build Script
echo   =====================================
echo.

cd /d "%~dp0"

:: Check Python
where python >nul 2>&1 || (echo [X] Python not found. Aborting. && pause && exit /b 1)

:: Install build dependencies
echo [*] Installing build dependencies...
python -m pip install --quiet --upgrade pip PyQt6 PyQt6-WebEngine PyInstaller
python -m pip install --quiet -r requirements.txt

:: Clean previous build
if exist dist\GhostCopilot   rmdir /s /q dist\GhostCopilot
if exist build\GhostCopilot  rmdir /s /q build\GhostCopilot

:: Build
echo [*] Building with PyInstaller...
pyinstaller packaging\windows\launcher_win.spec --noconfirm --clean

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [X] Build FAILED. Check output above.
    pause
    exit /b 1
)

:: Package as ZIP
echo [*] Packaging ZIP...
powershell -NoProfile -Command "Compress-Archive -Force -Path 'dist\GhostCopilot\*' -DestinationPath 'GhostCopilot_Windows_release.zip'"

echo.
echo [OK] Build complete!
echo      Executable: dist\GhostCopilot\GhostCopilot.exe
echo      Release ZIP: GhostCopilot_Windows_release.zip
echo.
echo Upload GhostCopilot_Windows_release.zip to:
echo https://github.com/anshuthehero/Ghost-Pilot/releases
echo.
pause
