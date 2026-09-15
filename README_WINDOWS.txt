==============================================================================
   INTERVIEW ASSISTANT - WINDOWS SETUP & TRANSFER GUIDE (v3.0.0)
==============================================================================

Follow these quick steps to run Interview Assistant on your Windows machine:

------------------------------------------------------------------------------
STEP 1: TRANSFER & EXTRACT
------------------------------------------------------------------------------
1. Copy "Interview_Assistant_Windows_Package.zip" to your Windows PC 
   (via USB drive, Google Drive, OneDrive, Dropbox, or local network share).
2. Right-click "Interview_Assistant_Windows_Package.zip" -> "Extract All...".
   Choose any destination folder (e.g. C:\InterviewAssistant or Desktop).

------------------------------------------------------------------------------
STEP 2: ZERO-INSTALLATION PRE-BUNDLED RUNTIME (NO INSTALLER NEEDED!)
------------------------------------------------------------------------------
Good news: A lightweight Python engine is ALREADY PRE-BUNDLED in the "runtime" folder!
You do NOT need to install Python onto your PC, and no admin rights are required.
It works out-of-the-box on:
  * Windows 11 (64-bit)
  * Windows 10 (64-bit)
  * Windows 8 & 8.1 (64-bit)
  * Windows 7 SP1 (see Windows 7 guide below)

* CONFIGURING YOUR GROQ API KEY:
1. Open ".env" in Notepad (or copy .env.example to .env).
2. Add your Groq API key:
   GROQ_API_KEY=gsk_your_groq_key_here
3. Save (Ctrl+S) and close Notepad.

------------------------------------------------------------------------------
STEP 3: LAUNCH INTERVIEW ASSISTANT
------------------------------------------------------------------------------
Choose either launch method:

>>> METHOD 1: SILENT 1-CLICK LAUNCH (RECOMMENDED) <<<
Double-click "InterviewAssistant.vbs".
  * Starts the local engine silently in the background with ZERO flashing black CMD windows.
  * Opens your default web browser directly to http://127.0.0.1:9471/
  * Done! Interview Assistant HUD opens immediately with ZERO password or token prompt!

>>> METHOD 2: CONSOLE LAUNCH (WITH TERMINAL LOGS) <<<
Double-click "start_windows.bat".
  * Starts the background engine and opens the HUD with diagnostic console logs.

------------------------------------------------------------------------------
SPECIAL INSTRUCTIONS FOR WINDOWS 7 USERS:
------------------------------------------------------------------------------
Why does stock Windows 7 sometimes block modern runtimes?
1. Missing Universal C Runtime:
   Unlike Windows 10/11, stock Windows 7 does not have modern UCRT DLLs
   (api-ms-win-crt-runtime-l1-1-0.dll) in System32.
2. Missing Dynamic Directory Patch:
   Python 3.8 calls SetDefaultDllDirectories in KERNEL32.dll, which requires
   Windows 7 Update KB2533623.
3. 32-bit Architecture:
   If your Windows 7 is 32-bit, the bundled 64-bit binary cannot execute.

HOW TO FIX ON WINDOWS 7 (1 MINUTE):
- Simply double-click "fix_windows7.bat" in this folder!
  It detects your architecture (32-bit vs 64-bit) and installs the official
  Microsoft Visual C++ Redistributable or downloads the 32-bit runtime.
- If prompted for KB2533623, download the official Microsoft update:
  https://www.catalog.update.microsoft.com/Search.aspx?q=KB2533623

------------------------------------------------------------------------------
CONTROLS & SHORTCUTS:
------------------------------------------------------------------------------
- Instant Access:
  * The HUD opens immediately in your browser. No token or password required!
- Auto-Listen vs Push-to-Talk (PTT):
  * Toggle modes anytime via the HUD button or press F5 / Spacebar.
- Copy any text (Ctrl+C):
  * Instant auto-solve: Interview Assistant detects copied coding questions or problems
    and provides instant guidance (with automated secret/token scrubbing).
- Stop Service:
  * Double-click "stop_windows.bat" anytime to cleanly terminate all background processes.

------------------------------------------------------------------------------
WINDOWS NATIVE FEATURES:
------------------------------------------------------------------------------
- Screen-Share Invisibility (WDA_EXCLUDEFROMCAPTURE):
  The HUD window is excluded from Windows compositor capture. It remains
  completely invisible on Zoom, Microsoft Teams, Google Meet, Discord, and OBS!
- Native WASAPI System Audio Loopback:
  Directly captures interviewer audio from speakers/headphones with NO virtual
  audio cable (BlackHole) needed.
- Top-Level Security Hardening:
  * Constant-time timing-attack resistant authentication (hmac.compare_digest)
  * DNS rebinding defense rejecting foreign Host headers
  * Sandboxed WebEngine preventing unauthorized external navigation
  * Modern secret scrubber filtering AWS, GitHub, OpenAI, and Anthropic keys
==============================================================================
