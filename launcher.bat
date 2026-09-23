@echo off
:: Ghost Copilot Launcher — Windows double-click starter
:: No personal info. No web browser. Pure desktop.

title Ghost Copilot
color 0A

echo.
echo   Ghost Copilot - Starting Launcher...
echo.

:: ── Find Python ──────────────────────────────────────────────────────────────
set "PY="
where python >nul 2>&1 && set "PY=python"
where py     >nul 2>&1 && if not defined PY set "PY=py"

if not defined PY (
    echo   [ERROR] Python not found. Download at python.org/downloads
    echo   Then run this launcher again.
    pause
    exit /b 1
)

:: ── Check PyQt6 installed ────────────────────────────────────────────────────
%PY% -c "import PyQt6" >nul 2>&1
if errorlevel 1 (
    echo   PyQt6 not found. Installing now...
    %PY% -m pip install --quiet --upgrade PyQt6 PyQt6-WebEngine
    if errorlevel 1 (
        echo   [ERROR] Could not install PyQt6.
        echo   Run manually:  pip install PyQt6 PyQt6-WebEngine
        pause
        exit /b 1
    )
    echo   Done. Launching...
)

:: ── Launch ───────────────────────────────────────────────────────────────────
%PY% "%~dp0launcher.py"
