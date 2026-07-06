; Inno Setup script for ocrmath
; Build the PyInstaller payload first:  python -m PyInstaller build.spec --clean
; Then compile this script with ISCC.exe:
;   "C:\Users\<user>\AppData\Local\Programs\Inno Setup 6\ISCC.exe" installer.iss

#define AppName        "ocrmath"
#define AppVersion     "1.1.2"
#define AppPublisher   "vvangpc"
#define AppURL         "https://github.com/vvangpc/ocrmath"
#define AppExe         "ocrmath.exe"

[Setup]
AppId={{6D4C3E8E-4B5A-4F2C-9D11-4F0E3A8E1B11}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
LicenseFile=LICENSE
OutputDir=dist\installer
OutputBaseFilename=ocrmath-setup-{#AppVersion}
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Per-user install: no admin needed, lives in %LOCALAPPDATA%\Programs
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763

[Languages]
Name: "english";       MessagesFile: "compiler:Default.isl"
; Translation vendored in-repo (requires Inno Setup 6.5+): the download URL
; it used to be fetched from moved once already and broke the build.
Name: "chinesesimp";   MessagesFile: "installer\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon";   Description: "{cm:CreateDesktopIcon}";   GroupDescription: "{cm:AdditionalIcons}";   Flags: unchecked
Name: "autostart";     Description: "Start {#AppName} automatically when I log in"; GroupDescription: "Auto-start:"; Flags: unchecked

[Files]
Source: "dist\ocrmath\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}";       Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: autostart

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Optional: clean up data on uninstall (commented out — preserve user history by default)
; Type: filesandordirs; Name: "{userappdata}\ocrmath"
