#!/bin/bash
# Ghost Copilot Launcher — macOS double-click starter (.command file)
# chmod +x this file so Finder can open it with a double-click.
# No personal info. No web browser. Pure desktop.

cd "$(dirname "$0")"

# ── Find Python ───────────────────────────────────────────────────────────────
PY=""
for candidate in python3 python3.12 python3.11 python3.10 python3.9; do
    if command -v "$candidate" &>/dev/null; then
        PY="$candidate"
        break
    fi
done

if [ -z "$PY" ]; then
    osascript -e 'display dialog "Python 3 not found.\n\nInstall it from python.org or with Homebrew:\n  brew install python" buttons {"OK"} with title "Ghost Copilot"'
    exit 1
fi

# ── Check PyQt6 installed ─────────────────────────────────────────────────────
if ! "$PY" -c "import PyQt6" 2>/dev/null; then
    echo "Installing PyQt6..."
    "$PY" -m pip install --quiet --upgrade PyQt6 PyQt6-WebEngine
    if [ $? -ne 0 ]; then
        osascript -e 'display dialog "Could not install PyQt6.\n\nRun in Terminal:\n  pip install PyQt6 PyQt6-WebEngine" buttons {"OK"} with title "Ghost Copilot"'
        exit 1
    fi
fi

# ── Launch ────────────────────────────────────────────────────────────────────
"$PY" "$(dirname "$0")/launcher.py"
