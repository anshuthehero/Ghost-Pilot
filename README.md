# 👻 Ghost Copilot — Real-Time AI Interview Assistant (macOS & Windows)

Ghost Copilot is an ultra-low latency, multi-platform AI assistant designed to listen to live conversations, automatically transcribe dialogue via Groq Whisper, and generate context-aware, streaming interview answers. It features stealth screen-capture protection to remain completely invisible during screen sharing on Zoom, Google Meet, Microsoft Teams, and Slack.

---

## 🌟 Key Features

- **🖥️ True Multi-Platform (macOS & Windows)**:
  - **macOS**: Native `NSWindowSharingNone` screen-invisibility, BlackHole virtual audio loopback, and `.app` bundle builder (`packaging/macos/build_app.sh`).
  - **Windows**: `WDA_EXCLUDEFROMCAPTURE` stealth client (`windows_client.py`), 1-click batch scripts (`start_windows.bat`, `install_windows.bat`), PyInstaller specs, and Inno Setup installer generator.
- **🎙️ Dual Audio Modes**:
  - **Auto-Listen (VAD)**: Automatically detects when the interviewer speaks and generates answers.
  - **Push-to-Talk (PTT)**: Manually trigger capture using keyboard shortcuts (`F5` / `Spacebar`).
  - **Browser Mic**: Listen directly from any browser/phone microphone with 1 click.
- **⚡ Ultra-Fast Groq Inference**: Sub-second speech transcription (`whisper-large-v3`) paired with high-speed LLM generation (`llama-3.3-70b-versatile`).
- **🔑 In-UI Groq API Key Setup**: Paste and save your Groq API key directly in the HUD interface without manually touching `.env` files.
- **🧠 Conversational Memory & Role Customization**: Full context retention with customizable system personas and interview role guidelines (`⚙️ Role` modal).
- **📋 Clipboard Watcher**: Copy any coding challenge or behavioral question for instant solutions.
- **🛡️ 100% Screen-Share Invisible**: Hidden at the OS window manager level from all screen-sharing APIs.

---

## 📋 Quick Start Setup Checklist

Follow this interactive checklist to get your Ghost Copilot instance up and running:

- [ ] **Step 1: Obtain a Free Groq API Key**
  1. Visit the [Groq Cloud Console](https://console.groq.com/keys).
  2. Sign in or create a free account.
  3. Click **Create API Key**.
  4. Copy your API key (starts with `gsk_`). Keep it secret!

- [ ] **Step 2: Clone the Repository**
  ```bash
  git clone https://github.com/<YOUR_USERNAME>/<YOUR_REPOSITORY_NAME>.git
  cd <YOUR_REPOSITORY_NAME>
  ```

- [ ] **Step 3: Install Dependencies**
  Ensure you have **Python 3.10+** installed:
  ```bash
  pip install -r requirements.txt
  ```

- [ ] **Step 4: Launch Ghost Copilot**
  - **On macOS / Linux**:
    ```bash
    python3 app.py
    ```
  - **On Windows**:
    Double-click `start_windows.bat` or run:
    ```bash
    python app.py
    ```

- [ ] **Step 5: Paste Your Groq API Key (Right in the UI!)**
  - Open `http://localhost:9471` in your browser.
  - Ghost Copilot will display an alert banner: **"⚡ Groq API Key Required: Click here to paste your key"**.
  - Click the banner or the **🔑 API Key** button in the header.
  - Paste your `gsk_...` key and click **Save Key**. The assistant is immediately ready!
  *(Alternatively, you can copy `.env.example` to `.env` and set `GROQ_API_KEY=gsk_...` before launching).*

- [ ] **Step 6: Open the Stealth Client**
  - **On Windows**: Run `python windows_client.py` for a floating window invisible to Zoom/Meet screen share.
  - **On macOS**: Use the browser HUD or build the native bundle using `packaging/macos/build_app.sh`.
  - **On Mobile/Tablet**: Open `http://<SERVER_IP>:9471` on your phone or iPad.

---

## 📁 Repository Structure

```
├── app.py                     # Main backend server + Groq Whisper + LLM streaming + Web HUD
├── windows_client.py          # Windows PyQt6 stealth client (WDA_EXCLUDEFROMCAPTURE)
├── start_windows.bat          # 1-Click launcher for Windows
├── install_windows.bat        # 1-Click installer for Windows dependencies
├── build_standalone_exe.bat   # Builds standalone Windows executable
├── requirements.txt           # Core Python dependencies
├── requirements-desktop.txt   # Desktop GUI dependencies (PyQt6, etc.)
├── copilot.service            # Systemd service definition for Linux servers
├── setup_server.sh            # 1-Click setup script for remote Ubuntu/Debian servers
├── ghost_copilot.icns         # High-resolution application icon
├── .env.example               # Environment template with setup guidance
├── .gitignore                 # Git ignore rules protecting keys, databases & audio
├── client/                    # Client engine & platform-specific drivers
│   ├── platform/macos/        # macOS CoreAudio loopback capture
│   └── platform/windows/      # Windows WASAPI loopback & stealth client
├── desktop/                   # Desktop audio capture & clipboard watchers
├── packaging/                 # Packaging & release scripts
│   ├── macos/                 # macOS .app build, notarization, & bundling scripts
│   └── windows/               # PyInstaller specs & Inno Setup installer script
├── server/                    # Modular server architecture (AI, Auth, Database, Sessions)
├── shared/                    # Shared data schemas and request models
└── tests/                     # Automated test suite (security, audio, auth, etc.)
```

---

## 🍏 macOS Guide

1. **Audio Loopback (Interviewer Audio)**:
   - Install a virtual audio device such as [BlackHole 2ch](https://existential.audio/blackhole/):
     ```bash
     brew install blackhole-2ch
     ```
   - In macOS **Audio MIDI Setup**, create a **Multi-Output Device** including your headphones and BlackHole 2ch.
   - Set Zoom/Meet speaker output to BlackHole 2ch, or set system output to your Multi-Output Device.
2. **Build Native macOS App Bundle**:
   ```bash
   cd packaging/macos
   ./build_app.sh
   ```

---

## 🪟 Windows Guide

1. **Quick Start**:
   - Double-click `install_windows.bat` to install dependencies.
   - Double-click `start_windows.bat` to launch the assistant.
2. **Run Stealth Floating HUD**:
   ```bash
   python windows_client.py
   ```
   > **Note**: Uses `WDA_EXCLUDEFROMCAPTURE` so the window remains visible to you, but completely invisible on screen shares (Zoom, Teams, Google Meet).
3. **Build Standalone Windows Installer**:
   - Double-click `build_standalone_exe.bat` to create a standalone `.exe` using PyInstaller and Inno Setup.

---

## 🧪 Running Tests

Verify security boundaries, audio abstraction, and API contracts:

```bash
pytest
```

---

## 🔒 Security & Privacy Practices

- **Zero-Secret Exposure**: Your `.env` and API keys are strictly excluded by `.gitignore`.
- **In-UI Key Protection**: Keys saved via the UI are stored locally in `.env` and are never exposed in logs or commits.
- **Audio Privacy**: Temporary audio buffers are processed in-memory or in temporary storage and cleaned up automatically.
- **Secret Redaction**: Built-in pattern matching automatically scrubs tokens, passwords, and private keys from prompts before sending to Groq.

---

## 📄 License

This project is released for educational and personal productivity purposes. Please use responsibly and adhere to the terms and guidelines of your interview and meeting platforms.
