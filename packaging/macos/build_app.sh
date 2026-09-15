#!/usr/bin/env bash
# ==============================================================================
# Ghost Copilot — macOS Application Packaging Script
# Compiles the native Cocoa/WebKit stealth HUD and builds a clean .app bundle.
# Treats the existing working Ghost Copilot.app as a regression baseline.
# Outputs to: dist/Ghost Copilot.app
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DIST_DIR="$REPO_ROOT/dist"
APP_NAME="Ghost Copilot.app"
APP_BUNDLE="$DIST_DIR/$APP_NAME"

echo "==> Building macOS Ghost Copilot bundle in $DIST_DIR..."

rm -rf "$APP_BUNDLE"
mkdir -p "$APP_BUNDLE/Contents/MacOS"
mkdir -p "$APP_BUNDLE/Contents/Resources"
mkdir -p "$APP_BUNDLE/Contents/SharedSupport"

export PATH="/Library/Developer/CommandLineTools/usr/bin:$PATH"

# 1. Compile native Cocoa/WebKit Mach-O binary (or use precompiled binary if clang is unavailable)
echo "==> Resolving native Cocoa stealth window binary..."
SDK_PATH="/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk"
SYSROOT_FLAG=""
if [ -d "$SDK_PATH" ]; then
    SYSROOT_FLAG="-isysroot $SDK_PATH"
fi
if /Library/Developer/CommandLineTools/usr/bin/clang $SYSROOT_FLAG -O2 -framework Cocoa -framework WebKit -framework QuartzCore -o "$APP_BUNDLE/Contents/MacOS/ghost_copilot" "$REPO_ROOT/ghost_copilot.m" 2>/dev/null; then
    echo "    Compiled freshly from ghost_copilot.m with clang."
    cp "$APP_BUNDLE/Contents/MacOS/ghost_copilot" "$REPO_ROOT/ghost_copilot"
elif [ -f "$REPO_ROOT/ghost_copilot" ]; then
    echo "    Clang compilation failed; using precompiled Mach-O binary from repository root."
    cp "$REPO_ROOT/ghost_copilot" "$APP_BUNDLE/Contents/MacOS/ghost_copilot"
    chmod +x "$APP_BUNDLE/Contents/MacOS/ghost_copilot"
else
    echo "ERROR: Neither clang nor precompiled ghost_copilot binary found!" >&2
    exit 1
fi
ln -sf "ghost_copilot" "$APP_BUNDLE/Contents/MacOS/ghost_copilot_bin"

# 2. Copy launcher script
echo "==> Copying launcher script..."
cat << 'EOF' > "$APP_BUNDLE/Contents/MacOS/Ghost Copilot"
#!/usr/bin/env bash
DIR="$(cd "$(dirname "$0")/../SharedSupport" && pwd)"
cd "$DIR"

pkill -9 -f "app.py" 2>/dev/null || true
pkill -9 -f "ghost_copilot" 2>/dev/null || true
sleep 0.2

# 1. Prefer embedded Python runtime inside bundle Frameworks
if [ -x "$DIR/../Frameworks/Python.framework/Versions/3.11/bin/python3" ]; then
    PY="$DIR/../Frameworks/Python.framework/Versions/3.11/bin/python3"
elif [ -x "$DIR/../Frameworks/Python.framework/Versions/Current/bin/python3" ]; then
    PY="$DIR/../Frameworks/Python.framework/Versions/Current/bin/python3"
elif [ -x "$DIR/.venv/bin/python3" ]; then
    PY="$DIR/.venv/bin/python3"
elif command -v python3 >/dev/null 2>&1; then
    PY="$(command -v python3)"
elif [ -x "/opt/homebrew/bin/python3" ]; then
    PY="/opt/homebrew/bin/python3"
elif [ -x "/usr/local/bin/python3" ]; then
    PY="/usr/local/bin/python3"
else
    PY="/usr/bin/python3"
fi

# Ensure bundled site-packages and app modules are discoverable
export PYTHONPATH="$DIR:$DIR/.venv/lib/python3.11/site-packages:${PYTHONPATH:-}"

# Ensure bundled MacOS bin directory (ffmpeg) is at the front of PATH
export PATH="$(cd "$(dirname "$0")" && pwd):$PATH"

# Start AI Engine
"$PY" app.py &
APP_PID=$!

# Wait for session token or engine readiness
for _ in {1..20}; do
    if [ -f "$HOME/.ghost_copilot/session_token" ]; then
        break
    fi
    sleep 0.1
done

# Start native Cocoa window (NSWindowSharingNone)
"$DIR/../MacOS/ghost_copilot"

# Cleanup on exit
kill -9 "$APP_PID" 2>/dev/null || true
EOF
chmod +x "$APP_BUNDLE/Contents/MacOS/Ghost Copilot"

# 3. Copy Application Metadata & Icon
echo "==> Packaging Info.plist and application icon..."
if [ -f "$REPO_ROOT/Ghost Copilot.app/Contents/Info.plist" ]; then
    cp "$REPO_ROOT/Ghost Copilot.app/Contents/Info.plist" "$APP_BUNDLE/Contents/"
fi

if [ -f "$REPO_ROOT/ghost_copilot.icns" ]; then
    cp "$REPO_ROOT/ghost_copilot.icns" "$APP_BUNDLE/Contents/Resources/AppIcon.icns"
    cp "$REPO_ROOT/ghost_copilot.icns" "$APP_BUNDLE/Contents/Resources/ghost_copilot.icns"
    cp "$REPO_ROOT/ghost_copilot.icns" "$APP_BUNDLE/Contents/MacOS/ghost_copilot.icns"
fi

# 4. Copy backend and shared modules
echo "==> Bundling application source modules..."
cp "$REPO_ROOT/app.py" "$APP_BUNDLE/Contents/SharedSupport/"
cp -r "$REPO_ROOT/client" "$APP_BUNDLE/Contents/SharedSupport/"
cp -r "$REPO_ROOT/server" "$APP_BUNDLE/Contents/SharedSupport/"
cp -r "$REPO_ROOT/desktop" "$APP_BUNDLE/Contents/SharedSupport/"
cp -r "$REPO_ROOT/shared" "$APP_BUNDLE/Contents/SharedSupport/"
# Backward-compatibility fallback for direct MacOS/ invocations
cp "$REPO_ROOT/app.py" "$APP_BUNDLE/Contents/MacOS/app.py"
cp -r "$REPO_ROOT/server" "$APP_BUNDLE/Contents/MacOS/"
cp -r "$REPO_ROOT/shared" "$APP_BUNDLE/Contents/MacOS/"

# 5. Embed Standalone Python Runtime and Relocatable FFmpeg
echo "==> Embedding standalone Python framework and relocatable FFmpeg..."
if [ -f "$SCRIPT_DIR/bundle_dependencies.py" ]; then
    "$REPO_ROOT/.venv/bin/python3" "$SCRIPT_DIR/bundle_dependencies.py" "$APP_BUNDLE"
fi

# Purge any stale developer bytecode caches
find "$APP_BUNDLE" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

echo "==> Ad-hoc signing bundle..."
codesign --force --deep --sign - "$APP_BUNDLE" 2>/dev/null || true

echo "==> SUCCESS: $APP_NAME cleanly assembled at: $APP_BUNDLE"
