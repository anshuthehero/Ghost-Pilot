#!/usr/bin/env python3
"""
Ghost Copilot Launcher
-----------------------
Native desktop setup wizard + launcher for macOS and Windows.
Double-click to open — no browser, no terminal, no personal data.

NEW FILE: does not modify any existing Ghost-Pilot code.
"""

import os
import re
import sys
import shutil
import subprocess
import time
import platform
import zipfile
import urllib.request


# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
ENV_PATH   = os.path.join(BASE_DIR, ".env")
APP_PY     = os.path.join(BASE_DIR, "app.py")
TOKEN_FILE = os.path.join(os.path.expanduser("~"), ".ghost_copilot", "session_token")
DAEMON_URL = "http://127.0.0.1:9471"

IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"

# ── Check PyQt6 before anything else ─────────────────────────────────────────
try:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QPushButton, QLineEdit, QStackedWidget,
        QGraphicsDropShadowEffect, QProgressBar, QFrame, QSizePolicy,
    )
    from PyQt6.QtCore import (
        Qt, QThread, pyqtSignal, QTimer, QPoint, QSize, QPropertyAnimation,
        QEasingCurve, QUrl,
    )
    from PyQt6.QtGui import (
        QFont, QColor, QPainter, QBrush, QPen, QLinearGradient,
        QPixmap, QIcon, QPainterPath, QCursor, QFontDatabase,
    )
    try:
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        from PyQt6.QtWebEngineCore import QWebEngineSettings, QWebEnginePage, QWebEngineHttpRequest
        from PyQt6.QtNetwork import QNetworkCookie
        from PyQt6.QtCore import QByteArray
        HAS_WEBENGINE = True
    except ImportError:
        HAS_WEBENGINE = False

except ImportError:
    if __name__ == "__main__":
        print(
            "\n[Ghost Copilot Launcher]\n"
            "PyQt6 is required but not installed.\n"
            "Run:  pip install PyQt6 PyQt6-WebEngine\n"
            "Then double-click this launcher again.\n"
        )
        sys.exit(1)
    else:
        class _MockSignal:
            def __init__(self, *args, **kwargs): pass
            def connect(self, *args, **kwargs): pass
            def emit(self, *args, **kwargs): pass
        pyqtSignal = _MockSignal

        class _DummyMeta(type):
            def __getattr__(cls, name):
                return cls

        class _Dummy(metaclass=_DummyMeta):
            def __init__(self, *args, **kwargs): pass
            def __call__(self, *args, **kwargs): return self
            def __getattr__(self, name): return self

        QApplication = QMainWindow = QWidget = QVBoxLayout = QHBoxLayout = _Dummy
        QLabel = QPushButton = QLineEdit = QStackedWidget = _Dummy
        QGraphicsDropShadowEffect = QProgressBar = QFrame = QSizePolicy = _Dummy
        Qt = QThread = QTimer = QPoint = QSize = QPropertyAnimation = _Dummy
        QEasingCurve = QUrl = QFont = QColor = QPainter = QBrush = QPen = QLinearGradient = _Dummy
        QPixmap = QIcon = QPainterPath = QCursor = QFontDatabase = _Dummy
        QWebEngineView = QWebEngineSettings = QWebEnginePage = QWebEngineHttpRequest = _Dummy
        QNetworkCookie = QByteArray = _Dummy
        HAS_WEBENGINE = False


# ── Palette ───────────────────────────────────────────────────────────────────
BG          = "#0D0D10"
SURFACE     = "#14141A"
SURFACE2    = "#1B1B25"
BORDER      = "#2A2A3C"
ACCENT      = "#7C3AED"
ACCENT_HOV  = "#9D5FFF"
ACCENT_PRE  = "#6025CC"
TEXT        = "#EDEDFF"
TEXT_DIM    = "#6B7180"
TEXT_MUT    = "#30303F"
SUCCESS     = "#22C55E"
WARN        = "#F59E0B"
ERROR       = "#EF4444"
INFO        = "#38BDF8"


# ── .env helpers (same safe logic as app.py /set_api_key — read-only mirror) ──
_KEY_RE = re.compile(r'^[a-zA-Z0-9_.\-]{10,128}$')

def _read_api_key() -> str:
    if not os.path.exists(ENV_PATH):
        return ""
    try:
        with open(ENV_PATH, "r", encoding="utf-8-sig", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if line.startswith("GROQ_API_KEY="):
                    val = line.split("=", 1)[1].strip().strip("'\"")
                    return val
    except OSError:
        pass
    return ""

def _write_api_key(key: str) -> bool:
    """Write GROQ_API_KEY to .env safely. Rejects bad chars (mirrors SEC-17 fix)."""
    if not _KEY_RE.match(key):
        return False
    lines: list[str] = []
    if os.path.exists(ENV_PATH):
        try:
            with open(ENV_PATH, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except OSError:
            pass
    new_lines: list[str] = []
    updated = False
    for line in lines:
        if line.strip().startswith("GROQ_API_KEY="):
            new_lines.append(f"GROQ_API_KEY={key}\n")
            updated = True
        else:
            new_lines.append(line)
    if not updated:
        new_lines.insert(0, f"GROQ_API_KEY={key}\n")
    try:
        with open(ENV_PATH, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
        return True
    except OSError:
        return False

def _read_session_token() -> str:
    env_token = os.environ.get("COPILOT_AUTH_TOKEN", "").strip()
    if env_token:
        return env_token
    for candidate in (TOKEN_FILE, os.path.join(BASE_DIR, ".session_token")):
        try:
            if os.path.exists(candidate):
                with open(candidate, "r", encoding="utf-8") as f:
                    tok = f.read().strip()
                    if tok:
                        return tok
        except OSError:
            pass
    return ""



# ── Background system-check worker ───────────────────────────────────────────
class CheckWorker(QThread):
    """Runs each check in order and emits results — never blocks the GUI."""
    result = pyqtSignal(str, bool, str)   # (label, passed, detail)
    done   = pyqtSignal()

    def run(self) -> None:
        checks = [
            ("Python Engine",  self._chk_python),
            ("Display Engine", self._chk_qt),
            ("Audio / FFmpeg", self._chk_ffmpeg),
            ("API Key",        self._chk_apikey),
        ]
        for name, fn in checks:
            ok, detail = fn()
            self.result.emit(name, ok, detail)
            time.sleep(0.35)
        self.done.emit()

    # -- individual checks -------------------------------------------------- #
    def _chk_python(self):
        v = sys.version_info
        ok = v >= (3, 8)
        return ok, f"Python {v.major}.{v.minor}.{v.micro}"

    def _chk_qt(self):
        try:
            from PyQt6.QtCore import PYQT_VERSION_STR
            return True, f"PyQt6 {PYQT_VERSION_STR}"
        except Exception:
            return False, "Not found"

    def _chk_ffmpeg(self):
        try:
            from client.core.ffmpeg import find_ffmpeg
            info = find_ffmpeg()
            if info.get("status") == "READY":
                return True, "Ready (" + ("Bundled" if info.get("is_bundled") else "System") + ")"
        except Exception:
            pass
        if shutil.which("ffmpeg"):
            return True, "Found in PATH"
        # local bundled binary?
        for sub in ("bin", "ffmpeg", "."):
            candidate = os.path.join(BASE_DIR, sub, "ffmpeg" + (".exe" if IS_WIN else ""))
            if os.path.exists(candidate):
                return True, "Bundled binary"
        return False, "Not found — install ffmpeg for audio"

    def _chk_apikey(self):
        key = _read_api_key()
        if key and _KEY_RE.match(key):
            n = len(key)
            if n > 10:
                masked = key[:6] + "•" * max(0, n - 10) + key[-4:]
            else:
                masked = key[:4] + "•" * (n - 4)
            return True, masked
        return False, "Not configured — enter below"



class FFmpegInstallWorker(QThread):
    """Downloads and extracts portable FFmpeg in background — zero-install for user."""
    progress = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def run(self) -> None:
        try:
            bin_dir = os.path.join(BASE_DIR, "bin")
            os.makedirs(bin_dir, exist_ok=True)
            if IS_WIN:
                dest = os.path.join(bin_dir, "ffmpeg.exe")
                # 1. Try winget first if available
                if shutil.which("winget"):
                    self.progress.emit("Running WinGet install...")
                    res = subprocess.run(
                        ["winget", "install", "-e", "--id", "Gyan.FFmpeg", "--accept-source-agreements", "--accept-package-agreements"],
                        capture_output=True, timeout=120
                    )
                    if res.returncode == 0:
                        self.finished.emit(True, "Installed via WinGet")
                        return

                # 2. Direct download of essentials zip from gyan.dev
                self.progress.emit("Downloading audio engine...")
                url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
                zip_path = os.path.join(bin_dir, "ffmpeg_dl.zip")
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
                with urllib.request.urlopen(req, timeout=60) as resp, open(zip_path, "wb") as out_f:
                    shutil.copyfileobj(resp, out_f)
                self.progress.emit("Extracting ffmpeg.exe...")
                with zipfile.ZipFile(zip_path, 'r') as zf:
                    for name in zf.namelist():
                        if name.endswith("ffmpeg.exe"):
                            with zf.open(name) as src, open(dest, "wb") as dst:
                                shutil.copyfileobj(src, dst)
                            break
                if os.path.exists(zip_path):
                    try: os.remove(zip_path)
                    except OSError: pass
                if os.path.exists(dest):
                    self.finished.emit(True, "Bundled binary")
                    return
            elif IS_MAC:
                dest = os.path.join(bin_dir, "ffmpeg")
                # 1. Try brew if available
                if shutil.which("brew"):
                    self.progress.emit("Running brew install...")
                    res = subprocess.run(["brew", "install", "ffmpeg"], capture_output=True, timeout=180)
                    if res.returncode == 0:
                        self.finished.emit(True, "Installed via brew")
                        return

                # 2. Portable static macOS binary
                self.progress.emit("Downloading audio engine...")
                url = "https://evermeet.cx/ffmpeg/getrelease/zip"
                zip_path = os.path.join(bin_dir, "ffmpeg_dl.zip")
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
                with urllib.request.urlopen(req, timeout=60) as resp, open(zip_path, "wb") as out_f:
                    shutil.copyfileobj(resp, out_f)
                self.progress.emit("Extracting ffmpeg...")
                with zipfile.ZipFile(zip_path, 'r') as zf:
                    for name in zf.namelist():
                        if name.split("/")[-1] == "ffmpeg":
                            with zf.open(name) as src, open(dest, "wb") as dst:
                                shutil.copyfileobj(src, dst)
                            break
                if os.path.exists(zip_path):
                    try: os.remove(zip_path)
                    except OSError: pass
                if os.path.exists(dest):
                    os.chmod(dest, 0o755)
                    self.finished.emit(True, "Bundled binary")
                    return
            self.finished.emit(False, "Auto-install unavailable")

        except Exception as e:
            self.finished.emit(False, str(e))


# ── Shared widget helpers ─────────────────────────────────────────────────────
def _lbl(text: str, size: int = 13, color: str = TEXT,
         bold: bool = False,
         align=Qt.AlignmentFlag.AlignLeft) -> QLabel:
    l = QLabel(text)
    f = QFont()
    f.setPointSize(size)
    f.setBold(bold)
    l.setFont(f)
    l.setStyleSheet(f"color: {color}; background: transparent;")
    l.setAlignment(align)
    return l

def _hline() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setFixedHeight(1)
    f.setStyleSheet(f"background: {BORDER}; border: none;")
    return f

def _btn(text: str, primary: bool = True) -> QPushButton:
    b = QPushButton(text)
    b.setFixedHeight(42)
    f = QFont()
    f.setPointSize(13)
    f.setBold(True)
    b.setFont(f)
    if primary:
        b.setStyleSheet(
            f"QPushButton{{background:{ACCENT};color:white;border:none;border-radius:8px;}}"
            f"QPushButton:hover{{background:{ACCENT_HOV};}}"
            f"QPushButton:pressed{{background:{ACCENT_PRE};}}"
            f"QPushButton:disabled{{background:{TEXT_MUT};color:{TEXT_DIM};}}"
        )
    else:
        b.setStyleSheet(
            f"QPushButton{{background:transparent;color:{ACCENT};border:1px solid {ACCENT};"
            f"border-radius:8px;}}"
            f"QPushButton:hover{{background:{ACCENT}18;}}"
        )
    return b


# ── Custom frameless title bar ────────────────────────────────────────────────
class _TitleBar(QWidget):
    def __init__(self, parent: QMainWindow) -> None:
        super().__init__(parent)
        self._win      = parent
        self._drag_pos: QPoint | None = None

        self.setFixedHeight(44)
        self.setStyleSheet(
            f"background: {SURFACE}; border-bottom: 1px solid {BORDER};"
            f"border-top-left-radius: 12px; border-top-right-radius: 12px;"
        )

        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 0, 10, 0)
        lay.setSpacing(8)

        dot = QLabel("●")
        dot.setFont(QFont("", 10))
        dot.setStyleSheet(f"color: {ACCENT}; background: transparent;")
        lay.addWidget(dot)

        title_f = QFont()
        title_f.setPointSize(13)
        title_f.setBold(True)
        title = QLabel("Ghost Copilot")
        title.setFont(title_f)
        title.setStyleSheet(f"color: {TEXT}; background: transparent;")
        lay.addWidget(title)
        lay.addStretch()

        for char, slot in [("—", parent.showMinimized), ("✕", parent.close)]:
            b = QPushButton(char)
            b.setFixedSize(30, 30)
            b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            b.setStyleSheet(
                f"QPushButton{{color:{TEXT_DIM};background:transparent;border:none;"
                f"font-size:14px;border-radius:6px;}}"
                f"QPushButton:hover{{color:{TEXT};background:{BORDER};}}"
            )
            b.clicked.connect(slot)
            lay.addWidget(b)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self._win.pos()

    def mouseMoveEvent(self, e):
        if self._drag_pos and e.buttons() == Qt.MouseButton.LeftButton:
            self._win.move(e.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, e):
        self._drag_pos = None


# ── Page 0: Animated splash ───────────────────────────────────────────────────
class _SplashPage(QWidget):
    finished = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.setStyleSheet(f"background: {BG};")

        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(14)
        lay.setContentsMargins(40, 60, 40, 60)

        name  = _lbl("GHOST COPILOT", 22, bold=True,
                      align=Qt.AlignmentFlag.AlignCenter)
        sub   = _lbl("Stealth Desktop Assistant", 12, TEXT_DIM,
                      align=Qt.AlignmentFlag.AlignCenter)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(3)
        self.bar.setStyleSheet(
            f"QProgressBar{{background:{BORDER};border-radius:2px;border:none;}}"
            f"QProgressBar::chunk{{background:{ACCENT};border-radius:2px;}}"
        )

        ver = _lbl(f"v3.0 · {platform.system()} {platform.machine()}",
                   10, TEXT_MUT, align=Qt.AlignmentFlag.AlignCenter)

        for w in (name, sub, self.bar, ver):
            lay.addWidget(w)

        self._val = 0
        self._t = QTimer(self)
        self._t.timeout.connect(self._tick)
        self._t.start(10)   # fast 80ms splash

    def _tick(self):
        self._val += 20
        self.bar.setValue(min(self._val, 100))
        if self._val >= 100:
            self._t.stop()
            self.finished.emit()



# ── Page 1: System checks + API key entry ────────────────────────────────────
class _SetupPage(QWidget):
    launch_requested = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.setStyleSheet(f"background: {BG};")
        self._rows: dict[str, tuple[QLabel, QLabel]] = {}
        self._checks_done = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 22, 28, 28)
        outer.setSpacing(14)

        # Header
        outer.addWidget(_lbl("System Check", 18, bold=True))
        outer.addWidget(_lbl("Verifying your environment before launch.", 12, TEXT_DIM))
        outer.addWidget(_hline())

        # ── Check rows ──
        self.ffmpeg_btn = QPushButton("Auto-Install")
        self.ffmpeg_btn.setFixedHeight(22)
        self.ffmpeg_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.ffmpeg_btn.setStyleSheet(
            f"QPushButton{{background:{ACCENT};color:white;border:none;border-radius:4px;padding:0 8px;font-size:10px;font-weight:bold;}}"
            f"QPushButton:hover{{background:{ACCENT_HOV};}}"
            f"QPushButton:disabled{{background:{TEXT_MUT};color:{TEXT_DIM};}}"
        )
        self.ffmpeg_btn.clicked.connect(self._start_ffmpeg_install)
        self.ffmpeg_btn.hide()

        checks_box = QVBoxLayout()
        checks_box.setSpacing(12)
        for name in ("Python Engine", "Display Engine", "Audio / FFmpeg", "API Key"):
            row = QHBoxLayout()
            row.setSpacing(10)

            dot = QLabel("○")
            dot.setFixedWidth(20)
            dot.setStyleSheet(f"color:{TEXT_MUT};font-size:16px;background:transparent;")

            name_lbl = _lbl(name, 12)
            name_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

            detail_lbl = _lbl("—", 11, TEXT_DIM)
            detail_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            row.addWidget(dot)
            row.addWidget(name_lbl)
            if name == "Audio / FFmpeg":
                row.addWidget(self.ffmpeg_btn)
            row.addStretch()
            row.addWidget(detail_lbl)
            self._rows[name] = (dot, detail_lbl)
            checks_box.addLayout(row)

        outer.addLayout(checks_box)
        outer.addWidget(_hline())

        # ── API Key section ──
        outer.addWidget(_lbl("Groq API Key", 13, bold=True))
        outer.addWidget(
            _lbl("Required for AI. Free at console.groq.com — sign in, copy your key.", 11, TEXT_DIM)
        )

        key_row = QHBoxLayout()
        key_row.setSpacing(8)

        self.key_input = QLineEdit()
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_input.setPlaceholderText("your_groq_api_key")
        self.key_input.setFixedHeight(38)
        self.key_input.setStyleSheet(
            f"QLineEdit{{background:{SURFACE2};color:{TEXT};border:1px solid {BORDER};"
            f"border-radius:7px;padding:0 12px;font-size:12px;letter-spacing:1px;}}"
            f"QLineEdit:focus{{border:1px solid {ACCENT};}}"
        )
        self.key_input.textChanged.connect(self._on_key_edit)

        self.save_btn = QPushButton("Save")
        self.save_btn.setFixedSize(62, 38)
        self.save_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.save_btn.setStyleSheet(
            f"QPushButton{{background:{ACCENT};color:white;border:none;border-radius:7px;"
            f"font-size:12px;font-weight:bold;}}"
            f"QPushButton:hover{{background:{ACCENT_HOV};}}"
            f"QPushButton:pressed{{background:{ACCENT_PRE};}}"
        )
        self.save_btn.clicked.connect(self._save_key)

        key_row.addWidget(self.key_input)
        key_row.addWidget(self.save_btn)
        outer.addLayout(key_row)

        self.key_status = _lbl("", 11, TEXT_DIM)
        outer.addWidget(self.key_status)
        outer.addStretch()

        # ── Launch button ──
        self.launch_btn = _btn("Launch Ghost Copilot", primary=True)
        self.launch_btn.setFixedHeight(52)
        self.launch_btn.setEnabled(False)
        self.launch_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.launch_btn.clicked.connect(self.launch_requested.emit)

        outer.addWidget(self.launch_btn)

        # Pre-fill existing key
        existing = _read_api_key()
        if existing:
            self.key_input.setText(existing)

        # Run checks in background
        self._worker = CheckWorker()
        self._worker.result.connect(self._on_check_result)
        self._worker.done.connect(self._on_checks_done)
        self._worker.start()

    # ── slots ── #
    def _on_check_result(self, name: str, ok: bool, detail: str) -> None:
        if name not in self._rows:
            return
        dot, detail_lbl = self._rows[name]
        dot.setText("✓" if ok else "✗")
        dot.setStyleSheet(
            f"color:{SUCCESS if ok else WARN};font-size:16px;background:transparent;"
        )
        detail_lbl.setText(detail)
        detail_lbl.setStyleSheet(
            f"color:{SUCCESS if ok else TEXT_DIM};font-size:11px;"
        )
        if name == "Audio / FFmpeg":
            if not ok:
                self.ffmpeg_btn.show()
            else:
                self.ffmpeg_btn.hide()

    def _start_ffmpeg_install(self) -> None:
        self.ffmpeg_btn.setEnabled(False)
        self.ffmpeg_btn.setText("Installing...")
        dot, detail_lbl = self._rows["Audio / FFmpeg"]
        detail_lbl.setText("Starting...")
        detail_lbl.setStyleSheet(f"color:{INFO};font-size:11px;")
        self._ff_worker = FFmpegInstallWorker()
        self._ff_worker.progress.connect(lambda msg: detail_lbl.setText(msg))
        self._ff_worker.finished.connect(self._on_ffmpeg_finished)
        self._ff_worker.start()

    def _on_ffmpeg_finished(self, success: bool, msg: str) -> None:
        dot, detail_lbl = self._rows["Audio / FFmpeg"]
        if success:
            dot.setText("✓")
            dot.setStyleSheet(f"color:{SUCCESS};font-size:16px;background:transparent;")
            detail_lbl.setText(msg)
            detail_lbl.setStyleSheet(f"color:{SUCCESS};font-size:11px;")
            self.ffmpeg_btn.hide()
        else:
            dot.setText("✗")
            dot.setStyleSheet(f"color:{WARN};font-size:16px;background:transparent;")
            detail_lbl.setText("Manual setup needed")
            detail_lbl.setStyleSheet(f"color:{WARN};font-size:11px;")
            self.ffmpeg_btn.setText("Retry")
            self.ffmpeg_btn.setEnabled(True)

    def _on_checks_done(self) -> None:
        self._checks_done = True
        self._refresh_launch_btn()

    def _on_key_edit(self, text: str) -> None:
        self.key_status.clear()
        self._refresh_launch_btn()

    def _refresh_launch_btn(self) -> None:
        # BUG-06 fix: require both a valid key AND checks finished
        if not self._checks_done:
            return
        key = _read_api_key() or self.key_input.text().strip()
        self.launch_btn.setEnabled(bool(key and _KEY_RE.match(key)))

    def _save_key(self) -> None:
        key = self.key_input.text().strip()
        if not _KEY_RE.match(key):
            self.key_status.setText("Key must be 10-128 alphanumeric characters.")
            self.key_status.setStyleSheet(f"color:{WARN};font-size:11px;")
            return
        if _write_api_key(key):
            self.key_status.setText("Saved to local .env - never leaves this device.")
            self.key_status.setStyleSheet(f"color:{SUCCESS};font-size:11px;")
            if "API Key" in self._rows:
                dot, det = self._rows["API Key"]
                dot.setText("✓")
                dot.setStyleSheet(f"color:{SUCCESS};font-size:16px;background:transparent;")
                # BUG-01 fix: safe masking that never overlaps or crashes
                n = len(key)
                if n > 10:
                    masked = key[:6] + "*" * max(0, n - 10) + key[-4:]
                else:
                    masked = key[:4] + "*" * (n - 4)
                det.setText(masked)
                det.setStyleSheet(f"color:{SUCCESS};font-size:11px;")
            self._refresh_launch_btn()
        else:
            self.key_status.setText("Could not write to .env - check folder permissions.")
            self.key_status.setStyleSheet(f"color:{ERROR};font-size:11px;")


# ── HUD floating window (appears after launch) ────────────────────────────────
class _DragBar(QWidget):
    """Mini title bar for the HUD that supports drag-to-move without monkey-patching."""
    def __init__(self, parent_win: QMainWindow) -> None:
        super().__init__(parent_win)
        self._win = parent_win
        self._drag_pos: QPoint | None = None
        self.setFixedHeight(28)
        self.setStyleSheet(
            f"background:{SURFACE};border-bottom:1px solid {BORDER};"
            f"border-top-left-radius:12px;border-top-right-radius:12px;"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 8, 0)
        lbl = QLabel("Ghost Copilot")
        lbl.setStyleSheet(f"color:{TEXT_DIM};font-size:11px;background:transparent;")
        lay.addWidget(lbl)

        lay.addStretch()
        close_b = QPushButton("✕")
        close_b.setFixedSize(22, 22)
        close_b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        close_b.setStyleSheet(
            f"QPushButton{{color:{TEXT_DIM};background:transparent;border:none;"
            f"font-size:12px;border-radius:4px;}}"
            f"QPushButton:hover{{color:{TEXT};background:{BORDER};}}"
        )
        close_b.clicked.connect(parent_win.close)
        lay.addWidget(close_b)

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self._win.pos()

    def mouseMoveEvent(self, e) -> None:
        if self._drag_pos and e.buttons() == Qt.MouseButton.LeftButton:
            self._win.move(e.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, e) -> None:
        self._drag_pos = None


class _HUDWindow(QMainWindow):
    """Frameless, always-on-top WebEngine view of the daemon HUD."""

    def __init__(self, auth_token: str = "", daemon: "subprocess.Popen | None" = None) -> None:
        super().__init__()
        self._auth_token = auth_token
        self._daemon = daemon   # BUG-10 fix: HUD owns the daemon ref so closing HUD kills it

        self.setWindowTitle("Ghost Copilot")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Position top-right corner
        screen = QApplication.primaryScreen()
        if screen:
            g = screen.availableGeometry()
            self.setGeometry(g.x() + g.width() - 476, g.y() + 12, 460, 800)

        root = QWidget()
        root.setObjectName("hudroot")
        root.setStyleSheet(
            f"#hudroot{{background:{BG};border:1px solid {BORDER};"
            f"border-radius:12px;}}"
        )
        self.setCentralWidget(root)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(50)
        shadow.setXOffset(0)
        shadow.setYOffset(10)
        shadow.setColor(QColor(0, 0, 0, 200))
        root.setGraphicsEffect(shadow)

        lay = QVBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # BUG-07 fix: use proper _DragBar subclass instead of monkey-patching
        lay.addWidget(_DragBar(self))

        # Content
        if HAS_WEBENGINE:
            self._setup_webengine(lay, auth_token)
        else:
            fallback = _lbl(
                f"Open {DAEMON_URL} in your browser.",
                13, WARN, align=Qt.AlignmentFlag.AlignCenter
            )
            lay.addWidget(fallback)

        # Windows: exclude from screen-share capture
        if IS_WIN:
            QTimer.singleShot(500, self._apply_win_affinity)

    def closeEvent(self, e) -> None:
        # BUG-10 fix: kill daemon when HUD is closed
        if self._daemon and self._daemon.poll() is None:
            self._daemon.terminate()
        super().closeEvent(e)

    def _setup_webengine(self, lay: QVBoxLayout, auth_token: str) -> None:
        class _LocalPage(QWebEnginePage):
            def acceptNavigationRequest(self, url, nav_type, is_main):
                host   = url.host().lower()
                scheme = url.scheme().lower()
                if scheme in ("about", "data", "qrc"):
                    return True
                if host in ("127.0.0.1", "localhost"):
                    return True
                return False  # block all external navigation

            def featurePermissionRequested(self, url, feature) -> None:
                """Auto-grant mic/audio for localhost — required for voice capture."""
                try:
                    if url.host().lower() not in ("127.0.0.1", "localhost"):
                        self.setFeaturePermission(url, feature, QWebEnginePage.PermissionPolicy.PermissionDeniedByUser)
                        return
                    try:
                        F = QWebEnginePage.Feature
                        audio_features = {
                            F.MediaAudioCapture, F.MediaVideoCapture,
                            F.MediaAudioVideoCapture, F.DesktopAudioVideoCapture,
                            F.DesktopVideoCapture,
                        }
                        policy = (
                            QWebEnginePage.PermissionPolicy.PermissionGrantedByUser
                            if feature in audio_features
                            else QWebEnginePage.PermissionPolicy.PermissionDeniedByUser
                        )
                    except AttributeError:
                        policy = QWebEnginePage.PermissionPolicy.PermissionGrantedByUser
                    self.setFeaturePermission(url, feature, policy)
                except Exception:
                    try:
                        self.setFeaturePermission(url, feature, QWebEnginePage.PermissionPolicy.PermissionGrantedByUser)
                    except Exception:
                        pass

        view = QWebEngineView()
        page = _LocalPage(view)
        page.setBackgroundColor(QColor(13, 13, 16))
        view.setPage(page)
        s = view.settings()
        try:
            s.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, False)
            s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, False)
            s.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        except Exception:
            pass

        if auth_token:
            try:
                cookie = QNetworkCookie(b"ghost_session", auth_token.encode())
                cookie.setDomain("127.0.0.1")
                cookie.setPath("/")
                cookie.setHttpOnly(True)
                view.page().profile().cookieStore().setCookie(
                    cookie, QUrl("http://127.0.0.1:9471")
                )
            except Exception:
                pass

            try:
                req = QWebEngineHttpRequest(QUrl(DAEMON_URL))
                req.setHeader(
                    QByteArray(b"Authorization"),
                    QByteArray(f"Bearer {auth_token}".encode())
                )
                view.load(req)
            except Exception:
                view.setUrl(QUrl(DAEMON_URL))
        else:
            view.setUrl(QUrl(DAEMON_URL))

        def _on_load_finish(ok: bool):
            if not ok:
                QTimer.singleShot(700, lambda: view.setUrl(QUrl(DAEMON_URL)))
        view.loadFinished.connect(_on_load_finish)

        lay.addWidget(view)


    def _apply_win_affinity(self) -> None:
        try:
            import ctypes
            WDA_EXCLUDEFROMCAPTURE = 0x00000011
            hwnd = int(self.winId())
            ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
        except Exception:
            pass


# ── Main launcher wizard window ───────────────────────────────────────────────
class _LauncherWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._daemon: subprocess.Popen | None = None
        self._hud: _HUDWindow | None = None

        self.setWindowTitle("Ghost Copilot")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(480, 580)

        # Center on screen
        screen = QApplication.primaryScreen()
        if screen:
            g = screen.availableGeometry()
            self.move(
                g.x() + (g.width()  - 480) // 2,
                g.y() + (g.height() - 580) // 2,
            )

        # Root card
        root = QWidget()
        root.setObjectName("lroot")
        root.setStyleSheet(
            f"#lroot{{background:{BG};border:1px solid {BORDER};border-radius:12px;}}"
        )
        self.setCentralWidget(root)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(48)
        shadow.setXOffset(0)
        shadow.setYOffset(10)
        shadow.setColor(QColor(0, 0, 0, 200))
        root.setGraphicsEffect(shadow)

        lay = QVBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._title_bar = _TitleBar(self)
        lay.addWidget(self._title_bar)

        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background: transparent;")
        lay.addWidget(self._stack)

        self._splash = _SplashPage()
        self._splash.finished.connect(self._show_setup)
        self._stack.addWidget(self._splash)   # 0

        self._setup = _SetupPage()
        self._setup.launch_requested.connect(self._on_launch)
        self._stack.addWidget(self._setup)    # 1

        self._stack.setCurrentIndex(0)

    # ── transitions ── #
    def _show_setup(self) -> None:
        self._stack.setCurrentIndex(1)

    def _is_daemon_healthy(self) -> bool:
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open("http://127.0.0.1:9471/health", timeout=0.3) as resp:
                return resp.status < 500
        except Exception:
            return False

    def _on_launch(self) -> None:
        self._setup.launch_btn.setText("Starting engine...")
        self._setup.launch_btn.setEnabled(False)
        self._setup.key_status.clear()

        # Fast path: If daemon is already running, open HUD instantly (< 50ms)
        if self._is_daemon_healthy():
            self._open_hud()
            return

        if not os.path.exists(APP_PY):
            self._setup.launch_btn.setText("Launch Ghost Copilot")
            self._setup.launch_btn.setEnabled(True)
            self._setup.key_status.setText("app.py not found in installation folder.")
            self._setup.key_status.setStyleSheet(f"color:{ERROR};font-size:11px;")
            return

        self._start_daemon()

        self._poll_attempts = 0
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_daemon)
        self._poll_timer.start(250)   # fast polling every 250ms

    def _poll_daemon(self) -> None:
        """Poll until daemon responds on port 9471, then open HUD."""
        self._poll_attempts += 1

        # Check if the process crashed/exited immediately
        if self._daemon and self._daemon.poll() is not None:
            self._poll_timer.stop()
            err_line = ""
            try:
                if self._daemon.stderr:
                    err_bytes = self._daemon.stderr.read()
                    if err_bytes:
                        lines = err_bytes.decode("utf-8", errors="replace").strip().splitlines()
                        err_line = lines[-1] if lines else ""
            except Exception:
                pass
            msg = f"Engine failed: {err_line[:60]}" if err_line else f"Engine exited with code {self._daemon.returncode}"
            self._setup.launch_btn.setText("Launch Ghost Copilot")
            self._setup.launch_btn.setEnabled(True)
            self._setup.key_status.setText(msg)
            self._setup.key_status.setStyleSheet(f"color:{ERROR};font-size:11px;")
            return

        if self._is_daemon_healthy():
            self._poll_timer.stop()
            self._open_hud()
        elif self._poll_attempts >= 30:   # 30 × 250ms = 7.5s timeout
            self._poll_timer.stop()
            self._setup.launch_btn.setText("Retry Launch")
            self._setup.launch_btn.setEnabled(True)
            self._setup.key_status.setText("Engine startup timed out. Click Retry.")
            self._setup.key_status.setStyleSheet(f"color:{WARN};font-size:11px;")

    def _start_daemon(self) -> None:
        # Terminate any stale zombie processes on Windows
        if IS_WIN:
            try:
                subprocess.run(
                    ["taskkill", "/F", "/IM", "python.exe", "/FI", "WINDOWTITLE eq Ghost Copilot Engine*"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2
                )
            except Exception:
                pass

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        bin_dir = os.path.join(BASE_DIR, "bin")
        if os.path.exists(bin_dir):
            env["PATH"] = bin_dir + os.pathsep + env.get("PATH", "")

        try:
            self._daemon = subprocess.Popen(
                [sys.executable, APP_PY],
                cwd=BASE_DIR,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except OSError as e:
            self._setup.launch_btn.setText("Launch Ghost Copilot")
            self._setup.launch_btn.setEnabled(True)
            self._setup.key_status.setText(f"Could not start engine: {e}")
            self._setup.key_status.setStyleSheet(f"color:{ERROR};font-size:11px;")

    def _open_hud(self) -> None:
        token = _read_session_token()
        # BUG-10 fix: pass daemon ref to HUD so HUD.closeEvent kills it
        self._hud = _HUDWindow(auth_token=token, daemon=self._daemon)
        self._daemon = None   # HUD now owns it
        self._hud.show()
        self.hide()


    # ── cleanup ── #
    def closeEvent(self, e) -> None:
        if self._daemon and self._daemon.poll() is None:
            self._daemon.terminate()
        super().closeEvent(e)


# ── Entry point ───────────────────────────────────────────────────────────────
def main() -> None:
    # On macOS, high-DPI is automatic; on Windows we need this attribute
    if IS_WIN:
        try:
            from PyQt6.QtCore import Qt as _Qt
            QApplication.setHighDpiScaleFactorRoundingPolicy(
                _Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
            )
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName("Ghost Copilot")
    app.setApplicationDisplayName("Ghost Copilot")

    # Global stylesheet — dark scrollbars + font stack
    app.setStyleSheet(
        f"* {{font-family: -apple-system, 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;}}"
        f"QScrollBar:vertical{{background:{SURFACE};width:6px;border:none;margin:0;}}"
        f"QScrollBar::handle:vertical{{background:{BORDER};border-radius:3px;min-height:30px;}}"
        f"QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{{height:0px;}}"
        f"QScrollBar:horizontal{{background:{SURFACE};height:6px;border:none;margin:0;}}"
        f"QScrollBar::handle:horizontal{{background:{BORDER};border-radius:3px;min-width:30px;}}"
        f"QScrollBar::add-line:horizontal,QScrollBar::sub-line:horizontal{{width:0px;}}"
        f"QToolTip{{background:{SURFACE2};color:{TEXT};border:1px solid {BORDER};"
        f"padding:4px;border-radius:4px;}}"
    )

    win = _LauncherWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
