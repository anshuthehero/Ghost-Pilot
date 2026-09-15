"""
Client Preflight & Diagnostic Readiness Engine.
Audits runtime dependencies, audio capabilities, permissions, and backend connectivity.
Provides actionable user guidance without blocking startup unnecessarily.
"""

import os
import sys

# Ensure repository root is on sys.path when executed directly
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import shutil
import platform
import subprocess
from typing import Dict, Any, List, Optional
from client.core.config import ClientConfig
from client.core.ffmpeg import find_ffmpeg
from client.audio.manager import get_audio_provider
from client.audio.base import AudioState


class PreflightChecker:
    def __init__(self, config: Optional[ClientConfig] = None):
        self.config = config or ClientConfig()
        self.audio_provider = get_audio_provider()

    def check_system_environment(self) -> Dict[str, Any]:
        """Detects host operating system, architecture, and Python runtime."""
        arch = platform.machine().lower()
        if sys.platform == "darwin":
            os_ver = platform.mac_ver()[0] or "Unknown macOS"
            friendly_arch = "Apple Silicon" if "arm" in arch else "Intel (x86_64)"
        elif sys.platform.startswith("win"):
            os_ver = f"Windows {platform.win32_ver()[0]}"
            friendly_arch = "ARM64" if "arm" in arch else "x64"
        else:
            os_ver = platform.system()
            friendly_arch = arch

        return {
            "platform": self.config.platform,
            "os_version": os_ver,
            "architecture": friendly_arch,
            "raw_arch": arch,
            "python_version": sys.version.split()[0],
            "python_executable": sys.executable,
        }

    def check_ffmpeg(self) -> Dict[str, Any]:
        """Audits FFmpeg binary availability and execution capabilities."""
        res = find_ffmpeg()
        return {
            "status": res["status"],
            "path": res["path"],
            "version": res.get("version"),
            "bundled": res.get("is_bundled", False),
            "user_hint": res.get("user_hint")
        }

    def check_permissions(self) -> Dict[str, Any]:
        """Evaluates hardware and OS privacy permissions."""
        if sys.platform == "darwin":
            # On macOS, microphone access is governed by TCC
            return {
                "microphone": {
                    "status": "OPTIONAL_OR_READY",
                    "what": "Microphone Access",
                    "why": "Required for candidate push-to-talk voice input",
                    "how": "macOS System Settings -> Privacy & Security -> Microphone"
                },
                "screen_audio": {
                    "status": "OPTIONAL",
                    "what": "Screen & System Audio Recording",
                    "why": "Required by macOS when BlackHole loopback captures system sound",
                    "how": "macOS System Settings -> Privacy & Security -> Screen & System Audio Recording"
                }
            }
        elif sys.platform.startswith("win"):
            return {
                "microphone": {
                    "status": "READY",
                    "what": "Microphone Access",
                    "why": "Required for voice input",
                    "how": "Windows Settings -> Privacy & Security -> Microphone"
                },
                "loopback": {
                    "status": "READY",
                    "what": "WASAPI Render Loopback",
                    "why": "Standard user permissions allow WASAPI process loopback",
                    "how": "No special permissions needed for standard audio output capture"
                }
            }
        return {}

    def check_backend_connectivity(self) -> Dict[str, Any]:
        """Pings the local/remote backend /health endpoint."""
        from client.api.client import CopilotApiClient
        client = CopilotApiClient(self.config)
        try:
            health = client.check_health()
            ready = client.check_readiness()
            return {
                "status": "READY",
                "backend_url": self.config.backend_url,
                "health": health,
                "readiness": ready
            }
        except Exception as e:
            return {
                "status": "UNAVAILABLE",
                "backend_url": self.config.backend_url,
                "error": str(e),
                "what": "Backend Server Unreachable",
                "why": f"Cannot connect to {self.config.backend_url}",
                "how": "Start local backend (uvicorn server.main:app --port 9471) or verify network connectivity.",
                "user_hint": "Backend server is not running or unreachable. Starting local in-process backend..."
            }

    def run_full_audit(self) -> Dict[str, Any]:
        """Runs the complete preflight readiness check."""
        env_info = self.check_system_environment()
        ffmpeg_info = self.check_ffmpeg()
        audio_caps = self.audio_provider.check_capabilities()
        perms_info = self.check_permissions()
        backend_info = self.check_backend_connectivity()

        # Evaluate readiness semantics accurately
        can_run = (ffmpeg_info["status"] == "READY")
        backend_connected = (backend_info["status"] == "READY")
        system_audio_ready = (audio_caps.get("system_audio", {}).get("state") == "READY")

        if not can_run:
            overall_status = "ACTION_REQUIRED"
            recommendation = "FFmpeg is missing or not executable. Install FFmpeg before running Interview Assistant."
        elif backend_connected and system_audio_ready:
            overall_status = "FULL_STACK_READY"
            recommendation = "Interview Assistant is fully ready (all local dependencies verified and backend server active)."
        elif backend_connected and not system_audio_ready:
            overall_status = "DEGRADED_READY"
            recommendation = "Interview Assistant is running in Microphone-Only mode. Backend server is active; configure system audio in Audio MIDI Setup when convenient."
        else:
            overall_status = "DESKTOP_READY"
            recommendation = "Desktop environment is ready. Backend server is currently offline (will launch automatically with desktop app, or run: uvicorn server.main:app --port 9471)."

        # Compile actionable guidance
        issues: List[Dict[str, str]] = []
        if ffmpeg_info["status"] != "READY":
            issues.append({
                "component": "FFmpeg",
                "what": "FFmpeg executable is missing or not runnable",
                "why": "FFmpeg is essential for audio capture, volume normalization, and format conversion",
                "how": ffmpeg_info.get("user_hint", "Install ffmpeg on your system")
            })

        sys_aud = audio_caps.get("system_audio", {})
        if sys_aud.get("state") not in ("READY", "OPTIONAL"):
            issues.append({
                "component": "System Audio",
                "what": f"System audio loopback state is {sys_aud.get('state')}",
                "why": "Interviewer questions cannot be captured directly from system speakers",
                "how": sys_aud.get("user_hint", "Check audio drivers and multi-output settings")
            })

        if not backend_connected:
            issues.append({
                "component": "Backend Server",
                "what": f"Backend server offline at {self.config.backend_url}",
                "why": "Standalone preflight doctor was run without an active backend server.",
                "how": "Launch the desktop app (which starts the local backend automatically) or run: uvicorn server.main:app --port 9471"
            })

        return {
            "platform": self.config.platform,
            "environment": env_info,
            "python_version": env_info["python_version"],
            "client_version": self.config.client_version,
            "overall_status": overall_status,
            "backend_connected": backend_connected,
            "can_start_application": True,  # Non-blocking startup policy
            "components": {
                "ffmpeg": ffmpeg_info,
                "audio": audio_caps,
                "permissions": perms_info,
                "backend": backend_info
            },
            "issues": issues,
            "recommendation": recommendation
        }


def print_doctor_report():
    """Human-readable CLI diagnosis for developers and packaging verification."""
    checker = PreflightChecker()
    report = checker.run_full_audit()
    env = report.get("environment", {})

    print("=" * 64)
    print("  🎙️ INTERVIEW ASSISTANT — SYSTEM DIAGNOSTIC DOCTOR")
    print("=" * 64)
    print(f"Platform:         {report['platform'].upper()} — {env.get('os_version', '')} ({env.get('architecture', '')})")
    print(f"Python Runtime:   {env.get('python_version', '')} ({env.get('python_executable', '')})")
    print(f"Client Version:   {report['client_version']}")
    print("-" * 64)
    
    # FFmpeg
    ff = report["components"]["ffmpeg"]
    ff_desc = ff.get("version") or ff.get("path") or ff.get("user_hint")
    print(f"FFmpeg Binary:    [{ff['status']}] {ff_desc}")

    # Audio
    aud = report["components"]["audio"]
    mic = aud.get("microphone", {})
    spk = aud.get("system_audio", {})
    print(f"Microphone:       [{mic.get('state', 'UNKNOWN')}] {mic.get('user_hint', '')}")
    print(f"System Audio:     [{spk.get('state', 'UNKNOWN')}] {spk.get('user_hint', '')}")

    # Backend
    be = report["components"]["backend"]
    print(f"Backend Server:   [{be['status']}] {be['backend_url']}")
    print("-" * 64)
    print(f"Readiness Status: {report['overall_status']}")
    print(f"Recommendation:   {report['recommendation']}")

    if report.get("issues"):
        print("\nACTIONABLE GUIDANCE:")
        for idx, issue in enumerate(report["issues"], 1):
            print(f"  {idx}. [{issue['component']}] {issue['what']}")
            print(f"     Why: {issue['why']}")
            print(f"     Fix: {issue['how']}")
    print("=" * 64)


if __name__ == "__main__":
    print_doctor_report()
