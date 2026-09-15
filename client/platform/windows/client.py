"""
Ghost Copilot Windows Client.
• Windows capture-exclusion mechanism implemented (WDA_EXCLUDEFROMCAPTURE);
  effectiveness depends on Windows version and capture technology.
• Floating Borderless Always-On-Top Window
• Communicates with Local or Remote Server via ClientConfig
• Hotkey support for candidate voice
"""

import sys
import os

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import ctypes
from typing import Dict, Any, Optional
from client.core.config import ClientConfig
from client.diagnostics.preflight import PreflightChecker

# Win32 Constants for Invisibility to Screen Share
WDA_NONE = 0x00000000
WDA_EXCLUDEFROMCAPTURE = 0x00000011  # Hidden from Zoom, Meet, Teams, OBS


def is_pyqt_available() -> bool:
    try:
        import PyQt6
        from PyQt6 import QtWebEngineWidgets
        return True
    except ImportError:
        pass
    try:
        import PyQt5
        from PyQt5 import QtWebEngineWidgets
        return True
    except ImportError:
        pass
    return False


def apply_windows_display_affinity(hwnd: int, enable: bool = True) -> Dict[str, Any]:
    """
    Applies window display affinity via user32.dll SetWindowDisplayAffinity.
    
    Technical Scope:
    - Windows 10 Build 19041+ and Windows 11: WDA_EXCLUDEFROMCAPTURE (0x11)
      Completely invisible from Zoom, Teams, Meet, OBS, Discord.
    - Windows 7 / 8 / older Win 10: WDA_MONITOR (0x01)
      Blocks window content from screen capture.
    """
    if not sys.platform.startswith("win"):
        return {"success": False, "status": "NON_WINDOWS_EMULATION", "mode": "MOCK"}

    try:
        try:
            from ctypes import wintypes
            ctypes.windll.user32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
            ctypes.windll.user32.SetWindowDisplayAffinity.restype = wintypes.BOOL
        except Exception:
            pass

        if enable:
            # 1. Try Windows 10/11 WDA_EXCLUDEFROMCAPTURE
            res = ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
            if res != 0:
                return {"success": True, "status": "ACTIVE", "mode": WDA_EXCLUDEFROMCAPTURE}

            # 2. Fallback for Windows 7 / 8: WDA_MONITOR (0x01)
            res = ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x00000001)
            if res != 0:
                return {"success": True, "status": "ACTIVE_LEGACY", "mode": 1}

            err = ctypes.GetLastError()
            return {
                "success": False,
                "status": "UNSUPPORTED",
                "error_code": err,
                "hint": "SetWindowDisplayAffinity not supported by this display driver."
            }
        else:
            ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, WDA_NONE)
            return {"success": True, "status": "DISABLED", "mode": WDA_NONE}
    except Exception as e:
        return {"success": False, "status": "ERROR", "error": str(e)}


def run_windows_client():
    # Enable High-DPI Scaling for multi-monitor Windows setups
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

    config = ClientConfig()
    checker = PreflightChecker(config)
    report = checker.run_full_audit()
    print(f"[Interview Assistant Windows] Preflight status: {report['overall_status']}")
    print(f"[Interview Assistant Windows] Connecting to backend: {config.backend_url}")

    has_qt6 = False
    try:
        from PyQt6.QtCore import QUrl, Qt, QByteArray, QTimer
        from PyQt6.QtWidgets import QApplication, QMainWindow, QSystemTrayIcon, QMenu
        from PyQt6.QtGui import QAction
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        try:
            from PyQt6.QtWebEngineCore import QWebEngineHttpRequest, QWebEnginePage, QWebEngineSettings
        except ImportError:
            try:
                from PyQt6.QtNetwork import QWebEngineHttpRequest
                QWebEnginePage = None
                QWebEngineSettings = None
            except ImportError:
                QWebEngineHttpRequest = None
                QWebEnginePage = None
                QWebEngineSettings = None
        has_qt6 = True
    except ImportError:
        try:
            from PyQt5.QtCore import QUrl, Qt, QByteArray, QTimer
            from PyQt5.QtWidgets import QApplication, QMainWindow, QSystemTrayIcon, QMenu, QAction
            from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage, QWebEngineSettings
            try:
                from PyQt5.QtNetwork import QWebEngineHttpRequest
            except ImportError:
                QWebEngineHttpRequest = None
            has_qt6 = False
        except ImportError:
            import webbrowser
            if config.auth_token:
                try:
                    from desktop.clipboard.watcher import DesktopClipboard
                    # Attempt copying token to clipboard for effortless browser pasting
                    if sys.platform.startswith("win"):
                        import subprocess
                        ps_set = f"Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Clipboard]::SetText('{config.auth_token}')"
                        subprocess.run(["powershell", "-NoProfile", "-Command", ps_set], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2, creationflags=0x08000000)
                except Exception:
                    pass
            print(f"[Interview Assistant Windows] Launching HUD in your default web browser: {config.backend_url}")
            print(f"[Interview Assistant Windows] Interview Assistant is running live in your web browser.")
            print(f"[Interview Assistant Windows] Press Ctrl+C in this window (or run stop_windows.bat) to stop.")
            webbrowser.open(config.backend_url)
            try:
                import time
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\n[Interview Assistant Windows] Stopping browser HUD...")
                return

    class WindowsStealthWindow(QMainWindow):
        def __init__(self, backend_url: str, auth_token: str = ""):
            super().__init__()
            self.backend_url = backend_url
            self.auth_token = auth_token
            self.is_ghost = True

            frameless = getattr(Qt, 'WindowType', Qt).FramelessWindowHint
            stays_on_top = getattr(Qt, 'WindowType', Qt).WindowStaysOnTopHint
            tool_flag = getattr(Qt, 'WindowType', Qt).Tool
            translucent = getattr(Qt, 'WidgetAttribute', Qt).WA_TranslucentBackground

            self.setWindowFlags(frameless | stays_on_top | tool_flag)
            self.setAttribute(translucent, True)
            self.resize(460, 800)

            # Position on primary screen right edge (safe against None primaryScreen)
            screen = QApplication.primaryScreen()
            if screen:
                geom = screen.availableGeometry()
                self.move(geom.x() + geom.width() - 480, geom.y() + 40)
            else:
                self.move(100, 40)

            self.browser = QWebEngineView(self)

            # Strict Sandbox: Enforce localhost-only navigation boundary
            if QWebEnginePage is not None:
                class SecureWebPage(QWebEnginePage):
                    def acceptNavigationRequest(self, url: QUrl, nav_type, isMainFrame: bool) -> bool:
                        host = url.host().lower()
                        scheme = url.scheme().lower()
                        if scheme in ("about", "data"):
                            return True
                        if host in ("127.0.0.1", "localhost") and (url.port() in (9471, -1)):
                            return True
                        print(f"[🛡️ Security Alert] Blocked Windows browser navigation to external URL: {url.toString()}")
                        return False

                self.browser.setPage(SecureWebPage(self.browser))

            # Harden browser security settings
            if QWebEngineSettings is not None:
                try:
                    s = self.browser.settings()
                    plugins_attr = getattr(getattr(QWebEngineSettings, 'WebAttribute', QWebEngineSettings), 'PluginsEnabled', None)
                    js_window_attr = getattr(getattr(QWebEngineSettings, 'WebAttribute', QWebEngineSettings), 'JavascriptCanOpenWindows', None)
                    local_remote_attr = getattr(getattr(QWebEngineSettings, 'WebAttribute', QWebEngineSettings), 'LocalContentCanAccessRemoteUrls', None)
                    if plugins_attr is not None: s.setAttribute(plugins_attr, False)
                    if js_window_attr is not None: s.setAttribute(js_window_attr, False)
                    if local_remote_attr is not None: s.setAttribute(local_remote_attr, False)
                except Exception:
                    pass

            # Header-based bootstrap: Bearer token is passed via Authorization header.
            # Also register cookie in WebEngine profile cookie store as defense-in-depth.
            # No token is ever attached to the URL query string.
            if self.auth_token:
                try:
                    if has_qt6:
                        from PyQt6.QtNetwork import QNetworkCookie
                    else:
                        from PyQt5.QtNetwork import QNetworkCookie
                    cookie = QNetworkCookie(b"ghost_session", self.auth_token.encode())
                    cookie.setDomain("127.0.0.1")
                    cookie.setPath("/")
                    cookie.setHttpOnly(True)
                    self.browser.page().profile().cookieStore().setCookie(cookie, QUrl(self.backend_url))
                except Exception:
                    pass

            if QWebEngineHttpRequest is not None and self.auth_token:
                request = QWebEngineHttpRequest(QUrl(self.backend_url))
                request.setHeader(
                    QByteArray(b"Authorization"),
                    QByteArray(f"Bearer {self.auth_token}".encode())
                )
                self.browser.load(request)
            else:
                self.browser.setUrl(QUrl(self.backend_url))

            self.setCentralWidget(self.browser)
            self.apply_invisibility(True)

            # Create System Tray Icon for window restore and control
            self.setup_tray_icon()

            # Poll /sharing_mode every 1 second to sync display affinity with HUD toggle
            self.sync_timer = QTimer(self)
            self.sync_timer.timeout.connect(self.poll_sharing_mode)
            self.sync_timer.start(1000)

        def setup_tray_icon(self):
            try:
                self.tray_icon = QSystemTrayIcon(self)
                style = QApplication.style()
                standard_icon = getattr(getattr(style, 'StandardPixmap', None) or style, 'SP_ComputerIcon', None)
                if standard_icon is not None:
                    self.tray_icon.setIcon(style.standardIcon(standard_icon))
                self.tray_icon.setToolTip("Interview Assistant")

                tray_menu = QMenu()
                toggle_action = QAction("Show / Hide HUD", self)
                toggle_action.triggered.connect(self.toggle_visibility)
                tray_menu.addAction(toggle_action)

                stealth_action = QAction("Toggle Stealth Invisibility", self)
                stealth_action.triggered.connect(lambda: self.apply_invisibility(not self.is_ghost))
                tray_menu.addAction(stealth_action)

                tray_menu.addSeparator()
                quit_action = QAction("Exit Interview Assistant", self)
                quit_action.triggered.connect(QApplication.instance().quit)
                tray_menu.addAction(quit_action)

                self.tray_icon.setContextMenu(tray_menu)
                self.tray_icon.activated.connect(self.on_tray_activated)
                self.tray_icon.show()
            except Exception as e:
                print(f"[Tray Warning] System tray icon could not be initialized: {e}")

        def on_tray_activated(self, reason):
            # Trigger = 3 (left click)
            trigger_val = getattr(getattr(QSystemTrayIcon, 'ActivationReason', None) or QSystemTrayIcon, 'Trigger', 3)
            if reason == trigger_val or reason == 3:
                self.toggle_visibility()

        def toggle_visibility(self):
            if self.isVisible():
                self.hide()
            else:
                self.showNormal()
                self.activateWindow()

        def poll_sharing_mode(self):
            try:
                import urllib.request
                import json
                req = urllib.request.Request(f"{self.backend_url}/sharing_mode")
                if self.auth_token:
                    req.add_header("Authorization", f"Bearer {self.auth_token}")
                with urllib.request.urlopen(req, timeout=1) as resp:
                    data = json.loads(resp.read().decode())
                    is_visible_mode = (data.get("mode") == "visible")
                    if is_visible_mode and self.is_ghost:
                        self.apply_invisibility(False)
                    elif not is_visible_mode and not self.is_ghost:
                        self.apply_invisibility(True)
            except Exception:
                pass

        def apply_invisibility(self, enable=True):
            self.is_ghost = enable
            hwnd = int(self.winId())
            res = apply_windows_display_affinity(hwnd, enable)
            if res.get("success"):
                print(f"[Stealth] Windows screen-share invisibility: {'ON' if enable else 'OFF'}.")
            else:
                print(f"[Stealth Warning] Display affinity warning: {res}")

        def keyPressEvent(self, event):
            # Esc key hides window safely; can be restored from system tray
            esc_key = getattr(Qt, 'Key', Qt).Key_Escape
            if event.key() == esc_key:
                self.hide()
                return
            super().keyPressEvent(event)

    app = QApplication(sys.argv)
    window = WindowsStealthWindow(config.backend_url, config.auth_token)
    window.show()
    exec_func = getattr(app, "exec", None) or getattr(app, "exec_")
    sys.exit(exec_func())


if __name__ == "__main__":
    run_windows_client()
