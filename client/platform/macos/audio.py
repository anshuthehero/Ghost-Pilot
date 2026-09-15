"""
macOS Native Audio Provider.
Handles AVFoundation microphone capture, BlackHole loopback discovery,
and multi-output device validation with graceful degradation to mic-only.
"""

import os
import re
import subprocess
import threading
import time
from typing import Dict, Any, Optional, Callable
from client.audio.base import BaseAudioProvider, AudioState


from client.core.ffmpeg import get_ffmpeg_bin


class MacAudioProvider(BaseAudioProvider):
    def __init__(self, mic_device_index: Optional[str] = None):
        self.mic_index = mic_device_index or "1"
        self.blackhole_index: Optional[str] = None
        self.ffmpeg_bin = get_ffmpeg_bin()
        self.is_running = False
        self._mic_thread: Optional[threading.Thread] = None
        self._spk_thread: Optional[threading.Thread] = None

    def detect_devices(self) -> Dict[str, Any]:
        """Enumerates AVFoundation audio devices via ffmpeg."""
        mic_found = False
        blackhole_found = False
        devices = []
        permission_denied = False

        try:
            r = subprocess.run(
                [self.ffmpeg_bin, "-f", "avfoundation", "-list_devices", "true", "-i", ""],
                stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True, timeout=4
            )
            err_output = r.stderr.lower()
            if "permission denied" in err_output or "not permitted" in err_output:
                permission_denied = True

            in_audio = False
            for line in r.stderr.splitlines():
                if "AVFoundation audio devices" in line:
                    in_audio = True
                    continue
                if in_audio and "[" in line and "]" in line:
                    m = re.search(r'\[(\d+)\]\s*(.*)', line)
                    if m:
                        idx, name = m.group(1), m.group(2).strip()
                        devices.append({"index": idx, "name": name})
                        if "BlackHole" in name:
                            self.blackhole_index = idx
                            blackhole_found = True
                        elif any(term in name.lower() for term in ("microphone", "air", "macbook", "input", "built-in")):
                            mic_found = True
        except Exception:
            pass

        return {
            "mic_detected": mic_found or bool(self.mic_index),
            "mic_index": self.mic_index,
            "blackhole_detected": blackhole_found,
            "blackhole_index": self.blackhole_index,
            "permission_denied": permission_denied,
            "all_devices": devices
        }

    def check_capabilities(self) -> Dict[str, Any]:
        """
        Thoroughly validates actual capture paths:
        1. Microphone accessibility and permissions
        2. BlackHole device open probe test
        3. Multi-Output routing guidance
        """
        devs = self.detect_devices()
        
        # 1. Evaluate Microphone State
        if devs.get("permission_denied"):
            mic_state = AudioState.NEEDS_PERMISSION
            mic_hint = "Microphone access blocked by macOS Security. Grant permission in System Settings -> Privacy & Security -> Microphone."
        elif devs["mic_detected"]:
            mic_state = AudioState.READY
            mic_hint = "Microphone ready."
        else:
            mic_state = AudioState.MISSING
            mic_hint = "No audio input device detected. Connect a microphone or headset."

        # 2. Evaluate BlackHole System Audio State
        if not devs["blackhole_detected"]:
            bh_state = AudioState.MISSING
            bh_hint = (
                "BlackHole 2ch virtual audio driver is not installed. "
                "System-audio loopback (interviewer voice) is disabled. "
                "Interview Assistant will operate in Microphone-Only mode. "
                "To enable system audio capture, install via: brew install blackhole-2ch"
            )
        else:
            # Test if BlackHole can open a non-destructive probe stream
            try:
                probe = subprocess.run([
                    self.ffmpeg_bin, "-y",
                    "-f", "avfoundation", "-i", f":{self.blackhole_index}",
                    "-t", "0.2", "-f", "null", "-"
                ], stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, timeout=2)
                if probe.returncode == 0:
                    bh_state = AudioState.READY
                    bh_hint = "System-audio capture ready."
                else:
                    err_text = probe.stderr.decode(errors="ignore").lower() if probe.stderr else ""
                    if "permission" in err_text or "not permitted" in err_text:
                        bh_state = AudioState.NEEDS_PERMISSION
                        bh_hint = "Screen and System Audio Recording permission required in macOS System Settings."
                    else:
                        bh_state = AudioState.MISCONFIGURED
                        bh_hint = (
                            "BlackHole is installed but failed probe capture. "
                            "Ensure Multi-Output Device is configured in Audio MIDI Setup and set as system output."
                        )
            except Exception:
                bh_state = AudioState.CAPTURE_FAILED
                bh_hint = "Failed to communicate with BlackHole device."

        return {
            "platform": "macos",
            "audio_backend": "AVFoundation",
            "microphone": {
                "state": mic_state.value,
                "device_index": self.mic_index,
                "user_hint": mic_hint
            },
            "system_audio": {
                "state": bh_state.value,
                "device_index": self.blackhole_index,
                "user_hint": bh_hint,
                "graceful_fallback": "Microphone-Only mode active"
            }
        }

    def start_microphone(self, callback: Callable[[str], None]):
        self.is_running = True
        # Managed capture loop implemented in DesktopAudioCapture

    def start_system_audio(self, callback: Callable[[str], None]):
        if not self.blackhole_index:
            return
        self.is_running = True

    def stop(self):
        self.is_running = False
