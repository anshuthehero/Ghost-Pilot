# -*- mode: python ; coding: utf-8 -*-
# ==============================================================================
# PyInstaller Build Specification for Ghost Copilot Windows Client
# Bundles PyQt6 WebEngine, client API, WASAPI audio drivers, and assets.
# Usage on Windows: pyinstaller packaging/windows/ghost_copilot.spec
# ==============================================================================

import os
import sys

block_cipher = None

repo_root = os.path.abspath(os.path.join(SPECPATH, "..", ".."))

added_files = [
    (os.path.join(repo_root, "shared"), "shared"),
    (os.path.join(repo_root, "client"), "client"),
    (os.path.join(repo_root, "desktop"), "desktop"),
]

if os.path.exists(os.path.join(repo_root, "app.py")):
    added_files.append((os.path.join(repo_root, "app.py"), "."))

if os.path.exists(os.path.join(repo_root, "icon.jpg")):
    added_files.append((os.path.join(repo_root, "icon.jpg"), "."))

if os.path.exists(os.path.join(repo_root, "bin", "windows", "ffmpeg.exe")):
    added_files.append((os.path.join(repo_root, "bin", "windows", "ffmpeg.exe"), "bin"))

hidden_deps = [
    "client.core.config",
    "client.core.errors",
    "client.core.ffmpeg",
    "client.audio.base",
    "client.audio.manager",
    "client.platform.windows.audio",
    "client.platform.windows.client",
    "client.diagnostics.preflight",
    "client.api.client",
    "desktop",
    "desktop.audio",
    "desktop.audio.capture",
    "desktop.clipboard",
    "desktop.clipboard.watcher",
    "shared.schemas",
]
try:
    import PyQt6
    hidden_deps.extend(["PyQt6", "PyQt6.QtCore", "PyQt6.QtGui", "PyQt6.QtWidgets", "PyQt6.QtWebEngineWidgets", "PyQt6.QtWebEngineCore"])
except ImportError:
    try:
        import PyQt5
        hidden_deps.extend(["PyQt5", "PyQt5.QtCore", "PyQt5.QtGui", "PyQt5.QtWidgets", "PyQt5.QtWebEngineWidgets"])
    except ImportError:
        pass

a = Analysis(
    [os.path.join(repo_root, "client", "platform", "windows", "client.py")],
    pathex=[repo_root],
    binaries=[],
    datas=added_files,
    hiddenimports=hidden_deps,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "scipy", "notebook", "pandas"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
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
    console=False,  # Windowed GUI application (no persistent command prompt)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(repo_root, "icon.jpg") if os.path.exists(os.path.join(repo_root, "icon.jpg")) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="GhostCopilot",
)
