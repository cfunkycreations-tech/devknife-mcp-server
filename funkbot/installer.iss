; Inno Setup script — builds FunkBot-Setup.exe from dist\FunkBot.exe
;
;   1. pyinstaller FunkBot.spec        ->  dist\FunkBot.exe
;   2. iscc installer.iss              ->  installer\FunkBot-Setup.exe
;
; Installs per-user by default (no admin prompt, no UAC), so it lands in
; %LOCALAPPDATA%\Programs\FunkBot. Memory, skills and dictations live under
; %LOCALAPPDATA%\FunkBot\data — outside the install directory, so upgrading or
; uninstalling never eats what FunkBot has learned.

#define AppName    "FunkBot"
#define AppVersion "1.0.0"
#define AppPublish "cfunky creations"
#define AppExe     "FunkBot.exe"

[Setup]
AppId={{B7E4F3A2-9C1D-4E8B-A5F6-3D2C1B0A9E8F}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublish}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=installer
OutputBaseFilename=FunkBot-Setup
SetupIconFile=FunkBot.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
; The bot is offline by design; say so where Windows shows it.
AppComments=Offline agent runtime. Runs against your own local model.

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; \
    GroupDescription: "Shortcuts:"
Name: "startupicon"; Description: "Start FunkBot when I sign in"; \
    GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md";      DestDir: "{app}"; Flags: ignoreversion isreadme
Source: "policy.json";    DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{group}\{#AppName}";          Filename: "{app}\{#AppExe}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}";    Filename: "{app}\{#AppExe}"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}";    Filename: "{app}\{#AppExe}"; \
    Parameters: "--no-browser"; Tasks: startupicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch FunkBot now"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Only the install directory. Data under %LOCALAPPDATA%\FunkBot is left alone
; on purpose — uninstalling the app should not delete what it remembers.
Type: filesandordirs; Name: "{app}\__pycache__"
