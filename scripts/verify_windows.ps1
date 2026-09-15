# ==============================================================================
# Ghost Copilot — Windows 10/11 x64 Reproducible Validation Script
# Usage in PowerShell (Admin recommended for loopback audio tests):
#   .\scripts\verify_windows.ps1
# ==============================================================================

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  👻 GHOST COPILOT — WINDOWS 10/11 RUNTIME & PACKAGING AUDIT   " -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan

# 1. Check Python Environment
Write-Host "`n[1/8] Checking Python Runtime..." -ForegroundColor Yellow
python --version
if ($LASTEXITCODE -ne 0) {
    Write-Error "Python 3.8+ (64-bit) is required on Windows."
    exit 1
}

# 2. Check & Install Requirements
Write-Host "`n[2/8] Checking Windows dependencies..." -ForegroundColor Yellow
pip install -r requirements.txt
pip install pyinstaller pytest pytest-asyncio
# Try PyQt6 first; fallback to PyQt5 on Windows 7 / Python 3.8
pip install PyQt6 PyQt6-WebEngine 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing PyQt5 for Windows 7..." -ForegroundColor Cyan
    pip install PyQt5 PyQtWebEngine requests
}

# 3. Run Automated Tests
Write-Host "`n[3/8] Running Automated Test Suite..." -ForegroundColor Yellow
pytest tests/ -v
if ($LASTEXITCODE -ne 0) {
    Write-Error "Test suite failed on Windows!"
    exit 1
}

# 4. Run Preflight Diagnostic Doctor
Write-Host "`n[4/8] Running Preflight Diagnostic Doctor..." -ForegroundColor Yellow
python -m client.diagnostics.preflight

# 5. Build PyInstaller Executable
Write-Host "`n[5/8] Assembling Standalone Executable with PyInstaller..." -ForegroundColor Yellow
pyinstaller packaging/windows/ghost_copilot.spec --clean
if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller build failed!"
    exit 1
}
Write-Host "[PASS] Standalone executable created at dist\GhostCopilot\GhostCopilot.exe" -ForegroundColor Green

# 6. Test Standalone Executable Launch
Write-Host "`n[6/8] Testing Standalone Executable Preflight..." -ForegroundColor Yellow
& ".\dist\GhostCopilot\GhostCopilot.exe" --diagnostics

# 7. Compile Inno Setup Installer
Write-Host "`n[7/8] Compiling Inno Setup Installer..." -ForegroundColor Yellow
if (Get-Command iscc -ErrorAction SilentlyContinue) {
    iscc packaging/windows/installer.iss
    Write-Host "[PASS] Installer compiled at dist\installer\GhostCopilot-Setup-v3.0.0.exe" -ForegroundColor Green
} else {
    Write-Host "[WARNING] ISCC (Inno Setup Compiler) not found in PATH." -ForegroundColor DarkYellow
    Write-Host "          Install Inno Setup 6+ and run: iscc packaging\windows\installer.iss"
}

# 8. Clean-Machine & Screen Exclusion Instructions
Write-Host "`n[8/8] Windows Screen Capture Exclusion & Clean Machine Verification:" -ForegroundColor Yellow
Write-Host "      1. Copy dist\installer\GhostCopilot-Setup-v3.0.0.exe to a clean Windows 10/11 VM."
Write-Host "      2. Run the installer and launch Ghost Copilot."
Write-Host "      3. Open Zoom / Teams / OBS and start screen share of entire display."
Write-Host "      4. Confirm Ghost Copilot HUD is INVISIBLE on the shared screen (WDA_EXCLUDEFROMCAPTURE)."
Write-Host "      5. Uninstall from Windows Settings -> Apps and verify clean removal."

Write-Host "`n================================================================" -ForegroundColor Cyan
Write-Host "  WINDOWS VALIDATION PROCEDURE PREPARED" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
