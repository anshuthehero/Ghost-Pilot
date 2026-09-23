#!/bin/bash
# Build Ghost Copilot macOS .app using PyInstaller
# Run this on macOS to produce dist/Ghost Copilot.app
# Then zip it and attach to a GitHub Release.

set -e
cd "$(dirname "$0")"

echo ""
echo "  Ghost Copilot — macOS Build Script"
echo "  ====================================="
echo ""

# Check Python
PY=""
for candidate in python3 python3.12 python3.11 python3.10; do
    if command -v "$candidate" &>/dev/null; then
        PY="$candidate"
        break
    fi
done

if [ -z "$PY" ]; then
    echo "[X] Python 3 not found. Install with: brew install python"
    exit 1
fi
echo "[*] Using $PY ($($PY --version))"

# Install build dependencies
echo "[*] Installing build dependencies..."
"$PY" -m pip install --quiet --upgrade pip PyQt6 PyQt6-WebEngine PyInstaller
"$PY" -m pip install --quiet -r requirements.txt

# Clean previous build
rm -rf "dist/Ghost Copilot.app" "build/Ghost Copilot"

# Build
echo "[*] Building with PyInstaller..."
"$PY" -m PyInstaller packaging/macos/launcher_mac.spec --noconfirm --clean

# Package as ZIP
echo "[*] Packaging ZIP..."
cd dist
zip -r "../GhostCopilot_Mac_release.zip" "Ghost Copilot.app"
cd ..

echo ""
echo "[OK] Build complete!"
echo "     App bundle: dist/Ghost Copilot.app"
echo "     Release ZIP: GhostCopilot_Mac_release.zip"
echo ""
echo "Upload GhostCopilot_Mac_release.zip to:"
echo "https://github.com/anshuthehero/Ghost-Pilot/releases"
echo ""
