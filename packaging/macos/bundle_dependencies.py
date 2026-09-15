#!/usr/bin/env python3
"""
macOS Application Bundle Dependency Packager.
Embeds a standalone Python runtime and relocatable FFmpeg binary with all
dynamic dylib dependencies into Ghost Copilot.app.
"""

import os
import sys
import shutil
import subprocess
import re
from pathlib import Path

OTOOL = "/Library/Developer/CommandLineTools/usr/bin/otool"
INSTALL_NAME_TOOL = "/Library/Developer/CommandLineTools/usr/bin/install_name_tool"
CODESIGN = "/usr/bin/codesign"

if not os.path.exists(OTOOL):
    OTOOL = "otool"
if not os.path.exists(INSTALL_NAME_TOOL):
    INSTALL_NAME_TOOL = "install_name_tool"

def get_non_system_deps(macho_path: str) -> list[str]:
    """Extracts non-system dylib dependencies from a Mach-O binary."""
    res = subprocess.run([OTOOL, "-L", macho_path], stdout=subprocess.PIPE, text=True, check=True)
    deps = []
    for line in res.stdout.splitlines()[1:]:
        m = re.match(r'\s+([^\s]+)', line)
        if m:
            dep = m.group(1)
            if not dep.startswith(("/System/", "/usr/lib/")):
                deps.append(dep)
    return deps

def bundle_ffmpeg(app_bundle: Path):
    """Bundles FFmpeg and all its required dylibs into the app bundle."""
    print("==> [Bundle] Packaging FFmpeg and dynamic libraries...")
    macos_dir = app_bundle / "Contents" / "MacOS"
    frameworks_dir = app_bundle / "Contents" / "Frameworks"
    macos_dir.mkdir(parents=True, exist_ok=True)
    frameworks_dir.mkdir(parents=True, exist_ok=True)

    src_ffmpeg = "/opt/homebrew/bin/ffmpeg"
    if not os.path.exists(src_ffmpeg):
        # Fallback to which
        src_ffmpeg = shutil.which("ffmpeg")
    
    if not src_ffmpeg or not os.path.exists(src_ffmpeg):
        print("    [WARNING] No source FFmpeg found to bundle.")
        return

    dest_ffmpeg = macos_dir / "ffmpeg"
    shutil.copy2(src_ffmpeg, dest_ffmpeg)
    os.chmod(dest_ffmpeg, 0o755)
    print(f"    Copied FFmpeg binary -> {dest_ffmpeg}")

    # Discover all recursive dylibs
    discovered_dylibs = {} # realpath -> target filename
    queue = [str(dest_ffmpeg)]
    seen_sources = set()

    while queue:
        curr = queue.pop(0)
        try:
            deps = get_non_system_deps(curr)
        except Exception:
            continue
        for dep in deps:
            if dep.startswith(("@rpath", "@loader_path", "@executable_path")):
                continue
            real_dep = os.path.realpath(dep)
            if os.path.exists(real_dep) and real_dep not in seen_sources:
                seen_sources.add(real_dep)
                fname = os.path.basename(real_dep)
                discovered_dylibs[real_dep] = fname
                queue.append(real_dep)

    print(f"    Discovered {len(discovered_dylibs)} dependent dylibs.")

    # Copy dylibs into Frameworks
    for real_src, fname in discovered_dylibs.items():
        dst = frameworks_dir / fname
        if not dst.exists():
            shutil.copy2(real_src, dst)
            os.chmod(dst, 0o755)

    # Also make sure aliases/symlinks from original dependency names exist
    for real_src, fname in discovered_dylibs.items():
        base_orig = os.path.basename(real_src)
        # Check if original was e.g. libavcodec.62.dylib pointing to libavcodec.62.11.100.dylib
        # Find any references that matched original alias
        alias_name = re.sub(r'(\.\d+)\.\d+\.\d+\.dylib$', r'\1.dylib', base_orig)
        if alias_name != base_orig:
            alias_path = frameworks_dir / alias_name
            if not alias_path.exists():
                try:
                    os.symlink(base_orig, alias_path)
                except Exception:
                    shutil.copy2(frameworks_dir / base_orig, alias_path)

    # Fix install names and references in all dylibs
    for dylib_file in frameworks_dir.glob("*.dylib"):
        if dylib_file.is_symlink():
            continue
        # Set dylib ID to @rpath/<filename>
        try:
            subprocess.run([INSTALL_NAME_TOOL, "-id", f"@rpath/{dylib_file.name}", str(dylib_file)], check=False)
        except Exception:
            pass

        # Rewrite references
        deps = get_non_system_deps(str(dylib_file))
        for dep in deps:
            if dep.startswith(("@rpath", "@loader_path", "@executable_path")):
                continue
            real = os.path.realpath(dep)
            target_fname = os.path.basename(real)
            subprocess.run([
                INSTALL_NAME_TOOL, "-change", dep,
                f"@loader_path/{target_fname}", str(dylib_file)
            ], check=False)

    # Fix FFmpeg binary dependencies and add rpath
    subprocess.run([INSTALL_NAME_TOOL, "-add_rpath", "@executable_path/../Frameworks", str(dest_ffmpeg)], check=False)
    ffmpeg_deps = get_non_system_deps(str(dest_ffmpeg))
    for dep in ffmpeg_deps:
        if dep.startswith(("@rpath", "@loader_path", "@executable_path")):
            continue
        real = os.path.realpath(dep)
        target_fname = os.path.basename(real)
        subprocess.run([
            INSTALL_NAME_TOOL, "-change", dep,
            f"@executable_path/../Frameworks/{target_fname}", str(dest_ffmpeg)
        ], check=False)

    # Re-sign bundled Mach-O files with ad-hoc signature
    for f in frameworks_dir.glob("*.dylib"):
        if not f.is_symlink():
            subprocess.run([CODESIGN, "-f", "-s", "-", str(f)], stderr=subprocess.DEVNULL, check=False)
    subprocess.run([CODESIGN, "-f", "-s", "-", str(dest_ffmpeg)], stderr=subprocess.DEVNULL, check=False)
    print("    FFmpeg binary and dynamic libraries successfully bundled and relocated.")

def bundle_python_runtime(app_bundle: Path, repo_root: Path):
    """Embeds Python.framework and project virtualenv packages into the app bundle."""
    print("==> [Bundle] Packaging standalone Python runtime...")
    frameworks_dir = app_bundle / "Contents" / "Frameworks"
    shared_support_dir = app_bundle / "Contents" / "SharedSupport"
    frameworks_dir.mkdir(parents=True, exist_ok=True)
    shared_support_dir.mkdir(parents=True, exist_ok=True)

    src_py_framework = Path("/opt/homebrew/opt/python@3.11/Frameworks/Python.framework")
    dst_py_framework = frameworks_dir / "Python.framework"

    if src_py_framework.exists() and not dst_py_framework.exists():
        print(f"    Copying Python.framework ({src_py_framework}) -> {dst_py_framework}...")
        # Copy framework without test suites to save space
        shutil.copytree(
            src_py_framework, dst_py_framework,
            symlinks=True,
            ignore=shutil.ignore_patterns("test", "tests", "idlelib", "tkinter", "turtle*")
        )

        py_dylib = dst_py_framework / "Versions" / "3.11" / "Python"
        if py_dylib.exists():
            subprocess.run([INSTALL_NAME_TOOL, "-id", "@rpath/Python.framework/Versions/3.11/Python", str(py_dylib)], check=False)
            subprocess.run([CODESIGN, "-f", "-s", "-", str(py_dylib)], stderr=subprocess.DEVNULL, check=False)

        bin_dir = dst_py_framework / "Versions" / "3.11" / "bin"
        py_bin = bin_dir / "python3.11"
        if py_bin.exists():
            # Create python3 and python symlinks if missing
            py3_sym = bin_dir / "python3"
            if not py3_sym.exists():
                try: os.symlink("python3.11", py3_sym)
                except Exception: shutil.copy2(py_bin, py3_sym)
            
            # Rewrite Python dylib path in the python binary
            deps = get_non_system_deps(str(py_bin))
            for dep in deps:
                if "Python" in dep:
                    subprocess.run([
                        INSTALL_NAME_TOOL, "-change", dep,
                        "@executable_path/../Python", str(py_bin)
                    ], check=False)
                    if py3_sym.is_file() and not py3_sym.is_symlink():
                        subprocess.run([
                            INSTALL_NAME_TOOL, "-change", dep,
                            "@executable_path/../Python", str(py3_sym)
                        ], check=False)

            subprocess.run([INSTALL_NAME_TOOL, "-add_rpath", "@executable_path/../../..", str(py_bin)], check=False)
            subprocess.run([CODESIGN, "-f", "-s", "-", str(py_bin)], stderr=subprocess.DEVNULL, check=False)
        
        # Ensure Versions/Current symlink exists
        versions_dir = dst_py_framework / "Versions"
        current_sym = versions_dir / "Current"
        if not current_sym.exists():
            try: os.symlink("3.11", current_sym)
            except Exception: pass

        print("    Embedded Python.framework successfully relocated.")
    elif dst_py_framework.exists():
        print("    Python.framework already embedded in Frameworks.")

    # Embed site-packages into SharedSupport/.venv/lib/python3.11/site-packages
    src_site_packages = repo_root / ".venv" / "lib" / "python3.11" / "site-packages"
    dst_venv_dir = shared_support_dir / ".venv"
    dst_site_packages = dst_venv_dir / "lib" / "python3.11" / "site-packages"

    if src_site_packages.exists():
        print("    Bundling project dependencies into SharedSupport/.venv...")
        dst_site_packages.mkdir(parents=True, exist_ok=True)
        # Copy required packages
        for item in src_site_packages.iterdir():
            target = dst_site_packages / item.name
            if not target.exists():
                if item.is_dir():
                    shutil.copytree(item, target, symlinks=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
                else:
                    shutil.copy2(item, target)
        
        # Also copy .venv/bin pyvenv.cfg
        cfg = repo_root / ".venv" / "pyvenv.cfg"
        if cfg.exists():
            shutil.copy2(cfg, dst_venv_dir / "pyvenv.cfg")

        print("    Bundled dependencies into SharedSupport/.venv.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <path_to_Ghost Copilot.app>")
        sys.exit(1)
    bundle_path = Path(sys.argv[1]).resolve()
    repo_path = Path(__file__).resolve().parent.parent.parent
    bundle_python_runtime(bundle_path, repo_path)
    bundle_ffmpeg(bundle_path)
    print("==> Bundle dependency packaging completed.")
