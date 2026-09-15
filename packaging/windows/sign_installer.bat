@echo off
rem ==============================================================================
rem Ghost Copilot — Windows Authenticode Signing Script
rem Usage:
rem   set CERT_PATH=C:\path\to\certificate.pfx
rem   set CERT_PASSWORD=your_password
rem   call packaging\windows\sign_installer.bat
rem ==============================================================================

echo ================================================================
echo   👻 GHOST COPILOT — WINDOWS AUTHENTICODE SIGNING
echo ================================================================

if "%CERT_PATH%"=="" (
    echo.
    echo [NOT VERIFIED] CERT_PATH is not configured.
    echo                Acquire a standard Authenticode code-signing certificate and run:
    echo                set CERT_PATH=C:\certs\mycert.pfx ^&^& packaging\windows\sign_installer.bat
    echo                Status: READY FOR SIGNING — NOT VERIFIED (No Authenticode certificate)
    echo.
    exit /b 2
)

set EXECUTABLE=dist\GhostCopilot\GhostCopilot.exe
set INSTALLER=dist\installer\GhostCopilot-Setup-v3.0.0.exe

echo ==^> 1. Signing standalone executable...
signtool sign /f "%CERT_PATH%" /p "%CERT_PASSWORD%" /tr http://timestamp.digicert.com /td sha256 /fd sha256 /a "%EXECUTABLE%"
if %errorlevel% neq 0 (
    echo [FAIL] Failed to sign %EXECUTABLE%
    exit /b 1
)

echo ==^> 2. Verifying executable signature...
signtool verify /pa /v "%EXECUTABLE%"

if exist "%INSTALLER%" (
    echo ==^> 3. Signing Inno Setup installer...
    signtool sign /f "%CERT_PATH%" /p "%CERT_PASSWORD%" /tr http://timestamp.digicert.com /td sha256 /fd sha256 /a "%INSTALLER%"
    echo ==^> 4. Verifying installer signature...
    signtool verify /pa /v "%INSTALLER%"
)

echo ==^> SUCCESS: Windows artifacts signed and verified.
