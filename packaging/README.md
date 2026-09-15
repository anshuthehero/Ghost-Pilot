# Ghost Copilot — Packaging & Distribution Architecture

This directory defines standalone build and packaging configurations for macOS and Windows.
**Existing application bundles (e.g. `Ghost Copilot.app` in repo root) are preserved as regression baselines.**

---

## 1. macOS Application Packaging

> **Verification Status**:
> - Packaging script: **IMPLEMENTED & RUNTIME-VERIFIED** (outputs to `dist/Ghost Copilot.app`).
> - Existing bundle `Ghost Copilot.app`: **PRESERVED** as known-good regression baseline.
> - Code signing & Notarization: **NOT VERIFIED** (requires active Apple Developer ID certificate).

### Build Command:
```bash
./packaging/macos/build_app.sh
```

### Process:
1. Compiles `ghost_copilot.m` with Clang (`-framework Cocoa -framework WebKit`) into `dist/Ghost Copilot.app/Contents/MacOS/ghost_copilot`.
2. Assembles native `Contents/Info.plist`, `AppIcon.icns`, and launcher scripts.
3. Bundles modular `client/`, `server/`, `desktop/`, and `shared/` python packages.
4. Output: `dist/Ghost Copilot.app`.

### Code Signing & Notarization Readiness:
```bash
# Ad-hoc sign for local testing:
codesign --force --deep --sign - "dist/Ghost Copilot.app"

# Production Developer ID Application signing:
codesign --force --deep --options runtime --sign "Developer ID Application: Your Name (ID)" "dist/Ghost Copilot.app"

# Notarization submission:
xcrun notarytool submit "dist/Ghost Copilot.app" --keychain-profile "notary-profile" --wait
```

---

## 2. Windows Desktop Packaging

> **Verification Status**:
> - PyInstaller spec & Inno Setup script: **IMPLEMENTED; PACKAGING SPECIFICATION CREATED; NOT BUILD/RUNTIME VERIFIED ON WINDOWS**
> - Note: The current execution host is macOS (Darwin); generating and testing frozen Windows PE binaries (`.exe`) requires a supported Windows 10/11 x64 machine.

### Prerequisites:
- Windows 10/11 x64
- Python 3.11+
- `pip install pyinstaller PyQt6 PyQt6-WebEngine`
- Inno Setup 6 (optional, for `.exe` installer)

### Step 1: Standalone Folder Packaging (PyInstaller)
```cmd
pyinstaller packaging\windows\ghost_copilot.spec
```
Outputs standalone directory to: `dist\GhostCopilot\` containing `GhostCopilot.exe`.

### Step 2: Installer Generation (Inno Setup)
```cmd
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" packaging\windows\installer.iss
```
Outputs: `dist\installer\GhostCopilot-Setup-v3.0.0.exe`.

### Code Signing:
```cmd
signtool sign /tr http://timestamp.digicert.com /td sha256 /fd sha256 /a dist\installer\GhostCopilot-Setup-v3.0.0.exe
```

---

## 3. FFmpeg Strategy Summary
- **macOS**: Looks for bundled binary in `Contents/MacOS/ffmpeg`, then falls back to Homebrew (`/opt/homebrew` on Apple Silicon, `/usr/local` on Intel) or system PATH.
- **Windows**: Looks for `ffmpeg.exe` alongside `GhostCopilot.exe` or `bin\ffmpeg.exe`, then WinGet path, Chocolatey path, or system PATH.
