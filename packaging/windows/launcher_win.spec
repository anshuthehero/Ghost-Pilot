# -*- mode: python ; coding: utf-8 -*-
# =============================================================================
# PyInstaller spec — Windows  →  dist/GhostCopilot/GhostCopilot.exe
# Build command (run from repo root on Windows):
#   pyinstaller packaging/windows/launcher_win.spec --noconfirm --clean
# =============================================================================

import os
import sys

block_cipher = None
repo_root    = os.path.abspath(os.path.join(SPECPATH, "..", ".."))


# ── Data files bundled into the executable ────────────────────────────────────
datas = [
    (os.path.join(repo_root, "client"),  "client"),
    (os.path.join(repo_root, "desktop"), "desktop"),
    (os.path.join(repo_root, "server"),  "server"),
    (os.path.join(repo_root, "app.py"),  "."),
]

# Bundle local ffmpeg if present (optional — users can also install system-wide)
ffmpeg_win = os.path.join(repo_root, "bin", "ffmpeg.exe")
if os.path.exists(ffmpeg_win):
    datas.append((ffmpeg_win, "bin"))

icon_path = os.path.join(repo_root, "icon.ico")
if not os.path.exists(icon_path):
    icon_path = os.path.join(repo_root, "icon.jpg")
    if not os.path.exists(icon_path):
        icon_path = None


# ── Hidden imports (PyInstaller misses these via static analysis) ─────────────
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
    "client.platform.windows.client",
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
    # BUG-12 fix: uvloop requires libuv — excluded so uvicorn falls back to asyncio
]


a = Analysis(
    [os.path.join(repo_root, "launcher.py")],   # entry point = our launcher wizard
    pathex=[repo_root],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "scipy", "notebook", "pandas", "PySide6",
              "uvloop", "uvicorn.loops.uvloop"],   # BUG-12: libuv not bundleable on Windows
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="GhostCopilot",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # No black CMD window — pure GUI
    argv_emulation=False,
    icon=icon_path,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=["Qt*.dll", "*.pyd"],
    name="GhostCopilot",
)
