"""
Universal FFmpeg Discovery and Validation Engine.
Resolves FFmpeg across macOS (Apple Silicon & Intel) and Windows (x64 & ARM)
supporting bundled executables, package managers, and system PATH.
"""

import os
import sys
import shutil
import subprocess
from typing import Dict, Any, Optional, List


def find_ffmpeg() -> Dict[str, Any]:
    """
    Locates the most reliable FFmpeg binary across platforms.
    Search priority:
    1. Bundled inside application directory (standalone distribution)
    2. Package manager paths (Homebrew on macOS, WinGet/Chocolatey on Windows)
    3. System PATH
    4. Fallback well-known system directories
    """
    candidates: List[str] = []
    
    # 1. Bundled application paths
    app_dir = os.path.dirname(os.path.abspath(sys.executable))
    bin_name = "ffmpeg.exe" if sys.platform.startswith("win") else "ffmpeg"
    candidates.append(os.path.join(app_dir, bin_name))
    candidates.append(os.path.join(app_dir, "bin", bin_name))
    candidates.append(os.path.join(app_dir, "..", "MacOS", "ffmpeg"))
    candidates.append(os.path.join(app_dir, "..", "Resources", "ffmpeg"))

    # Check for macOS .app bundle structure around sys.executable and __file__
    for search_start in (app_dir, os.path.dirname(os.path.abspath(__file__))):
        curr = search_start
        for _ in range(7):
            if curr.endswith(".app") or curr.endswith(".app/Contents"):
                contents_dir = curr if curr.endswith("Contents") else os.path.join(curr, "Contents")
                candidates.append(os.path.join(contents_dir, "MacOS", bin_name))
                candidates.append(os.path.join(contents_dir, "Resources", bin_name))
                break
            # Check for binary directly in directory (e.g. user placed ffmpeg.exe in app folder)
            direct_bin = os.path.join(curr, bin_name)
            if os.path.isfile(direct_bin):
                candidates.append(direct_bin)
            # Check for repo-level bin/ directory
            plat_sub = "windows" if sys.platform.startswith("win") else "macos"
            repo_bin = os.path.join(curr, "bin", plat_sub, bin_name)
            if os.path.isfile(repo_bin):
                candidates.append(repo_bin)
            parent = os.path.dirname(curr)
            if parent == curr:
                break
            curr = parent

    # 2. System PATH
    try:
        which_bin = shutil.which("ffmpeg")
        if which_bin:
            candidates.append(which_bin)
    except Exception:
        pass

    # 3. Platform-specific well-known paths
    if sys.platform == "darwin":
        candidates.extend([
            "/opt/homebrew/bin/ffmpeg",       # Apple Silicon Homebrew
            "/usr/local/bin/ffmpeg",          # Intel Mac Homebrew / MacPorts
            "/usr/bin/ffmpeg",
        ])
    elif sys.platform.startswith("win"):
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        candidates.extend([
            os.path.join(local_app_data, "Microsoft", "WinGet", "Links", "ffmpeg.exe"),
            r"C:\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
            r"C:\ProgramData\chocolatey\bin\ffmpeg.exe",
        ])

    for candidate in candidates:
        if candidate and os.path.isfile(candidate) and (sys.platform.startswith("win") or os.access(candidate, os.X_OK)):
            # Validate binary responsiveness
            try:
                sp_kwargs = {"timeout": 2}
                if sys.platform.startswith("win"):
                    sp_kwargs["creationflags"] = 0x08000000
                r = subprocess.run([candidate, "-version"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, **sp_kwargs)
                if r.returncode == 0:
                    version_line = r.stdout.splitlines()[0] if r.stdout else "ffmpeg version unknown"
                    return {
                        "status": "READY",
                        "path": candidate,
                        "version": version_line,
                        "is_bundled": ("Contents" in candidate or app_dir in candidate)
                    }
            except Exception:
                continue

    # Missing binary guidance
    if sys.platform == "darwin":
        hint = "FFmpeg is required for audio capture & normalization. Install via: brew install ffmpeg"
    elif sys.platform.startswith("win"):
        hint = "FFmpeg is required for audio capture. Install via: winget install Gyan.FFmpeg or place ffmpeg.exe in app folder."
    else:
        hint = "Install ffmpeg using your system package manager (e.g. sudo apt install ffmpeg)."

    return {
        "status": "MISSING",
        "path": None,
        "version": None,
        "is_bundled": False,
        "user_hint": hint
    }


def get_ffmpeg_bin() -> str:
    """Returns the resolved executable path or fallback binary name string."""
    info = find_ffmpeg()
    return info["path"] or "ffmpeg"
