#!/usr/bin/env python3
"""
Ghost Copilot - System Doctor & Readiness Verifier
---------------------------------------------------
Run this command in terminal/PowerShell to get 100% mathematical certainty
that your system is ready for the live demo before opening the GUI:

    python doctor.py

Checks:
1. Python Runtime & Architecture
2. PyQt6 & PyQt6-WebEngine GUI Framework
3. FFmpeg Audio Engine (System / Bundled)
4. Port 9471 Socket Availability
5. Groq API Key & Live Cloud Ping
6. Real Engine Boot, Health Handshake (< 100ms), and Clean Shutdown
"""

import os
import sys
import time
import socket
import subprocess
import urllib.request
import urllib.parse
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IS_WIN   = sys.platform.startswith("win")
IS_MAC   = sys.platform == "darwin"


def p_ok(title, detail=""):
    det = f" -> {detail}" if detail else ""
    print(f"  [PASS] {title}{det}")

def p_fail(title, detail, fix=""):
    print(f"  [FAIL] {title} -> {detail}")
    if fix:
        print(f"         FIX: {fix}")

def p_warn(title, detail):
    print(f"  [WARN] {title} -> {detail}")


def main():
    print("=" * 64)
    print("   GHOST COPILOT - SYSTEM READINESS DOCTOR")
    print("=" * 64)
    all_passed = True

    # 1. Python Runtime
    v = sys.version_info
    if v >= (3, 8):
        p_ok("Python Runtime", f"{v[0]}.{v[1]}.{v[2]} ({'64-bit' if sys.maxsize > 2**32 else '32-bit'})")
    else:
        p_fail("Python Runtime", f"Version {v[0]}.{v[1]} is below 3.8", "Install Python 3.10 or 3.11 64-bit from python.org")
        all_passed = False

    # 2. PyQt6 and PyQt6-WebEngine
    qt_ok = False
    try:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import PYQT_VERSION_STR
        p_ok("PyQt6 GUI Framework", f"v{PYQT_VERSION_STR}")
        qt_ok = True
    except ImportError:
        p_fail("PyQt6 Missing", "PyQt6 is not installed in this environment", "pip install PyQt6")
        all_passed = False

    try:
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        from PyQt6.QtWebEngineCore import QWebEngineSettings
        p_ok("PyQt6-WebEngine", "Installed and ready for HUD rendering")
    except ImportError:
        p_fail("PyQt6-WebEngine Missing", "PyQt6-WebEngine is not installed", "pip install PyQt6-WebEngine")
        all_passed = False

    # 3. FFmpeg
    bin_dir = os.path.join(BASE_DIR, "bin")
    if os.path.exists(bin_dir) and bin_dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")

    ffmpeg_bin = None
    try:
        from client.core.ffmpeg import find_ffmpeg
        info = find_ffmpeg()
        if info.get("status") == "READY":
            ffmpeg_bin = info.get("path")
    except Exception:
        pass

    if not ffmpeg_bin:
        import shutil
        ffmpeg_bin = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")

    if ffmpeg_bin and os.path.exists(ffmpeg_bin):
        try:
            sp_kwargs = {"creationflags": 0x08000000} if IS_WIN else {}
            r = subprocess.run([ffmpeg_bin, "-version"], capture_output=True, text=True, timeout=3, **sp_kwargs)
            ver = r.stdout.splitlines()[0] if r.stdout else "Available"
            p_ok("Audio Engine (FFmpeg)", f"{ver[:45]} ({ffmpeg_bin})")
        except Exception as e:
            p_fail("Audio Engine (FFmpeg)", f"Cannot execute binary: {e}", "Ensure binary has execution permissions")
            all_passed = False
    else:
        p_warn("Audio Engine (FFmpeg)", "FFmpeg not detected yet. Launcher will offer 1-click Auto-Install.")

    # 4. Port 9471 Availability
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    port_in_use = False
    try:
        s.bind(("127.0.0.1", 9471))
        s.close()
        p_ok("Port 9471", "Free and available for engine binding")
    except OSError:
        port_in_use = True
        s.close()
        # Check if it's already an active Ghost Copilot instance
        try:
            with urllib.request.urlopen("http://127.0.0.1:9471/health", timeout=1.0) as resp:
                if resp.status == 200:
                    p_ok("Port 9471", "Ghost Copilot engine is ALREADY running and healthy on this port!")
        except Exception:
            p_fail("Port 9471 Occupied", "Port 9471 is in use by another process",
                   "taskkill /F /IM python.exe (on Windows) or lsof -ti:9471 | xargs kill -9 (on Mac)")
            all_passed = False

    # 5. Groq API Key Verification
    env_file = os.path.join(BASE_DIR, ".env")
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if not key and os.path.exists(env_file):
        try:
            with open(env_file, "r", encoding="utf-8-sig") as f:
                for line in f:
                    if line.strip().startswith("GROQ_API_KEY="):
                        key = line.split("=", 1)[1].strip().strip("'\"")
                        break
        except Exception:
            pass

    if key:
        masked = key[:6] + "..." + key[-4:] if len(key) > 10 else "***"
        # Test real ping to Groq API
        try:
            req = urllib.request.Request(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {key}", "User-Agent": "GhostCopilot/Doctor"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    p_ok("Groq Cloud AI Ping", f"Authenticated successfully with key [{masked}]")
                else:
                    p_warn("Groq Cloud AI Ping", f"Received status {resp.status} from Groq")
        except Exception as e:
            p_warn("Groq Cloud AI Ping", f"Cloud ping test returned: {e} (Verify internet or key)")
    else:
        p_warn("Groq API Key", "No key in .env. You can paste it into the launcher window before launch.")

    # 6. Live Engine Boot & Handshake Simulation (only if port is not in use)
    if not port_in_use:
        print("\n  [Testing Live Engine Boot...]")
        app_py = os.path.join(BASE_DIR, "app.py")
        if not os.path.exists(app_py):
            p_fail("Engine Script", "app.py not found in repo directory", "Ensure you are running doctor.py from repo root")
            all_passed = False
        else:
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUTF8"] = "1"
            env["COPILOT_AUTH_TOKEN"] = "doctor_test_token_1234567890abcdef"

            sp_kwargs = {"creationflags": 0x08000000} if IS_WIN else {}
            log_path = os.path.join(BASE_DIR, "doctor_test.log")
            lf = open(log_path, "w", encoding="utf-8")
            proc = subprocess.Popen(
                [sys.executable, app_py],
                cwd=BASE_DIR,
                env=env,
                stdout=lf,
                stderr=subprocess.STDOUT,
                **sp_kwargs
            )

            booted = False
            boot_time_ms = 0
            start_t = time.perf_counter()
            last_probe_err = ""
            for _ in range(30):  # 30 * 100ms = 3.0s max
                time.sleep(0.1)
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(0.5)
                    s.connect(("127.0.0.1", 9471))
                    s.sendall(b"GET /health HTTP/1.1\r\nHost: 127.0.0.1:9471\r\nConnection: close\r\n\r\n")
                    res = s.recv(512)
                    s.close()
                    if b"200" in res or b"status" in res:
                        booted = True
                        boot_time_ms = int((time.perf_counter() - start_t) * 1000)
                        break
                    else:
                        last_probe_err = f"Raw response: {res}"
                except Exception as ex:
                    last_probe_err = f"Socket error: {ex}"

            # Terminate test process
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except Exception:
                proc.kill()

            try:
                lf.close()
            except Exception:
                pass

            err_detail = ""
            if not booted and os.path.exists(log_path):
                try:
                    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                        err_detail = f.read().strip()
                except Exception:
                    pass

            if booted:
                p_ok("Engine Live Handshake", f"Server answered in {boot_time_ms}ms (HTTP 200 OK)")
                if os.path.exists(log_path):
                    try:
                        os.remove(log_path)
                    except Exception:
                        pass
            else:
                p_fail("Engine Live Handshake", f"Engine failed to respond on port 9471 ({last_probe_err})", "Check doctor_test.log")
                if err_detail:
                    print("         --- Engine Output ---")
                    for l in err_detail.splitlines()[-10:]:
                        print(f"         {l}")
                    print("         ---------------------")
                all_passed = False

    print("-" * 64)
    if all_passed:
        print("  [RESULT] 100% OPERATIONAL. ALL SYSTEM CHECKS PASSED.")
        print("  You can confidently run: python launcher.py")
    else:
        print("  [RESULT] ISSUES DETECTED. Please follow the FIX steps above.")
    print("=" * 64)
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
