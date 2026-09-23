# -*- mode: python ; coding: utf-8 -*-
# =============================================================================
# PyInstaller spec — macOS  →  dist/Ghost Copilot.app
# Build command (run from repo root on macOS):
#   pyinstaller packaging/macos/launcher_mac.spec --noconfirm --clean
# =============================================================================

import os
import sys

block_cipher = None
repo_root    = os.path.abspath(os.path.join(SPECPATH, "..", ".."))


# ── Data files bundled into the .app ─────────────────────────────────────────
datas = [
    (os.path.join(repo_root, "client"),  "client"),
    (os.path.join(repo_root, "desktop"), "desktop"),
    (os.path.join(repo_root, "server"),  "server"),
    (os.path.join(repo_root, "app.py"),  "."),
]

icon_path = os.path.join(repo_root, "icon.icns")
if not os.path.exists(icon_path):
    icon_path = None


# ── Hidden imports ────────────────────────────────────────────────────────────
hidden = [
    "PyQt6",
    "PyQt6.QtCore",
    "PyQt6.QtGui",
    "PyQt6.QtWidgets",
    "PyQt6.QtWebEngineWidgets",
    "PyQt6.QtWebEngineCore",
    "PyQt6.QtNetwork",
    "client.core.config",
    "client.diagnostics.preflight",
    "desktop.audio.capture",
    "email.mime.text",
    "email.mime.multipart",
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
]


a = Analysis(
    [os.path.join(repo_root, "launcher.py")],   # entry point = launcher wizard
    pathex=[repo_root],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "scipy", "notebook", "pandas", "PySide6"],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Ghost Copilot",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX not recommended on macOS (code-signing issues)
    console=False,
    argv_emulation=False,
    target_arch=None,   # set to "arm64" or "x86_64" to force single-arch
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="Ghost Copilot",
)

app = BUNDLE(
    coll,
    name="Ghost Copilot.app",
    icon=icon_path,
    bundle_identifier="com.ghostcopilot.app",
    info_plist={
        "NSPrincipalClass":               "NSApplication",
        "NSHighResolutionCapable":        True,
        "NSMicrophoneUsageDescription":   "Ghost Copilot uses your microphone for voice capture.",
        "NSScreenCaptureDescription":     "Ghost Copilot captures audio for transcription.",
        "CFBundleShortVersionString":     "3.0.0",
        "CFBundleVersion":                "3.0.0",
        "LSMinimumSystemVersion":         "11.0",
        "LSUIElement":                    False,
    },
)
