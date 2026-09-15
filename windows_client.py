"""
Ghost Copilot Windows Stealth Client
• Built-in Screen Share Invisibility (WDA_EXCLUDEFROMCAPTURE)
• Floating Borderless Always-On-Top Window
• Connects to Local or Remote Server (FileZilla / Cloud Server)
• Global Spacebar PTT Hotkey support

Requirements on Windows:
  pip install PyQt6 PyQt6-WebEngine keyboard requests
"""

import sys
import ctypes
from PyQt6.QtCore import QUrl, Qt
from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6.QtWebEngineWidgets import QWebEngineView

# Change this if your server is hosted remotely:
SERVER_URL = "http://localhost:9471"

# Win32 Constants for Invisibility to Screen Share
WDA_NONE = 0x00000000
WDA_EXCLUDEFROMCAPTURE = 0x00000011  # Hidden from Zoom, Meet, Teams, OBS

class StealthWindow(QMainWindow):
    def __init__(self, url):
        super().__init__()
        self.url = url
        self.is_ghost = True

        # Window settings: Frameless, Always on Top, Floating Tool
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.SubWindow
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(460, 800)

        # Move to top right corner of screen
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - 480, 40)

        # Web view rendering the HUD
        self.browser = QWebEngineView(self)
        self.browser.setUrl(QUrl(self.url))
        self.setCentralWidget(self.browser)

        # Enable Invisibility by default
        self.apply_invisibility(True)

    def apply_invisibility(self, enable=True):
        self.is_ghost = enable
        hwnd = int(self.winId())
        mode = WDA_EXCLUDEFROMCAPTURE if enable else WDA_NONE
        ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, mode)
        print(f"[Stealth] Screen capture invisibility set to: {enable}")

    def toggle_invisibility(self):
        self.apply_invisibility(not self.is_ghost)

def main():
    app = QApplication(sys.argv)
    window = StealthWindow(SERVER_URL)
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
