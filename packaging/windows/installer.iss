; ==============================================================================
; Inno Setup Script for Ghost Copilot Windows Client
; Packages the PyInstaller output into a standard Windows installer (.exe).
; Features: Desktop shortcut, Start Menu entry, uninstaller, FFmpeg bundling.
; ==============================================================================

#define MyAppName "Ghost Copilot"
#define MyAppVersion "3.0.0"
#define MyAppPublisher "Ghost Copilot Team"
#define MyAppURL "https://ghostcopilot.local"
#define MyAppExeName "GhostCopilot.exe"

[Setup]
AppId={{D14299B2-38B6-4E28-8C6D-55E8D88F21B9}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\..\dist\installer
OutputBaseFilename=GhostCopilot-Setup-v{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\..\dist\GhostCopilot\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Bundled FFmpeg binary if present in packaging assets
Source: "..\..\bin\windows\ffmpeg.exe"; DestDir: "{app}\bin"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
