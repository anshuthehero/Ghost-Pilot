#!/usr/bin/env python3
"""
Ghost Copilot v3 — Full Featured
• TWO MODES: Auto-listen (mic VAD) ↔ PTT (F5/Spacebar)
• Auto-mode reading cooldown: waits based on answer length before re-listening
• Conversation history: follow-up questions understood in context
• Visible/Invisible toggle button in HUD
• Speaker VAD: BlackHole captures interviewer audio automatically
• Clipboard watcher: copy any text → instant answer
• Invisible to screen capture (NSWindowSharingNone)
"""

import collections
import hmac
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
AUDIO_DIR  = os.path.expanduser("~/.ghost_copilot/audio")
try:
    os.makedirs(AUDIO_DIR, exist_ok=True)
except Exception:
    AUDIO_DIR = os.path.join(BASE_DIR, "audio")
    os.makedirs(AUDIO_DIR, exist_ok=True)

def load_env():
    candidates = [
        os.path.join(BASE_DIR, ".env"),
        os.path.expanduser("~/.ghost_copilot/.env"),
        os.path.join(os.path.dirname(BASE_DIR), "Resources", ".env"),
        os.path.join(BASE_DIR, "..", ".env"),
    ]
    for env_path in candidates:
        if os.path.exists(env_path):
            try:
                with open(env_path, "r", encoding="utf-8-sig", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            k = k.strip().lstrip("\ufeff")
                            if k not in os.environ:
                                os.environ[k] = v.strip().strip("'\"")
            except Exception:
                pass

load_env()
GROQ_KEY    = os.environ.get("GROQ_API_KEY", "")
HOST        = os.environ.get("HOST", "127.0.0.1")
PORT        = int(os.environ.get("PORT", "9471"))

# ── H-1 Security Fix: Always enforce a session auth token ──────────────────
# If COPILOT_AUTH_TOKEN is not set, generate a cryptographically random one
# so that no local process can call the API without it.
_token_from_env = os.environ.get("COPILOT_AUTH_TOKEN", "").strip()
if _token_from_env:
    AUTH_TOKEN = _token_from_env
else:
    AUTH_TOKEN = secrets.token_hex(24)  # 48-char hex, 192 bits of entropy
    # Persist the generated token so ghost_copilot.m/Windows client can read it
    try:
        _token_file = os.path.join(os.path.expanduser("~/.ghost_copilot"), "session_token")
        os.makedirs(os.path.dirname(_token_file), exist_ok=True)
        with open(_token_file, "w", encoding="utf-8") as _tf:
            _tf.write(AUTH_TOKEN)
        try:
            os.chmod(_token_file, 0o600)  # Owner read/write only
        except Exception:
            pass
        print(f"[🔒 Security] Auto-generated session token (stored at ~/.ghost_copilot/session_token)")
        print(f"[🔒 Security] Set COPILOT_AUTH_TOKEN in .env to use a persistent token instead.")
    except Exception as _e:
        print(f"[⚠️ Security] Could not persist session token to ~/.ghost_copilot: {_e}")

    # Always persist locally next to app.py for portable and restricted Windows setups
    try:
        _fallback_file = os.path.join(BASE_DIR, ".session_token")
        with open(_fallback_file, "w", encoding="utf-8") as _tf:
            _tf.write(AUTH_TOKEN)
        print(f"[🔒 Security] Stored session token in local directory (.session_token)")
    except Exception:
        pass
# ────────────────────────────────────────────────────────────────────────────

WHISPER_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
CHAT_URL    = "https://api.groq.com/openai/v1/chat/completions"
MODEL       = "qwen/qwen3.8-27b"

try:
    from client.core.ffmpeg import get_ffmpeg_bin
    FFMPEG_BIN = get_ffmpeg_bin()
except Exception:
    import shutil
    FFMPEG_BIN = shutil.which("ffmpeg") or "ffmpeg"

if not GROQ_KEY:
    print("[⚠️ SECURITY WARNING] GROQ_API_KEY is not set in environment or .env file!")

# Regex patterns to detect and filter out accidentally copied sensitive data
SECRET_PATTERNS = [
    re.compile(r'AKIA[0-9A-Z]{16}'),                          # AWS Access Key
    re.compile(r'(?:ghp|gho|ghu|ghs|ghr)_[0-9a-zA-Z]{36}'),  # GitHub Classic Tokens
    re.compile(r'github_pat_[0-9a-zA-Z_]{82}'),              # GitHub Fine-Grained Token
    re.compile(r'sk-(?:proj-)?[a-zA-Z0-9_-]{20,}'),          # OpenAI API Key
    re.compile(r'sk-ant-[a-zA-Z0-9_-]{20,}'),                # Anthropic Claude API Key
    re.compile(r'gsk_[a-zA-Z0-9]{40,}'),                     # Groq Key
    re.compile(r'xox[baprs]-[0-9a-zA-Z]{10,}'),              # Slack Token
    re.compile(r'ey[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}'), # JWT
    re.compile(r'-----BEGIN (?:RSA|OPENSSH|EC|DSA)? ?PRIVATE KEY-----'), # Private Key
    re.compile(r'password\s*[:=]\s*\S+', re.IGNORECASE),     # Plaintext passwords
    re.compile(r'(?:postgres|mysql|mongodb|redis):\/\/\S+'), # Database connection strings
    re.compile(r'[a-zA-Z0-9_-]+_SECRET[a-zA-Z0-9_-]*', re.IGNORECASE), # Secret identifiers
]

def is_sensitive_data(text):
    if not text:
        return False
    for p in SECRET_PATTERNS:
        if p.search(text):
            print("[🛡️ Security] Filtered sensitive credential from clipboard.")
            return True
    return False

def _win32_sp_kwargs(**kwargs):
    """Adds CREATE_NO_WINDOW (0x08000000) on Windows to prevent console window flashing."""
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | 0x08000000
    return kwargs

if sys.platform == "darwin":
    try:
        subprocess.run(["osascript", "-e", "set volume input volume 90"], check=False)
    except Exception:
        pass

IGNORED = {
    "", ".", " .", "thank you", "thank you.", "thanks", "thanks.", "okay",
    "ok", "okay.", "ok.", "yes", "yeah", "yep", "no", "alright", "bye",
    "cool", "sure", "mm", "hmm", "uh", "um", "thank you for watching",
    "thank you for watching.", "thanks for watching", "thanks for watching.",
    "subtitles by", "subtitles by the amara.org community", "you", "...", "....",
    "subscribe", "please subscribe", "like and subscribe", "bye bye", "so"
}

DEFAULT_SYSTEM_PROMPT = """You are a brilliant real-time interview assistant. Answer ANY question — technical, general knowledge, HR, behavioural, domain-specific.

RULES:
- Answer directly. No preamble, no filler phrases.
- Factual/general knowledge (capitals, dates, definitions): 1-2 sentences max.
- Technical questions: key concept + 2-3 crisp bullet points.
- HR/behavioural: structured, natural-sounding answer.
- No code blocks unless explicitly asked.
- Be authoritative. Never say "I think" or "I believe" for facts."""

SYSTEM_PROMPT = DEFAULT_SYSTEM_PROMPT

# Global state
sse_clients      = []
sse_lock         = threading.Lock()
last_clipboard   = ""
gen_id           = 0
gen_lock         = threading.Lock()
auto_mode        = False
manual_recording = False
reading_until    = 0.0
conv_history     = collections.deque(maxlen=6)
BLACKHOLE_DEVICE = None
MIC_DEVICE       = "1"
sharing_mode     = "hidden"   # "hidden" = ghost (default), "visible" = shows on screen share
user_custom_duration = "auto" # "auto", 15, 30, 60, 120, "inf"


def local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1)); return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()

def clipboard():
    try:
        if sys.platform == "darwin":
            return subprocess.check_output(["pbpaste"], text=True).strip()
        elif sys.platform.startswith("win"):
            # Native Win32 API via ctypes: zero-overhead, no process spawns, no AV triggers
            try:
                import ctypes
                from ctypes import wintypes
                user32 = ctypes.windll.user32
                kernel32 = ctypes.windll.kernel32
                CF_UNICODETEXT = 13
                user32.OpenClipboard.argtypes = [wintypes.HWND]
                user32.OpenClipboard.restype = wintypes.BOOL
                user32.GetClipboardData.argtypes = [wintypes.UINT]
                user32.GetClipboardData.restype = wintypes.HANDLE
                user32.CloseClipboard.argtypes = []
                user32.CloseClipboard.restype = wintypes.BOOL
                kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
                kernel32.GlobalLock.restype = wintypes.LPCWSTR
                kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
                kernel32.GlobalUnlock.restype = wintypes.BOOL

                if user32.OpenClipboard(None):
                    try:
                        h_glb = user32.GetClipboardData(CF_UNICODETEXT)
                        if h_glb:
                            ptr = kernel32.GlobalLock(h_glb)
                            if ptr:
                                try:
                                    return str(ptr).strip()
                                finally:
                                    kernel32.GlobalUnlock(h_glb)
                    finally:
                        user32.CloseClipboard()
            except Exception:
                pass
            ps_cmd = "if (Get-Command Get-Clipboard -ErrorAction SilentlyContinue) { Get-Clipboard } else { Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Clipboard]::GetText() }"
            return subprocess.check_output(["powershell", "-NoProfile", "-Command", ps_cmd], text=True, stderr=subprocess.DEVNULL, **_win32_sp_kwargs()).strip()
        else:
            return subprocess.check_output(["xclip", "-o", "-selection", "clipboard"], text=True).strip()
    except Exception:
        return ""

def broadcast(event, data):
    payload = f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()
    with sse_lock:
        dead = []
        for c in sse_clients:
            try:
                c.wfile.write(payload); c.wfile.flush()
            except Exception:
                dead.append(c)
        for d in dead:
            if d in sse_clients:
                sse_clients.remove(d)

def reading_cooldown_secs(word_count):
    return min(30, max(5, round(word_count / 180 * 60) + 3))


def trim_silence(src, dst):
    try:
        subprocess.run([
            FFMPEG_BIN, "-y", "-i", src,
            "-af", "silenceremove=stop_periods=-1:stop_duration=1.2:stop_threshold=-35dB", dst
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3, **_win32_sp_kwargs())
        return dst if os.path.exists(dst) and os.path.getsize(dst) > 2000 else src
    except Exception:
        return src

def loudnorm(src, dst):
    try:
        subprocess.run([
            FFMPEG_BIN, "-y", "-i", src,
            "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", dst
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3, **_win32_sp_kwargs())
        return dst if os.path.exists(dst) and os.path.getsize(dst) > 1000 else src
    except Exception:
        return src

def transcribe(path):
    if not os.path.exists(path) or os.path.getsize(path) < 8000:
        return None
    trimmed = trim_silence(path, path.replace(".wav", "_trim.wav"))
    boosted = loudnorm(trimmed, path.replace(".wav", "_boost.wav"))

    text = None
    # 1. Try system curl if available (macOS & Windows 10/11)
    curl_bin = shutil.which("curl") or ("/usr/bin/curl" if os.path.exists("/usr/bin/curl") else None)
    if curl_bin:
        curl_target = boosted.replace("\\", "/")
        cmd = [
            curl_bin, "-s", WHISPER_URL,
            "-H", f"Authorization: Bearer {GROQ_KEY}",
            "-F", f"file=@{curl_target}",
            "-F", "model=whisper-large-v3-turbo",
            "-F", "language=en"
        ]
        try:
            r = subprocess.run(cmd, stdout=subprocess.PIPE, text=True, timeout=8, **_win32_sp_kwargs())
            if r.stdout:
                text = json.loads(r.stdout).get("text", "").strip()
        except Exception:
            text = None

    # 2. Pure Python fallback (works on Windows 7 and systems without curl installed)
    if text is None:
        try:
            boundary = f"----InterviewAssistant{secrets.token_hex(12)}"
            filename = os.path.basename(boosted)
            with open(boosted, "rb") as f:
                file_bytes = f.read()

            parts = [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode(),
                b"Content-Type: audio/wav\r\n\r\n",
                file_bytes,
                b"\r\n",
                f"--{boundary}\r\n".encode(),
                b'Content-Disposition: form-data; name="model"\r\n\r\n',
                b"whisper-large-v3-turbo\r\n",
                f"--{boundary}\r\n".encode(),
                b'Content-Disposition: form-data; name="language"\r\n\r\n',
                b"en\r\n",
                f"--{boundary}--\r\n".encode()
            ]
            payload = b"".join(parts)
            req = urllib.request.Request(
                WHISPER_URL,
                data=payload,
                headers={
                    "Authorization": f"Bearer {GROQ_KEY}",
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                    "User-Agent": "InterviewAssistant/3.0"
                }
            )
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode())
                text = data.get("text", "").strip()
        except Exception as e:
            print(f"[❌ Whisper] {e}")
            return None

    if text:
        print(f"[🎤 Whisper] \"{text}\"")
        return text if text.lower().rstrip(".,!? ") not in IGNORED else None
    return None


def stream_answer(question, gid):
    global reading_until, conv_history
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += list(conv_history)
    messages.append({"role": "user", "content": question})
    payload = {"model": MODEL, "messages": messages,
               "temperature": 0.0, "max_tokens": 400, "stream": True}
    req = urllib.request.Request(CHAT_URL, data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {GROQ_KEY}",
                 "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
    full = ""
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            for line in resp:
                with gen_lock:
                    if gid != gen_id: return
                line = line.decode().strip()
                if not line.startswith("data: ") or line == "data: [DONE]": continue
                try:
                    token = json.loads(line[6:])["choices"][0]["delta"].get("content", "")
                    if token:
                        full += token
                        broadcast("token", {"token": token})
                except Exception:
                    continue
    except Exception as e:
        print(f"[❌ LLM] {e}"); broadcast("error", {"message": str(e)}); return

    if full:
        conv_history.append({"role": "user", "content": question})
        conv_history.append({"role": "assistant", "content": full})
        wc = len(full.split())
        if user_custom_duration == "inf":
            cooldown = 0
            reading_until = 0.0
        elif isinstance(user_custom_duration, (int, float)) and user_custom_duration > 0:
            cooldown = int(user_custom_duration)
            reading_until = time.time() + cooldown
        else:
            cooldown = reading_cooldown_secs(wc)
            reading_until = time.time() + cooldown

        broadcast("status", {"state": "done"})
        broadcast("cooldown", {"seconds": cooldown, "words": wc, "mode": str(user_custom_duration)})
        print(f"[📖] {wc} words → {cooldown}s duration (mode: {user_custom_duration})")


def solve(question):
    global gen_id
    q = question.strip()
    if not q or q.lower().rstrip(".,!? ") in IGNORED: return
    with gen_lock:
        gen_id += 1; gid = gen_id
    print(f"\n[🚀 Q#{gid}] \"{q[:80]}\"")
    broadcast("status", {"state": "generating", "question": q})
    stream_answer(q, gid)


def has_voice(audio_path, threshold_db=-30.0, min_dynamic_range=5.0):
    if not os.path.exists(audio_path) or os.path.getsize(audio_path) < 4000:
        return False
    try:
        cmd = [FFMPEG_BIN, "-i", audio_path, "-af", "volumedetect", "-f", "null", "-"]
        r = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True, timeout=3, **_win32_sp_kwargs())
        max_m = re.search(r"max_volume:\s*([-0-9.]+)\s*dB", r.stderr)
        mean_m = re.search(r"mean_volume:\s*([-0-9.]+)\s*dB", r.stderr)
        if max_m:
            max_vol = float(max_m.group(1))
            mean_vol = float(mean_m.group(1)) if mean_m else max_vol - 12.0
            dynamic_range = max_vol - mean_vol
            # Speech has strong peaks above flat baseline noise
            if max_vol > threshold_db and dynamic_range >= min_dynamic_range:
                return True
    except Exception:
        pass
    return False


def get_mic_ffmpeg_args(out_path, duration=None):
    args = [FFMPEG_BIN, "-y"]
    if sys.platform == "darwin":
        args.extend(["-f", "avfoundation", "-i", f":{MIC_DEVICE}"])
    elif sys.platform.startswith("win"):
        if MIC_DEVICE == "default" or "wasapi" in str(MIC_DEVICE).lower():
            args.extend(["-f", "wasapi", "-i", "default"])
        else:
            mic_target = MIC_DEVICE if str(MIC_DEVICE).startswith("audio=") else f"audio={MIC_DEVICE}"
            args.extend(["-f", "dshow", "-i", mic_target])
    else:
        args.extend(["-f", "pulse", "-i", "default"])
    if duration:
        args.extend(["-t", str(duration)])
    args.extend(["-ar", "16000", "-ac", "1", out_path])
    return args


def auto_vad_loop():
    CHUNK = 3.5
    print("[🎙️ Auto VAD] Thread listening...")
    while True:
        if not auto_mode or manual_recording:
            time.sleep(0.3); continue
        remaining = reading_until - time.time()
        if remaining > 0:
            broadcast("vadstate", {"state": "cooling",
                "label": f"📖 Reading... auto-listen in {int(remaining)}s"})
            time.sleep(1); continue
        chunk = os.path.join(AUDIO_DIR, "mic_chunk.wav")
        broadcast("vadstate", {"state": "listening", "label": "👂 Auto-Listening (speak anytime)..."})
        try:
            cmd = get_mic_ffmpeg_args(chunk, duration=CHUNK)
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=int(CHUNK) + 2, **_win32_sp_kwargs())
        except Exception:
            time.sleep(0.5); continue

        if has_voice(chunk, threshold_db=-42.0, min_dynamic_range=1.5):
            print("[🎤 Auto VAD] Voice detected! Transcribing...")
            broadcast("vadstate", {"state": "processing", "label": "⚡ Heard speech — transcribing..."})
            text = transcribe(chunk)
            if text and len(text.strip()) >= 2:
                threading.Thread(target=solve, args=(text,), daemon=True).start()
            else:
                broadcast("vadstate", {"state": "listening", "label": "👂 Auto-Listening (speak anytime)..."})
        else:
            broadcast("vadstate", {"state": "listening", "label": "👂 Auto-Listening (speak anytime)..."})


_devices_probed = False

def detect_audio_devices():
    global MIC_DEVICE, BLACKHOLE_DEVICE, _devices_probed
    if _devices_probed:
        return
    _devices_probed = True
    if sys.platform == "darwin":
        try:
            r = subprocess.run(
                [FFMPEG_BIN, "-f", "avfoundation", "-list_devices", "true", "-i", ""],
                stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True, timeout=5)
            in_audio = False
            for line in (r.stderr or "").splitlines():
                if "AVFoundation audio devices" in line: in_audio = True
                if in_audio:
                    if any(k in line.lower() for k in ("macbook", "microphone", "mic", "built-in")):
                        m = re.search(r'\[(\d+)\]', line)
                        if m and not MIC_DEVICE:
                            MIC_DEVICE = m.group(1)
                            print(f"[🎤 Mic] Using microphone at [{MIC_DEVICE}] ({line.strip()})")
                    if "BlackHole" in line:
                        m = re.search(r'\[(\d+)\]', line)
                        if m:
                            BLACKHOLE_DEVICE = m.group(1)
                            print(f"[🔊] BlackHole at [{BLACKHOLE_DEVICE}]")
        except Exception:
            pass
        if not MIC_DEVICE:
            MIC_DEVICE = "1"
            print(f"[🎤 Mic] Defaulting to microphone index [{MIC_DEVICE}]")
    elif sys.platform.startswith("win"):
        try:
            r = subprocess.run(
                [FFMPEG_BIN, "-f", "dshow", "-list_devices", "true", "-i", "dummy"],
                stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True, errors="ignore", timeout=4, **_win32_sp_kwargs())
            for line in (r.stderr or "").splitlines():
                if "(audio)" in line:
                    clean_name = line.split("]")[ -1].replace("(audio)", "").strip().strip('"')
                    MIC_DEVICE = clean_name
                    print(f"[🎤 Mic] Using Windows microphone: \"{MIC_DEVICE}\"")
                    break
        except Exception:
            pass
        if not MIC_DEVICE:
            MIC_DEVICE = "default"
            print(f"[🎤 Mic] Defaulting to Windows microphone: \"{MIC_DEVICE}\"")

        BLACKHOLE_DEVICE = "default"
        try:
            r = subprocess.run(
                [FFMPEG_BIN, "-list_devices", "true", "-f", "wasapi", "-i", "dummy"],
                stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True, errors="ignore", timeout=4, **_win32_sp_kwargs())
            for line in (r.stderr or "").splitlines():
                if "render" in line.lower() or "output" in line.lower() or "speakers" in line.lower():
                    clean_name = line.split("]")[ -1].strip().strip('"')
                    if clean_name:
                        BLACKHOLE_DEVICE = clean_name
                        print(f"[🔊] Windows WASAPI loopback target: \"{BLACKHOLE_DEVICE}\"")
                        break
        except Exception:
            pass
        print(f"[🔊] Windows native WASAPI loopback ready (using: {BLACKHOLE_DEVICE}).")

def detect_mic():
    detect_audio_devices()
    return bool(MIC_DEVICE)

def detect_blackhole():
    detect_audio_devices()
    return bool(BLACKHOLE_DEVICE)

def speaker_vad_loop():
    CHUNK = 5.0
    if not detect_blackhole():
        broadcast("speakervad", {"state": "unavailable",
            "label": "❌ System audio capture not ready"})
        return
    broadcast("speakervad", {"state": "active", "label": "🔊 Interviewer Listen: ON"})
    print("[🔊 Speaker VAD] Listening to system audio...")
    while True:
        chunk = os.path.join(AUDIO_DIR, "spk_chunk.wav")
        try:
            if sys.platform == "darwin":
                spk_cmd = [
                    FFMPEG_BIN, "-y",
                    "-f", "avfoundation", "-i", f":{BLACKHOLE_DEVICE}",
                    "-t", str(CHUNK), "-ar", "16000", "-ac", "1", chunk
                ]
            elif sys.platform.startswith("win"):
                spk_target = BLACKHOLE_DEVICE if BLACKHOLE_DEVICE else "default"
                spk_cmd = [
                    FFMPEG_BIN, "-y",
                    "-f", "wasapi", "-i", spk_target,
                    "-t", str(CHUNK), "-ar", "16000", "-ac", "1", chunk
                ]
            else:
                time.sleep(1); continue
            subprocess.run(spk_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=int(CHUNK) + 2, **_win32_sp_kwargs())
        except Exception:
            time.sleep(1); continue

        if has_voice(chunk, threshold_db=-35.0):
            print("[🔊 Speaker VAD] Interviewer speech detected!")
            broadcast("speakervad", {"state": "processing", "label": "🔊 Heard Interviewer — answering..."})
            text = transcribe(chunk)
            if text:
                threading.Thread(target=solve, args=(text,), daemon=True).start()
            broadcast("speakervad", {"state": "active", "label": "🔊 Interviewer Listen: ON"})


def clipboard_watcher():
    global last_clipboard
    last_clipboard = clipboard()
    while True:
        try:
            c = clipboard()
            if c and c != last_clipboard and len(c) >= 10:
                last_clipboard = c
                if not is_sensitive_data(c):
                    threading.Thread(target=solve, args=(c,), daemon=True).start()
                else:
                    print("[🛡️ Security] Ignored sensitive clipboard data.")
            time.sleep(0.3)
        except Exception:
            time.sleep(1)


ptt_lock = threading.Lock()

def ptt_record():
    global manual_recording
    if not ptt_lock.acquire(blocking=False):
        return
    try:
        ptt = os.path.join(AUDIO_DIR, "ptt.wav")
        broadcast("ptt_state", {"recording": True})
        broadcast("vadstate", {"state": "recording", "label": "🔴 Recording... speak now"})
        cmd = get_mic_ffmpeg_args(ptt)
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **_win32_sp_kwargs())
        while manual_recording:
            time.sleep(0.05)
        proc.terminate()
        try: proc.wait(timeout=2)
        except Exception: proc.kill()
        broadcast("ptt_state", {"recording": False})
        broadcast("vadstate", {"state": "processing", "label": "⚡ Transcribing..."})
        text = transcribe(ptt)
        if text:
            solve(text)
        else:
            broadcast("vadstate", {"state": "idle", "label": "🎤 PTT ready — Spacebar"})
    finally:
        ptt_lock.release()


HUD = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Interview Assistant</title>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<style>
:root {
  --bg: #07080d;
  --card-bg: rgba(15, 18, 28, 0.75);
  --card-border: rgba(255, 255, 255, 0.09);
  --accent-blue: #3b82f6;
  --accent-emerald: #10b981;
  --accent-amber: #f59e0b;
  --accent-rose: #f43f5e;
  --text-primary: #f8fafc;
  --text-secondary: #94a3b8;
  --text-muted: #64748b;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  background: var(--bg);
  background-image: radial-gradient(circle at 50% 0%, rgba(59, 130, 246, 0.12) 0%, transparent 60%);
  color: var(--text-primary);
  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro Display", "Segoe UI", Roboto, sans-serif;
  padding: 14px;
  padding-bottom: 90px;
  max-width: 490px;
  margin: 0 auto;
  min-height: 100vh;
  user-select: text;
  -webkit-font-smoothing: antialiased;
}

::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.15); border-radius: 4px; }

/* Full Window Aura Transformation Animation */
@keyframes aura-green-sweep {
  0% {
    box-shadow: inset 0 0 120px rgba(16, 185, 129, 0.75), 0 0 50px rgba(16, 185, 129, 0.5);
    background-color: rgba(16, 185, 129, 0.12);
  }
  50% {
    box-shadow: inset 0 0 50px rgba(16, 185, 129, 0.35);
  }
  100% {
    box-shadow: none;
    background-color: var(--bg);
  }
}

@keyframes aura-red-sweep {
  0% {
    box-shadow: inset 0 0 120px rgba(244, 63, 94, 0.85), 0 0 50px rgba(244, 63, 94, 0.6);
    background-color: rgba(244, 63, 94, 0.14);
  }
  50% {
    box-shadow: inset 0 0 50px rgba(244, 63, 94, 0.4);
  }
  100% {
    box-shadow: none;
    background-color: var(--bg);
  }
}

body.aura-green {
  animation: aura-green-sweep 1.1s cubic-bezier(0.2, 0.8, 0.2, 1);
}

body.aura-red {
  animation: aura-red-sweep 1.1s cubic-bezier(0.2, 0.8, 0.2, 1);
}

/* Animated Shield Banner */
.shield-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 7px 12px;
  border-radius: 8px;
  margin-bottom: 10px;
  font-size: 11.5px;
  font-weight: 600;
  transition: all 0.35s cubic-bezier(0.4, 0, 0.2, 1);
  border: 1px solid rgba(16, 185, 129, 0.35);
  background: rgba(16, 185, 129, 0.1);
  color: #34d399;
  box-shadow: 0 0 16px rgba(16, 185, 129, 0.15);
  animation: banner-slide 0.3s ease-out;
}
.shield-banner.danger {
  border-color: rgba(244, 63, 94, 0.5);
  background: rgba(244, 63, 94, 0.15);
  color: #fb7185;
  box-shadow: 0 0 16px rgba(244, 63, 94, 0.25);
}
@keyframes banner-slide { from { opacity: 0; transform: translateY(-4px); } to { opacity: 1; transform: translateY(0); } }

/* Header */
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 2px 2px 10px 2px;
  border-bottom: 1px solid var(--card-border);
  margin-bottom: 10px;
}
.brand {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11.5px;
  font-weight: 700;
  letter-spacing: 0.9px;
  color: #f1f5f9;
  text-transform: uppercase;
}
.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--accent-emerald);
  box-shadow: 0 0 10px rgba(16, 185, 129, 0.7);
  animation: pulse-glow 2.5s infinite;
}
@keyframes pulse-glow { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.35; transform: scale(0.85); } }

.header-actions { display: flex; gap: 4px; align-items: center; }

.btn-glass {
  background: rgba(255, 255, 255, 0.04);
  color: var(--text-secondary);
  border: 1px solid var(--card-border);
  border-radius: 6px;
  padding: 4px 8px;
  font-size: 10.5px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
}
.btn-glass:hover { background: rgba(255, 255, 255, 0.09); color: var(--text-primary); }

/* Mode Segmented Control */
.segmented-bar {
  display: flex;
  background: rgba(15, 18, 28, 0.9);
  border: 1px solid var(--card-border);
  border-radius: 8px;
  padding: 3px;
  gap: 2px;
  margin-bottom: 8px;
}
.segment-btn {
  flex: 1;
  padding: 7px 10px;
  border-radius: 6px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  font-size: 11.5px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}
.segment-btn.active {
  background: rgba(59, 130, 246, 0.22);
  color: #bfdbfe;
  border: 1px solid rgba(59, 130, 246, 0.4);
  box-shadow: 0 1px 6px rgba(0,0,0,0.35);
}

/* Duration Bar */
.dur-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: rgba(15, 18, 28, 0.65);
  border: 1px solid var(--card-border);
  border-radius: 8px;
  padding: 5px 8px;
  margin-bottom: 8px;
}
.dur-label {
  font-size: 10px;
  font-weight: 700;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.6px;
}
.dur-group { display: flex; gap: 3px; }
.dur-chip {
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid transparent;
  border-radius: 5px;
  padding: 3px 7px;
  font-size: 10.5px;
  font-weight: 600;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s ease;
}
.dur-chip.active {
  background: rgba(59, 130, 246, 0.28);
  border-color: rgba(59, 130, 246, 0.45);
  color: #ffffff;
}
.dur-chip:hover { color: #fff; }

/* Emergency Freeze Stay Button */
.stay-btn {
  width: 100%;
  padding: 7px 11px;
  border-radius: 8px;
  border: 1px solid rgba(245, 158, 11, 0.28);
  background: rgba(245, 158, 11, 0.07);
  color: #fcd34d;
  font-size: 11.5px;
  font-weight: 700;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  margin-bottom: 8px;
  transition: all 0.2s ease;
}
.stay-btn:hover { background: rgba(245, 158, 11, 0.15); border-color: rgba(245, 158, 11, 0.45); }
.stay-btn.frozen {
  background: rgba(245, 158, 11, 0.25) !important;
  border-color: #f59e0b !important;
  color: #ffffff !important;
  box-shadow: 0 0 16px rgba(245, 158, 11, 0.4);
  animation: freeze-glow 2s infinite;
}
@keyframes freeze-glow { 0%, 100% { transform: scale(1); } 50% { transform: scale(0.99); opacity: 0.95; } }

/* Emergency Skip Button */
.skip-btn {
  width: 100%;
  padding: 7px 11px;
  border-radius: 8px;
  border: 1px solid rgba(244, 63, 94, 0.35);
  background: rgba(244, 63, 94, 0.08);
  color: #fb7185;
  font-size: 11.5px;
  font-weight: 700;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  margin-bottom: 8px;
  transition: all 0.2s ease;
}
.skip-btn:hover {
  background: rgba(244, 63, 94, 0.18);
  border-color: rgba(244, 63, 94, 0.6);
  color: #fff;
}

/* Unified Status Monitor */
.status-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--card-bg);
  backdrop-filter: blur(16px);
  border: 1px solid var(--card-border);
  border-radius: 8px;
  padding: 7px 11px;
  margin-bottom: 8px;
  font-size: 11px;
}
.status-indicator { display: flex; align-items: center; gap: 6px; }
.status-text { font-weight: 600; color: #94a3b8; font-size: 11px; }

/* PTT Action Button */
.ptt-action {
  width: 100%;
  padding: 11px;
  border-radius: 8px;
  border: 1px solid rgba(59, 130, 246, 0.35);
  background: rgba(59, 130, 246, 0.12);
  color: #93c5fd;
  font-size: 12.5px;
  font-weight: 700;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-bottom: 8px;
  transition: all 0.15s ease;
}
.ptt-action:hover { background: rgba(59, 130, 246, 0.2); }
.ptt-action.rec {
  background: rgba(244, 63, 94, 0.22) !important;
  border-color: rgba(244, 63, 94, 0.65) !important;
  color: #ffe4e6 !important;
  box-shadow: 0 0 16px rgba(244, 63, 94, 0.45);
}

/* Cooldown Timer Bar */
.cooldown-wrap {
  background: rgba(245, 158, 11, 0.08);
  border: 1px solid rgba(245, 158, 11, 0.28);
  border-radius: 8px;
  padding: 8px 11px;
  font-size: 11px;
  color: #fbbf24;
  margin-bottom: 8px;
  display: none;
}
.cd-bar-track {
  height: 4px;
  background: rgba(245, 158, 11, 0.2);
  border-radius: 2px;
  margin-top: 6px;
  overflow: hidden;
}
.cd-bar-fill {
  height: 100%;
  background: #f59e0b;
  border-radius: 2px;
  transition: width 0.9s linear;
}

/* Prompt Card */
.prompt-card {
  background: rgba(59, 130, 246, 0.09);
  border: 1px solid rgba(59, 130, 246, 0.28);
  border-radius: 8px;
  padding: 9px 12px;
  margin-bottom: 8px;
  display: none;
}
.prompt-label { font-weight: 700; font-size: 10px; color: #60a5fa; text-transform: uppercase; letter-spacing: 0.6px; margin-bottom: 3px; }

/* Large High-Readability Answer Box */
.output-card {
  background: var(--card-bg);
  backdrop-filter: blur(24px);
  border: 1px solid var(--card-border);
  border-radius: 12px;
  padding: 16px 18px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.35);
}
.output-card.md h3 {
  color: #60a5fa;
  font-size: 15px;
  font-weight: 700;
  margin: 10px 0 6px;
  border-bottom: 1px solid rgba(255,255,255,0.08);
  padding-bottom: 4px;
}
.output-card.md ul { list-style: disc; padding-left: 18px; margin: 6px 0 10px; }
.output-card.md li {
  margin-bottom: 6px;
  color: #f1f5f9;
  font-size: 14.5px;
  line-height: 1.65;
  letter-spacing: 0.1px;
}
.output-card.md strong { color: #ffffff; font-weight: 700; }
.output-card.md p {
  margin-bottom: 8px;
  color: #e2e8f0;
  font-size: 14.5px;
  line-height: 1.68;
  letter-spacing: 0.1px;
}
.output-card.md code {
  background: rgba(255,255,255,0.1);
  padding: 2px 5px;
  border-radius: 4px;
  font-family: ui-monospace, SFMono-Regular, monospace;
  font-size: 13px;
  color: #93c5fd;
}

/* Floating Input Dock */
.input-dock {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 10px 14px;
  background: rgba(7, 8, 13, 0.92);
  backdrop-filter: blur(24px);
  border-top: 1px solid var(--card-border);
  max-width: 490px;
  margin: 0 auto;
  display: flex;
  gap: 7px;
}
.dock-input {
  flex: 1;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid var(--card-border);
  border-radius: 8px;
  padding: 8px 12px;
  color: #fff;
  font-size: 13px;
  outline: none;
  transition: all 0.15s ease;
}
.dock-input:focus { border-color: var(--accent-blue); background: rgba(255, 255, 255, 0.08); }
.dock-btn {
  background: #2563eb;
  color: #fff;
  border: none;
  border-radius: 8px;
  padding: 0 14px;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.15s ease;
}
.dock-btn:hover { background: #1d4ed8; }

/* Prompt Input Composer */
.prompt-input-card {
  background: var(--card-bg);
  backdrop-filter: blur(24px);
  border: 1px solid var(--card-border);
  border-radius: 10px;
  padding: 10px 12px;
  margin-bottom: 10px;
}
.prompt-textarea {
  width: 100%;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid var(--card-border);
  border-radius: 7px;
  padding: 8px 10px;
  color: #f8fafc;
  font-size: 13px;
  line-height: 1.5;
  resize: vertical;
  min-height: 56px;
  outline: none;
  font-family: inherit;
  transition: border-color 0.2s ease;
}
.prompt-textarea:focus {
  border-color: var(--accent-blue);
  background: rgba(255, 255, 255, 0.08);
}
.chip-template {
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--card-border);
  border-radius: 4px;
  padding: 2px 7px;
  font-size: 10.5px;
  font-weight: 600;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s ease;
}
.chip-template:hover {
  background: rgba(59, 130, 246, 0.22);
  color: #bfdbfe;
  border-color: rgba(59, 130, 246, 0.45);
}
.btn-ask {
  background: #2563eb;
  color: #fff;
  border: none;
  border-radius: 6px;
  padding: 6px 14px;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.15s ease;
}
.btn-ask:hover { background: #1d4ed8; }

/* In-Browser Mic Button */
.browser-mic-btn {
  width: 100%;
  padding: 8px 12px;
  border-radius: 8px;
  border: 1px solid rgba(16, 185, 129, 0.35);
  background: rgba(16, 185, 129, 0.08);
  color: #34d399;
  font-size: 11.5px;
  font-weight: 700;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  margin-bottom: 8px;
  transition: all 0.2s ease;
}
.browser-mic-btn:hover {
  background: rgba(16, 185, 129, 0.18);
  border-color: rgba(16, 185, 129, 0.6);
}
.browser-mic-btn.active-mic {
  background: rgba(244, 63, 94, 0.25) !important;
  border-color: #f43f5e !important;
  color: #ffe4e6 !important;
  animation: pulse-glow 1.5s infinite;
}

/* System Prompt Modal Drawer */
.modal-overlay {
  display: none;
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.75);
  backdrop-filter: blur(10px);
  z-index: 9999;
  align-items: center;
  justify-content: center;
  padding: 16px;
}
.modal-overlay.open { display: flex; }
.modal-content {
  background: #0f121c;
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 12px;
  max-width: 480px;
  width: 100%;
  padding: 18px;
  box-shadow: 0 16px 48px rgba(0,0,0,0.7);
}
.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}
.modal-textarea {
  width: 100%;
  height: 180px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid var(--card-border);
  border-radius: 8px;
  padding: 10px;
  color: #f1f5f9;
  font-size: 12px;
  line-height: 1.55;
  font-family: inherit;
  outline: none;
  resize: vertical;
}
.modal-textarea:focus { border-color: var(--accent-blue); }
</style>
</head>
<body id="body" tabindex="0">

<!-- Groq API Key Missing Banner -->
<div class="shield-banner" id="api-key-banner" style="display:none;background:rgba(245,158,11,0.12);border-color:rgba(245,158,11,0.4);color:#fcd34d;cursor:pointer;margin-bottom:8px" onclick="openApiKeyModal()">
  <div style="display:flex;align-items:center;gap:6px">
    <span>⚡</span>
    <span><b>Groq API Key Required:</b> Click here to paste your key</span>
  </div>
  <span style="font-size:10px;text-transform:uppercase;font-weight:700;padding:2px 6px;background:rgba(245,158,11,0.2);border-radius:4px">Setup</span>
</div>

<!-- Animated Shield Status Banner -->
<div class="shield-banner" id="shield-banner">
  <div style="display:flex;align-items:center;gap:6px">
    <span id="shield-icon">🛡️</span>
    <span id="shield-text">Ghost Shield Active — Invisible to Screen Share</span>
  </div>
  <span style="font-size:9.5px;opacity:0.75;text-transform:uppercase;letter-spacing:0.5px" id="shield-tag">Protected</span>
</div>

<!-- Header -->
<header class="app-header">
  <div class="brand">
    <span class="status-dot"></span>
    <span>Interview Assistant</span>
  </div>
  <div class="header-actions">
    <button class="btn-glass" id="api-key-btn" onclick="openApiKeyModal()">🔑 API Key</button>
    <button class="btn-glass" onclick="openRoleModal()">⚙️ Role</button>
    <button class="btn-glass" id="vis-btn" onclick="toggleVisible()">🫥 Toggle Ghost</button>
    <button class="btn-glass" onclick="clearAll()">Clear</button>
    <button class="btn-glass" onclick="setOp(.65)">65%</button>
    <button class="btn-glass" onclick="setOp(.3)">Ghost</button>
  </div>
</header>

<!-- Mode Toggle -->
<div class="segmented-bar">
  <button class="segment-btn active" id="btn-ptt" onclick="setMode('ptt')">🎤 Spacebar PTT</button>
  <button class="segment-btn" id="btn-auto" onclick="setMode('auto')">🔁 Auto-Listen</button>
</div>

<!-- Browser Mic Live Listen -->
<button class="browser-mic-btn" id="web-mic-btn" onclick="toggleBrowserMic()">
  <span id="web-mic-icon">🎙️</span>
  <span id="web-mic-text">Browser Mic: Click to Listen Live</span>
</button>

<!-- Duration Selector (5s, 10s, 15s, 30s, 45s, 1m + Auto) -->
<div class="dur-row">
  <span class="dur-label">⏱️ Display Time</span>
  <div class="dur-group">
    <button class="dur-chip active" id="dur-auto" onclick="setDuration('auto')">Auto</button>
    <button class="dur-chip" id="dur-5" onclick="setDuration(5)">5s</button>
    <button class="dur-chip" id="dur-10" onclick="setDuration(10)">10s</button>
    <button class="dur-chip" id="dur-15" onclick="setDuration(15)">15s</button>
    <button class="dur-chip" id="dur-30" onclick="setDuration(30)">30s</button>
    <button class="dur-chip" id="dur-45" onclick="setDuration(45)">45s</button>
    <button class="dur-chip" id="dur-60" onclick="setDuration(60)">1m</button>
  </div>
</div>

<!-- Emergency Stay / Freeze Button -->
<button class="stay-btn" id="stay-btn" onclick="toggleEmergencyStay()">
  <span id="stay-icon">📌</span>
  <span id="stay-label">Emergency Stay (Freeze Answer) [P]</span>
</button>

<!-- Emergency Skip Question Button (Auto-Listen only) -->
<button class="skip-btn" id="skip-btn" onclick="emergencySkip()">
  <span>⏭️</span>
  <span>Emergency Skip Question [S]</span>
</button>

<!-- Unified Status Monitor -->
<div class="status-card">
  <div class="status-indicator">
    <span id="vad-icon">🎤</span>
    <span class="status-text" id="vad-label" style="color:#93c5fd">PTT ready — Spacebar</span>
  </div>
  <div class="status-indicator">
    <span id="spk-icon">🔊</span>
    <span class="status-text" id="spk-label" style="color:#34d399">Interviewer Listen</span>
  </div>
</div>

<!-- PTT Action Button -->
<button class="ptt-action" id="ptt-btn" onclick="togglePTT()">
  <span id="ptt-ico">🎤</span>
  <span id="ptt-lbl">Press Spacebar — Start Speaking</span>
</button>

<!-- Cooldown Bar -->
<div class="cooldown-wrap" id="cd-box">
  <div style="display:flex;justify-content:space-between;font-size:11px">
    <span>📖 Reading Cooldown</span>
    <span><b id="cd-num">0</b>s remaining</span>
  </div>
  <div class="cd-bar-track">
    <div class="cd-bar-fill" id="cd-bar" style="width:100%"></div>
  </div>
</div>

<!-- Prompt Composer Box -->
<div class="prompt-input-card">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
    <div style="display:flex;align-items:center;gap:6px">
      <span style="font-size:12px">✍️</span>
      <span style="font-size:11px;font-weight:700;color:#93c5fd;text-transform:uppercase;letter-spacing:0.6px">Write Prompt / Question</span>
    </div>
    <button class="btn-glass" onclick="openRoleModal()" style="font-size:10px;padding:3px 7px">⚙️ Role Instructions</button>
  </div>
  <textarea class="prompt-textarea" id="main-prompt-input" rows="2" placeholder="Type or paste any interview prompt or question here... (Enter to ask, Shift+Enter for new line)"></textarea>
  <div style="display:flex;justify-content:space-between;align-items:center;margin-top:8px;flex-wrap:wrap;gap:6px">
    <div style="display:flex;gap:4px;flex-wrap:wrap">
      <button class="chip-template" onclick="applyTemplate('approach')">💡 Approach</button>
      <button class="chip-template" onclick="applyTemplate('code')">💻 Code</button>
      <button class="chip-template" onclick="applyTemplate('star')">⭐ Behavioral</button>
      <button class="chip-template" onclick="applyTemplate('complexity')">⏱️ Complexity</button>
    </div>
    <button class="btn-ask" onclick="submitMainPrompt()">⚡ Ask AI</button>
  </div>
</div>

<!-- Question Display -->
<div class="prompt-card" id="heard-box">
  <div class="prompt-label">Prompt</div>
  <div id="heard-text" style="color:#f8fafc;font-weight:600;font-size:13px"></div>
</div>

<!-- Answer Box -->
<main id="out">
  <div class="output-card" style="text-align:center;padding:34px 16px;color:#64748b">
    <div style="font-size:36px;margin-bottom:10px">🎙️</div>
    <div style="font-weight:700;color:#f1f5f9;font-size:14px;margin-bottom:8px">Interview Assistant is Ready</div>
    <div style="font-size:12px;line-height:1.75;color:#94a3b8;max-width:340px;margin:0 auto">
      • Press <b style="color:#93c5fd">Spacebar</b> to speak &amp; submit<br>
      • Switch to <b style="color:#34d399">Auto-Listen</b> for continuous AI assistance<br>
      • Press <b style="color:#fcd34d">P (Emergency Stay)</b> anytime to freeze long answers
    </div>
  </div>
</main>

<!-- Floating Input -->
<footer class="input-dock">
  <input class="dock-input" id="inp" type="text" placeholder="Type prompt + Enter...">
  <button class="dock-btn" onclick="sendText()">⚡</button>
</footer>

<script>
let isScreenVisible = false;
let isPTT = false, currentMode = 'ptt', currentDuration = 'auto';
let isFrozen = false;
let tokenQ = [], displayedMd = '', dripping = false;
let cdTotal = 0, cdTimer = null;

function setOp(v) { document.getElementById('body').style.opacity = v; }

function toggleVisible() {
  isScreenVisible = !isScreenVisible;
  const b = document.getElementById('body');
  const banner = document.getElementById('shield-banner');
  const sIcon = document.getElementById('shield-icon');
  const sText = document.getElementById('shield-text');
  const sTag = document.getElementById('shield-tag');
  
  fetch('/set_sharing', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode: isScreenVisible ? 'visible' : 'hidden' })
  });

  b.classList.remove('aura-green', 'aura-red');
  void b.offsetWidth; // Force CSS reflow to re-trigger animation cleanly

  if (isScreenVisible) {
    b.classList.add('aura-red');
    banner.className = 'shield-banner danger';
    sIcon.textContent = '👁️';
    sText.textContent = 'Visible Mode — Screen Share Can See Window';
    sTag.textContent = 'Test Mode';
  } else {
    b.classList.add('aura-green');
    banner.className = 'shield-banner';
    sIcon.textContent = '🛡️';
    sText.textContent = 'Ghost Shield Active — Invisible to Screen Share';
    sTag.textContent = 'Protected';
  }
}

function setMode(m) {
  currentMode = m;
  document.getElementById('btn-ptt').classList.toggle('active', m === 'ptt');
  document.getElementById('btn-auto').classList.toggle('active', m === 'auto');
  document.getElementById('ptt-btn').style.display = m === 'ptt' ? 'flex' : 'none';
  const skipBtn = document.getElementById('skip-btn');
  if (skipBtn) skipBtn.style.display = 'flex';
  fetch('/set_mode', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode: m })
  });
  const vl = document.getElementById('vad-label');
  if (m === 'auto') {
    vl.textContent = 'Auto-listen active';
    vl.style.color = '#34d399';
  } else {
    vl.textContent = 'PTT ready — Spacebar';
    vl.style.color = '#93c5fd';
  }
}

function emergencySkip() {
  fetch('/skip_question', { method: 'POST' });
  clearAll();
  const hb = document.getElementById('heard-box');
  if (hb) hb.style.display = 'none';
  document.getElementById('out').innerHTML = '<div class="output-card" style="text-align:center;padding:24px;color:#fb7185;font-size:12.5px;font-weight:600">⏭️ Question Skipped — Resuming Auto-Listen...</div>';
  setTimeout(() => {
    document.getElementById('out').innerHTML = '<div class="output-card" style="text-align:center;padding:32px;color:#64748b;font-size:13px">👻 Ready</div>';
  }, 1400);
}

function setDuration(d) {
  currentDuration = d;
  document.querySelectorAll('.dur-chip').forEach(b => b.classList.remove('active'));
  const btn = document.getElementById('dur-' + d);
  if (btn) btn.classList.add('active');
  fetch('/set_duration', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ duration: d })
  });
}

function toggleEmergencyStay() {
  isFrozen = !isFrozen;
  const btn = document.getElementById('stay-btn');
  const ico = document.getElementById('stay-icon');
  const lbl = document.getElementById('stay-label');
  const box = document.getElementById('cd-box');
  
  if (isFrozen) {
    clearInterval(cdTimer);
    btn.classList.add('frozen');
    ico.textContent = '⏸️';
    lbl.textContent = 'Answer Frozen — Click to Unfreeze [P]';
    if (box) box.style.display = 'none';
    fetch('/set_duration', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ duration: 'inf' })
    });
  } else {
    btn.classList.remove('frozen');
    ico.textContent = '📌';
    lbl.textContent = 'Emergency Stay (Freeze Answer) [P]';
    fetch('/set_duration', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ duration: currentDuration })
    });
  }
}

function togglePTT() {
  fetch('/toggle_ptt', { method: 'POST' }).catch(() => {});
}

window.addEventListener('keydown', e => {
  const inp = document.getElementById('inp');
  const isInput = (document.activeElement === inp);
  if (e.key === 'Escape') {
    e.preventDefault();
    toggleVisible();
    return;
  }
  if ((e.code === 'Space' || e.key === ' ' || e.key === 'Spacebar' || e.key === 'F5') && !isInput) {
    e.preventDefault();
    e.stopPropagation();
    togglePTT();
    return;
  }
  if ((e.key === 'p' || e.key === 'P') && !isInput) {
    e.preventDefault();
    toggleEmergencyStay();
    return;
  }
  if ((e.key === 's' || e.key === 'S') && !isInput) {
    e.preventDefault();
    emergencySkip();
    return;
  }
});

function startCooldown(secs, mode) {
  clearInterval(cdTimer);
  if (isFrozen) return;
  const box = document.getElementById('cd-box');
  if (mode === 'inf' || currentDuration === 'inf') {
    box.style.display = 'none';
    return;
  }
  if (!secs || secs <= 0) {
    box.style.display = 'none';
    return;
  }
  box.style.display = 'block';
  cdTotal = secs;
  let left = secs;
  const numEl = document.getElementById('cd-num');
  const barEl = document.getElementById('cd-bar');
  if (numEl) numEl.textContent = left;
  if (barEl) barEl.style.width = '100%';

  cdTimer = setInterval(() => {
    if (isFrozen) { clearInterval(cdTimer); return; }
    left--;
    if (numEl) numEl.textContent = Math.max(0, left);
    if (barEl) barEl.style.width = Math.max(0, left / cdTotal * 100) + '%';
    if (left <= 0) {
      clearInterval(cdTimer);
      box.style.display = 'none';
    }
  }, 1000);
}

function drip() {
  if (tokenQ.length === 0) { dripping = false; return; }
  displayedMd += tokenQ.splice(0, 2).join('');
  const box = document.getElementById('stream-box');
  if (box) box.innerHTML = window.marked ? marked.parse(displayedMd) : displayedMd;
  setTimeout(drip, 45);
}
function startDrip() { if (!dripping) { dripping = true; setTimeout(drip, 45); } }

function sendText() {
  const inp = document.getElementById('inp');
  const t = inp.value.trim();
  if (!t) return;
  fetch('/solve', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question: t })
  });
  inp.value = '';
}
document.getElementById('inp').addEventListener('keydown', e => { if (e.key === 'Enter') sendText(); });

function submitMainPrompt() {
  const ta = document.getElementById('main-prompt-input');
  const t = ta ? ta.value.trim() : '';
  if (!t) return;
  fetch('/solve', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question: t })
  });
  ta.value = '';
}

const mainInput = document.getElementById('main-prompt-input');
if (mainInput) {
  mainInput.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submitMainPrompt();
    }
  });
}

function applyTemplate(type) {
  const ta = document.getElementById('main-prompt-input');
  if (!ta) return;
  let prefix = '';
  if (type === 'approach') prefix = 'Explain step-by-step approach to solve: ';
  else if (type === 'code') prefix = 'Provide clean, optimal, production-ready code with explanation for: ';
  else if (type === 'star') prefix = 'Give a structured STAR method (Situation, Task, Action, Result) interview answer for: ';
  else if (type === 'complexity') prefix = 'What is the optimal Time and Space complexity, trade-offs, and edge cases for: ';
  ta.value = prefix + (ta.value ? ta.value : '');
  ta.focus();
}

function openApiKeyModal() {
  const modal = document.getElementById('api-key-modal');
  if (modal) modal.classList.add('open');
  const input = document.getElementById('groq-api-key-input');
  const msg = document.getElementById('api-key-msg');
  if (msg) { msg.textContent = ''; msg.style.color = '#94a3b8'; }
  fetch('/get_api_status')
    .then(r => r.json())
    .then(d => {
      if (input && d.masked_key) {
        input.placeholder = 'Current key: ' + d.masked_key;
      }
      if (d.configured) {
        if (msg) { msg.textContent = '✅ Active Key: ' + d.masked_key; msg.style.color = '#34d399'; }
      } else {
        if (msg) { msg.textContent = '⚠️ No API key set yet'; msg.style.color = '#fcd34d'; }
      }
      if (input) input.focus();
    })
    .catch(() => {});
}

function closeApiKeyModal() {
  const modal = document.getElementById('api-key-modal');
  if (modal) modal.classList.remove('open');
}

function toggleKeyVisibility() {
  const input = document.getElementById('groq-api-key-input');
  const btn = document.getElementById('vis-key-toggle-btn');
  if (!input) return;
  if (input.type === 'password') {
    input.type = 'text';
    if (btn) btn.textContent = '🔒 Hide';
  } else {
    input.type = 'password';
    if (btn) btn.textContent = '👁️ Show';
  }
}

function saveApiKey() {
  const input = document.getElementById('groq-api-key-input');
  const msg = document.getElementById('api-key-msg');
  const key = input ? input.value.trim() : '';
  if (!key) {
    if (msg) { msg.textContent = 'Please enter a valid key.'; msg.style.color = '#f43f5e'; }
    return;
  }
  fetch('/set_api_key', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ api_key: key })
  })
  .then(r => r.json())
  .then(d => {
    if (d.status === 'ok') {
      if (msg) { msg.textContent = '✅ ' + (d.message || 'Key saved successfully!'); msg.style.color = '#34d399'; }
      if (input) { input.value = ''; input.placeholder = 'Current key: ' + d.masked_key; }
      checkApiKeyStatus();
      setTimeout(closeApiKeyModal, 900);
    } else {
      if (msg) { msg.textContent = '❌ Error: ' + (d.error || 'Failed to save'); msg.style.color = '#f43f5e'; }
    }
  })
  .catch(err => {
    if (msg) { msg.textContent = '❌ Network error saving key'; msg.style.color = '#f43f5e'; }
  });
}

function checkApiKeyStatus() {
  fetch('/get_api_status')
    .then(r => r.json())
    .then(d => {
      const banner = document.getElementById('api-key-banner');
      const btn = document.getElementById('api-key-btn');
      if (d.configured) {
        if (banner) banner.style.display = 'none';
        if (btn) { btn.innerHTML = '🔑 <span style="color:#34d399">●</span> API Key'; btn.title = 'Groq API Key Active: ' + d.masked_key; }
      } else {
        if (banner) banner.style.display = 'flex';
        if (btn) { btn.innerHTML = '🔑 <span style="color:#fcd34d">●</span> Enter Key'; btn.title = 'Groq API Key Not Configured'; }
      }
    })
    .catch(() => {});
}

// Ensure key check runs on window load
window.addEventListener('DOMContentLoaded', () => {
  checkApiKeyStatus();
});

function openRoleModal() {
  const modal = document.getElementById('role-modal');
  const ta = document.getElementById('role-prompt-textarea');
  if (modal) modal.classList.add('open');
  fetch('/get_system_prompt')
    .then(r => r.json())
    .then(d => { if (ta && d.prompt) ta.value = d.prompt; })
    .catch(() => {});
}

function closeRoleModal() {
  const modal = document.getElementById('role-modal');
  if (modal) modal.classList.remove('open');
}

function saveRolePrompt() {
  const ta = document.getElementById('role-prompt-textarea');
  const p = ta ? ta.value.trim() : '';
  if (!p) return;
  fetch('/set_system_prompt', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt: p })
  }).then(r => r.json()).then(() => {
    closeRoleModal();
  }).catch(() => { closeRoleModal(); });
}

function resetRolePrompt() {
  if (!confirm('Reset AI persona back to default interview assistant?')) return;
  fetch('/reset_system_prompt', { method: 'POST' })
    .then(r => r.json())
    .then(d => {
      const ta = document.getElementById('role-prompt-textarea');
      if (ta && d.prompt) ta.value = d.prompt;
    }).catch(() => {});
}

// In-Browser Speech Recognition (Works directly in Chrome, Edge, Safari)
let speechRec = null;
let isBrowserListening = false;

function initBrowserSpeech() {
  const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRec) return false;
  try {
    speechRec = new SpeechRec();
    speechRec.continuous = true;
    speechRec.interimResults = true;
    speechRec.lang = 'en-US';

    speechRec.onresult = (event) => {
      let interim = '';
      for (let i = event.resultIndex; i < event.results.length; ++i) {
        if (event.results[i].isFinal) {
          const text = event.results[i][0].transcript.trim();
          if (text.length > 2) {
            document.getElementById('vad-label').textContent = '⚡ Asking: ' + text.slice(0, 32) + '...';
            document.getElementById('vad-label').style.color = '#60a5fa';
            fetch('/solve', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ question: text })
            });
          }
        } else {
          interim += event.results[i][0].transcript;
          document.getElementById('vad-label').textContent = '👂 Heard: ' + interim;
          document.getElementById('vad-label').style.color = '#f87171';
        }
      }
    };

    speechRec.onerror = (e) => {
      console.warn('Speech error:', e.error);
      if (e.error === 'not-allowed') {
        alert('Microphone access was denied in browser. Please allow microphone permission in your address bar.');
        isBrowserListening = false;
        updateBrowserMicUI();
      }
    };

    speechRec.onend = () => {
      if (isBrowserListening) {
        try { speechRec.start(); } catch(_) {}
      }
    };
    return true;
  } catch (err) {
    return false;
  }
}

function updateBrowserMicUI() {
  const btn = document.getElementById('web-mic-btn');
  const txt = document.getElementById('web-mic-text');
  const ico = document.getElementById('web-mic-icon');
  if (!btn) return;
  if (isBrowserListening) {
    btn.classList.add('active-mic');
    if (ico) ico.textContent = '🔴';
    if (txt) txt.textContent = 'Browser Mic: LISTENING LIVE (Click to stop)';
  } else {
    btn.classList.remove('active-mic');
    if (ico) ico.textContent = '🎙️';
    if (txt) txt.textContent = 'Web Browser Mic: Click to Listen Live';
  }
}

function toggleBrowserMic() {
  if (!speechRec) {
    const ok = initBrowserSpeech();
    if (!ok) {
      alert('Browser Speech Recognition is not supported in this browser. Please use Chrome, Edge, or Safari, or use Spacebar PTT mode.');
      return;
    }
  }
  isBrowserListening = !isBrowserListening;
  if (isBrowserListening) {
    try {
      speechRec.start();
      document.getElementById('vad-label').textContent = '👂 Browser Mic Active — Speak anytime!';
      document.getElementById('vad-label').style.color = '#34d399';
    } catch(e) {
      console.error(e);
    }
  } else {
    try { speechRec.stop(); } catch(_) {}
    document.getElementById('vad-label').textContent = 'Browser Mic Paused';
    document.getElementById('vad-label').style.color = '#94a3b8';
  }
  updateBrowserMicUI();
}

function clearAll() {
  document.getElementById('out').innerHTML = '<div class="output-card" style="text-align:center;padding:32px;color:#64748b;font-size:13px">👻 Ready</div>';
  document.getElementById('heard-box').style.display = 'none';
  if (isFrozen) toggleEmergencyStay();
  displayedMd = ''; tokenQ = [];
}

function connect() {
  const es = new EventSource('/stream');
  es.addEventListener('vadstate', e => {
    const d = JSON.parse(e.data);
    const vl = document.getElementById('vad-label');
    const vi = document.getElementById('vad-icon');
    if (!vl || !vi) return;
    vl.textContent = d.label || '';
    if (d.state === 'listening') { vi.textContent = '👂'; vl.style.color = '#f87171'; }
    else if (d.state === 'processing') { vi.textContent = '⚡'; vl.style.color = '#60a5fa'; }
    else if (d.state === 'cooling') { vi.textContent = '📖'; vl.style.color = '#fbbf24'; }
    else { vi.textContent = currentMode === 'auto' ? '🔁' : '🎤'; vl.style.color = '#93c5fd'; }
  });

  es.addEventListener('ptt_state', e => {
    const d = JSON.parse(e.data);
    isPTT = !!d.recording;
    const btn = document.getElementById('ptt-btn');
    const lbl = document.getElementById('ptt-lbl');
    const ico = document.getElementById('ptt-ico');
    if (!btn || !lbl || !ico) return;
    if (isPTT) {
      btn.classList.add('rec');
      ico.textContent = '⏹️';
      lbl.textContent = 'Listening... Spacebar to submit';
    } else {
      btn.classList.remove('rec');
      ico.textContent = '🎤';
      lbl.textContent = 'Press Spacebar — Start Speaking';
    }
  });

  es.addEventListener('speakervad', e => {
    const d = JSON.parse(e.data);
    const sl = document.getElementById('spk-label');
    const si = document.getElementById('spk-icon');
    if (!sl || !si) return;
    sl.textContent = d.label || '';
    if (d.state === 'active') { si.textContent = '🔊'; sl.style.color = '#34d399'; }
    else if (d.state === 'processing') { si.textContent = '⚡'; sl.style.color = '#60a5fa'; }
    else { si.textContent = '❌'; sl.style.color = '#f87171'; }
  });

  es.addEventListener('status', e => {
    const d = JSON.parse(e.data);
    if (d.state === 'generating') {
      const hb = document.getElementById('heard-box');
      hb.style.display = 'block';
      document.getElementById('heard-text').textContent = d.question || '';
      tokenQ = []; displayedMd = ''; dripping = false;
      document.getElementById('out').innerHTML = '<div class="output-card md" id="stream-box"></div>';
    }
  });

  es.addEventListener('token', e => { tokenQ.push(JSON.parse(e.data).token); startDrip(); });
  es.addEventListener('cooldown', e => {
    const d = JSON.parse(e.data);
    startCooldown(d.seconds, d.mode);
  });
  es.addEventListener('error', e => {
    try {
      document.getElementById('out').innerHTML = `<div style="color:#fb7185;padding:12px;font-size:12.5px;background:rgba(244,63,94,0.1);border-radius:8px">⚠️ ${JSON.parse(e.data).message}</div>`;
    } catch (_) {}
  });
  es.onerror = () => setTimeout(connect, 2000);
}
connect();
</script>

<!-- Persona & System Prompt Modal -->
<!-- Groq API Key Modal -->
<div class="modal-overlay" id="api-key-modal" onclick="if(event.target===this)closeApiKeyModal()">
  <div class="modal-content" style="max-width:440px">
    <div class="modal-header">
      <div style="display:flex;align-items:center;gap:6px">
        <span style="font-size:15px">🔑</span>
        <span style="font-weight:700;font-size:13px;color:#f1f5f9">Groq API Key Configuration</span>
      </div>
      <button class="btn-glass" onclick="closeApiKeyModal()">✕</button>
    </div>
    <div style="font-size:11.5px;color:#94a3b8;margin-bottom:10px;line-height:1.6">
      Paste your Groq API key to activate real-time speech transcription and high-speed LLM answers.
      <br><a href="https://console.groq.com/keys" target="_blank" style="color:#60a5fa;text-decoration:none;font-weight:600">➜ Get a free key at console.groq.com/keys</a>
    </div>
    <div style="margin-bottom:8px">
      <input type="password" class="prompt-textarea" id="groq-api-key-input" style="min-height:38px;height:38px;padding:8px 12px;font-family:monospace;font-size:12px" placeholder="Paste your key: your_groq_api_key_here" autocomplete="off">
    </div>
    <div id="api-key-msg" style="font-size:11px;min-height:16px;margin-bottom:8px"></div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-top:10px">
      <button class="btn-glass" onclick="toggleKeyVisibility()" id="vis-key-toggle-btn" style="font-size:11px">👁️ Show</button>
      <div style="display:flex;gap:6px">
        <button class="btn-glass" onclick="closeApiKeyModal()">Cancel</button>
        <button class="btn-ask" onclick="saveApiKey()" id="save-api-key-btn">Save Key</button>
      </div>
    </div>
  </div>
</div>

<div class="modal-overlay" id="role-modal" onclick="if(event.target===this)closeRoleModal()">
  <div class="modal-content">
    <div class="modal-header">
      <div style="display:flex;align-items:center;gap:6px">
        <span style="font-size:14px">⚙️</span>
        <span style="font-weight:700;font-size:13px;color:#f1f5f9">AI Interview Persona &amp; Instructions</span>
      </div>
      <button class="btn-glass" onclick="closeRoleModal()">✕</button>
    </div>
    <div style="font-size:11px;color:#94a3b8;margin-bottom:8px">
      Set specific instructions, target job role, interview stage, or guidelines for the AI:
    </div>
    <textarea class="modal-textarea" id="role-prompt-textarea"></textarea>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-top:12px">
      <button class="btn-glass" onclick="resetRolePrompt()">Reset Default</button>
      <div style="display:flex;gap:6px">
        <button class="btn-glass" onclick="closeRoleModal()">Cancel</button>
        <button class="btn-ask" onclick="saveRolePrompt()">Save &amp; Apply</button>
      </div>
    </div>
  </div>
</div>
</body>
</html>"""

UNLOCK_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Interview Assistant — Session Unlock</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
  body { background: #0b0f19; color: #f1f5f9; display: flex; align-items: center; justify-content: center; min-height: 100vh; padding: 20px; }
  .card { background: #131b2e; border: 1px solid #1e293b; border-radius: 16px; padding: 36px 32px; width: 100%; max-width: 420px; box-shadow: 0 20px 40px rgba(0,0,0,0.5); text-align: center; }
  .icon { font-size: 44px; margin-bottom: 16px; }
  h1 { font-size: 20px; font-weight: 700; margin-bottom: 8px; color: #f8fafc; }
  p { font-size: 13px; color: #94a3b8; line-height: 1.5; margin-bottom: 24px; }
  input { width: 100%; background: #090d16; border: 1px solid #334155; border-radius: 8px; padding: 12px 14px; font-size: 14px; color: #f8fafc; outline: none; margin-bottom: 16px; }
  input:focus { border-color: #38bdf8; }
  button { width: 100%; background: linear-gradient(135deg, #2563eb, #3b82f6); color: white; border: none; border-radius: 8px; padding: 12px; font-size: 14px; font-weight: 600; cursor: pointer; }
  button:hover { opacity: 0.9; }
  .hint { margin-top: 18px; font-size: 12px; color: #64748b; }
  .hint code { background: #090d16; padding: 2px 6px; border-radius: 4px; color: #38bdf8; }
  .error { color: #f87171; font-size: 13px; margin-top: 12px; display: none; }
</style>
</head>
<body>
<div class="card">
  <div class="icon">🎙️</div>
  <h1>Interview Assistant Verification</h1>
  <p>To access the HUD in your browser, enter the session token generated by the local engine.</p>
  <form id="f" onsubmit="unlock(event)">
    <input type="password" id="t" placeholder="Paste session token here..." autocomplete="off" required autofocus />
    <button type="submit" id="b">Unlock HUD</button>
    <button type="button" id="cp" onclick="autoPaste()" style="margin-top: 10px; background: #1e293b; border: 1px solid #334155; color: #94a3b8;">📋 Auto-Paste &amp; Unlock</button>
  </form>
  <div id="err" class="error">Invalid token. Please check your .session_token file.</div>
  <div class="hint">Your token is in: <code>.session_token</code> (in the app folder)</div>
</div>
<script>
async function autoPaste() {
  try {
    const text = await navigator.clipboard.readText();
    if (text && text.trim()) {
      document.getElementById('t').value = text.trim();
      unlock(new Event('submit'));
    }
  } catch(e) {
    document.getElementById('t').focus();
  }
}

async function unlock(e) {
  if (e && e.preventDefault) e.preventDefault();
  const tok = document.getElementById('t').value.trim();
  const btn = document.getElementById('b');
  const err = document.getElementById('err');
  btn.disabled = true; btn.textContent = 'Verifying...';
  err.style.display = 'none';
  try {
    const res = await fetch('/auth/session', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token: tok })
    });
    if (res.ok) {
      window.location.reload();
    } else {
      err.style.display = 'block';
      btn.disabled = false; btn.textContent = 'Unlock HUD';
    }
  } catch (ex) {
    err.textContent = 'Connection error: ' + ex.message;
    err.style.display = 'block';
    btn.disabled = false; btn.textContent = 'Unlock HUD';
  }
}
</script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def is_authorized(self):
        # 1. DNS Rebinding Defense: When bound to localhost, strictly enforce local hostnames
        if HOST in ('127.0.0.1', 'localhost'):
            host_hdr = self.headers.get('Host', '')
            if host_hdr:
                try:
                    host_only = host_hdr.split(':')[0].strip().lower()
                    if host_only not in ('localhost', '127.0.0.1', '::1', '[::1]'):
                        print(f"[🛡️ Security Alert] Blocked suspicious Host header (DNS rebinding attempt): {host_hdr}")
                        return False
                except Exception:
                    return False

            # 2. Cross-Site Origin & Referer Defense: Block external webpage requests
            origin = self.headers.get('Origin', '')
            if origin:
                try:
                    host = urllib.parse.urlparse(origin).hostname or ''
                    if host not in ('localhost', '127.0.0.1'):
                        print(f"[🛡️ Security Alert] Blocked cross-origin request from origin: {origin}")
                        return False
                except Exception:
                    return False

            referer = self.headers.get('Referer', '')
            if referer:
                try:
                    host = urllib.parse.urlparse(referer).hostname or ''
                    if host not in ('localhost', '127.0.0.1'):
                        print(f"[🛡️ Security Alert] Blocked cross-origin request from referer: {referer}")
                        return False
                except Exception:
                    return False

        # 3. Authentication Verification (Constant-Time Timing-Attack Resistant)
        if AUTH_TOKEN:
            auth = self.headers.get('Authorization', '')
            cookie_hdr = self.headers.get('Cookie', '')

            # Priority A: Authorization: Bearer <token>
            if auth:
                expected_auth = f"Bearer {AUTH_TOKEN}"
                return hmac.compare_digest(auth, expected_auth)

            # Priority B: SameSite=Strict ghost_session cookie
            if cookie_hdr:
                cookies = dict(c.strip().split('=', 1) for c in cookie_hdr.split(';') if '=' in c)
                cookie_tok = cookies.get('ghost_session', '')
                if cookie_tok and hmac.compare_digest(cookie_tok, AUTH_TOKEN):
                    return True

            # Query parameter tokens (?token=...) and unauthenticated requests are strictly rejected
            return False
        return True

    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path).path
        if parsed_path in ('/health', '/api/v1/health'):
            self._ok({"status": "ok", "app": "ghost_copilot", "version": "3.0.0", "environment": "development"})
            return
        elif parsed_path in ('/ready', '/api/v1/ready'):
            self._ok({"status": "ready", "database": "connected", "ai_configured": bool(GROQ_KEY)})
            return

        # Direct access: serve HUD interface
        if parsed_path in ('/', '/index.html'):
            if HOST in ('127.0.0.1', 'localhost'):
                host_hdr = self.headers.get('Host', '')
                if host_hdr:
                    try:
                        host_only = host_hdr.split(':')[0].strip().lower()
                        if host_only not in ('localhost', '127.0.0.1', '::1', '[::1]'):
                            self.send_error(403, "Forbidden: Invalid Host header")
                            return
                    except Exception:
                        self.send_error(403, "Forbidden")
                        return

            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            # Issue SameSite=Strict cookie so all subsequent browser requests are automatically authenticated
            if AUTH_TOKEN:
                self.send_header('Set-Cookie', f'ghost_session={AUTH_TOKEN}; Path=/; SameSite=Strict; HttpOnly')
            # Top-level defense-in-depth headers
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('X-XSS-Protection', '1; mode=block')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy',
                             f"default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                             f"style-src 'self' 'unsafe-inline'; connect-src *; "
                             f"img-src 'self' data:; object-src 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(HUD.encode())
            return

        if not self.is_authorized():
            self.send_error(403, "Forbidden: Access Denied")
            return
        elif parsed_path == '/stream':
            self.send_response(200); self.send_header('Content-Type','text/event-stream')
            self.send_header('Cache-Control','no-cache'); self.send_header('Connection','keep-alive')
            self.end_headers()
            with sse_lock: sse_clients.append(self)
            try:
                while True: time.sleep(1)
            except Exception: pass
        elif parsed_path == '/sharing_mode':
            # Polled by ghost_copilot.m every 600ms to update NSWindowSharingType
            self._ok({'mode': sharing_mode})
        elif parsed_path == '/get_api_status':
            masked = (GROQ_KEY[:6] + "..." + GROQ_KEY[-4:]) if (GROQ_KEY and len(GROQ_KEY) > 10) else ("***" if GROQ_KEY else "")
            self._ok({'configured': bool(GROQ_KEY), 'masked_key': masked})
        elif parsed_path == '/get_system_prompt':
            self._ok({'prompt': SYSTEM_PROMPT})
        else: self.send_error(404)

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        if length > 1_048_576:  # 1MB maximum payload limit
            self.send_error(413, "Payload Too Large: Maximum 1MB allowed")
            return

        raw_path = getattr(self, 'path', '/')
        parsed_path = urllib.parse.urlparse(raw_path).path
        body = self.rfile.read(length) if length else b'{}'

        # Endpoint to unlock browser session by exchanging token for HttpOnly cookie
        if parsed_path == '/auth/session':
            try:
                data = json.loads(body.decode('utf-8'))
                tok = data.get('token', '').strip()
                if AUTH_TOKEN and hmac.compare_digest(tok, AUTH_TOKEN):
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Set-Cookie', f'ghost_session={AUTH_TOKEN}; Path=/; SameSite=Strict; HttpOnly')
                    self.end_headers()
                    self.wfile.write(json.dumps({'status': 'ok'}).encode())
                    return
            except Exception:
                pass
            self.send_response(401)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'unauthorized', 'error': 'Invalid session token'}).encode())
            return

        if not self.is_authorized():
            self.send_error(403, "Forbidden: Access Denied")
            return

        global auto_mode, manual_recording, sharing_mode, user_custom_duration, gen_id, reading_until, SYSTEM_PROMPT
        parsed_path = urllib.parse.urlparse(self.path).path
        if parsed_path in ('/solve', '/api/v1/solve'):
            q = json.loads(body).get('question','')
            threading.Thread(target=solve, args=(q,), daemon=True).start()
            self._ok({'status':'ok', 'question': q})
        elif parsed_path == '/set_api_key':
            try:
                data = json.loads(body.decode('utf-8'))
                new_key = data.get('api_key', '').strip()
                if new_key and len(new_key) >= 10:
                    global GROQ_KEY
                    GROQ_KEY = new_key
                    os.environ["GROQ_API_KEY"] = new_key
                    env_path = os.path.join(BASE_DIR, ".env")
                    try:
                        lines = []
                        if os.path.exists(env_path):
                            with open(env_path, "r", encoding="utf-8") as f:
                                lines = f.readlines()
                        updated = False
                        new_lines = []
                        for line in lines:
                            if line.strip().startswith("GROQ_API_KEY="):
                                new_lines.append(f"GROQ_API_KEY={new_key}\n")
                                updated = True
                            else:
                                new_lines.append(line)
                        if not updated:
                            new_lines.insert(0, f"GROQ_API_KEY={new_key}\n")
                        with open(env_path, "w", encoding="utf-8") as f:
                            f.writelines(new_lines)
                    except Exception as pe:
                        print(f"[⚠️ Notice] Could not persist key to .env file: {pe}")
                    masked = (new_key[:6] + "..." + new_key[-4:]) if len(new_key) > 10 else "***"
                    print(f"[🔑 API Key Configured via HUD UI] Active key set: {masked}")
                    self._ok({'status': 'ok', 'message': 'API key updated and saved!', 'configured': True, 'masked_key': masked})
                else:
                    self._ok({'status': 'error', 'error': 'Invalid key length'})
            except Exception as e:
                self._ok({'status': 'error', 'error': str(e)})
        elif parsed_path == '/set_system_prompt':
            new_prompt = json.loads(body).get('prompt', '').strip()
            if new_prompt:
                SYSTEM_PROMPT = new_prompt
                print(f"[⚙️ Role Updated] System prompt updated ({len(SYSTEM_PROMPT)} chars)")
                self._ok({'status': 'ok', 'prompt': SYSTEM_PROMPT})
            else:
                self._ok({'status': 'empty', 'prompt': SYSTEM_PROMPT})
        elif parsed_path == '/reset_system_prompt':
            SYSTEM_PROMPT = DEFAULT_SYSTEM_PROMPT
            print("[⚙️ Role Reset] Reverted to default interview system prompt")
            self._ok({'status': 'ok', 'prompt': SYSTEM_PROMPT})
        elif parsed_path == '/set_mode':
            mode = json.loads(body).get('mode','ptt')
            auto_mode = (mode == 'auto')
            if auto_mode:
                broadcast("vadstate", {"state": "listening", "label": "👂 Auto-Listening (speak anytime)..."})
            else:
                broadcast("vadstate", {"state": "idle", "label": "🎤 PTT ready — Spacebar"})
            print(f"[🔁 Mode Switched] Active mode: {mode} (Auto-VAD: {auto_mode})")
            self._ok({'auto': auto_mode, 'mode': mode})
        elif parsed_path == '/skip_question':
            with gen_lock:
                gen_id += 1 # Abort current streaming LLM call immediately
            reading_until = 0.0 # Reset cooldown
            print("[⏭️ Emergency Skip] Aborted active question, resumed auto-listen.")
            broadcast("status", {"state": "ready"})
            broadcast("vadstate", {"state": "listening", "label": "👂 Auto-Listening (speak anytime)..."})
            self._ok({'status': 'skipped'})
        elif parsed_path == '/set_duration':
            dur = json.loads(body).get('duration', 'auto')
            try:
                user_custom_duration = int(dur) if str(dur).isdigit() else str(dur)
            except Exception:
                user_custom_duration = 'auto'
            print(f"[⏱️ Duration Setting] Display & cooldown duration: {user_custom_duration}")
            self._ok({'duration': user_custom_duration})
        elif parsed_path == '/set_sharing':
            sharing_mode = json.loads(body).get('mode', 'hidden')
            print(f"[👁 Screen share] {sharing_mode}")
            self._ok({'sharing': sharing_mode})
        elif parsed_path == '/toggle_ptt':
            if manual_recording:
                manual_recording = False
                broadcast("ptt_state", {"recording": False})
                self._ok({'status': 'stopped', 'recording': False})
            else:
                manual_recording = True
                threading.Thread(target=ptt_record, daemon=True).start()
                broadcast("ptt_state", {"recording": True})
                self._ok({'status': 'recording', 'recording': True})
        elif parsed_path == '/record_start':
            manual_recording = True
            threading.Thread(target=ptt_record, daemon=True).start()
            broadcast("ptt_state", {"recording": True})
            self._ok({'status':'recording', 'recording': True})
        elif parsed_path == '/record_stop':
            manual_recording = False
            broadcast("ptt_state", {"recording": False})
            self._ok({'status':'stopped', 'recording': False})
        else: self.send_error(404)

    def _ok(self, data):
        self.send_response(200); self.send_header('Content-Type','application/json'); self.end_headers()
        self.wfile.write(json.dumps(data).encode())


def main():
    print("="*52); print("  🎙️ INTERVIEW ASSISTANT v3 (DESKTOP ENGINE)"); print("="*52)
    print(f"  Bound to: http://{HOST}:{PORT}")
    print(f"  AI Key configured: {'YES' if GROQ_KEY else 'NO'}")
    ThreadingHTTPServer.allow_reuse_address = True
    server = None
    for attempt in range(5):
        try:
            server = ThreadingHTTPServer((HOST, PORT), Handler)
            break
        except OSError as e:
            if attempt < 4:
                print(f"[⚠️ Port {PORT} in TIME_WAIT] Retrying bind in 1 second... ({attempt + 1}/5)")
                time.sleep(1)
            else:
                print(f"[❌ Fatal] Could not bind to http://{HOST}:{PORT}: {e}")
                sys.exit(1)

    print(f"  Interview Assistant Desktop Server running on http://{HOST}:{PORT}")

    detect_audio_devices()
    threading.Thread(target=clipboard_watcher, daemon=True).start()
    threading.Thread(target=auto_vad_loop, daemon=True).start()
    threading.Thread(target=speaker_vad_loop, daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Shutting down] Interview Assistant Desktop Server stopped cleanly.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
