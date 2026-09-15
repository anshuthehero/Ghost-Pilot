#!/usr/bin/env bash
# ==============================================================================
# Ghost Copilot — macOS Developer ID Code Signing & Notarization Script
# Usage:
#   DEVELOPER_ID="Developer ID Application: Your Name (TEAMID)" \
#   APPLE_ID="dev@example.com" \
#   APP_SPECIFIC_PW="xxxx-xxxx-xxxx-xxxx" \
#   TEAM_ID="TEAMID1234" \
#   ./packaging/macos/sign_and_notarize.sh
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
APP_PATH="$REPO_ROOT/dist/Ghost Copilot.app"
ZIP_PATH="$REPO_ROOT/dist/GhostCopilot.zip"

echo "================================================================"
echo "  👻 GHOST COPILOT — MACOS SIGNING & NOTARIZATION PIPELINE"
echo "================================================================"

if [ ! -d "$APP_PATH" ]; then
    echo "ERROR: Bundle not found at $APP_PATH. Run packaging/macos/build_app.sh first." >&2
    exit 1
fi

SIGNING_IDENTITY="${DEVELOPER_ID:-}"

if [ -z "$SIGNING_IDENTITY" ]; then
    echo ""
    echo "[NOT VERIFIED] Code signing identity DEVELOPER_ID is not configured."
    echo "               Acquire an Apple Developer ID Application certificate and run:"
    echo "               DEVELOPER_ID=\"Developer ID Application: ...\" ./packaging/macos/sign_and_notarize.sh"
    echo "               Status: READY FOR SIGNING — NOT VERIFIED (No Apple Developer ID certificate)"
    echo ""
    exit 2
fi

echo "==> 1. Signing application bundle with hardened runtime and timestamp..."
codesign --force --deep --options runtime --timestamp --sign "$SIGNING_IDENTITY" "$APP_PATH"

echo "==> 2. Verifying local codesign signature..."
codesign --verify --deep --strict --verbose=2 "$APP_PATH"

echo "==> 3. Creating archive for Apple Notary Service..."
ditto -c -k --keepParent "$APP_PATH" "$ZIP_PATH"

if [ -n "${APPLE_ID:-}" ] && [ -n "${APP_SPECIFIC_PW:-}" ] && [ -n "${TEAM_ID:-}" ]; then
    echo "==> 4. Submitting archive to Apple Notary Service..."
    xcrun notarytool submit "$ZIP_PATH" \
        --apple-id "$APPLE_ID" \
        --password "$APP_SPECIFIC_PW" \
        --team-id "$TEAM_ID" \
        --wait

    echo "==> 5. Stapling notarization ticket to application bundle..."
    xcrun stapler staple "$APP_PATH"

    echo "==> 6. Validating Gatekeeper acceptance..."
    spctl --assess --verbose=4 --type execute "$APP_PATH"
    echo "==> SUCCESS: Ghost Copilot.app is signed, notarized, stapled, and Gatekeeper-compliant!"
else
    echo ""
    echo "[INFO] App signed locally. Notarization requires APPLE_ID, APP_SPECIFIC_PW, and TEAM_ID."
    echo ""
fi
