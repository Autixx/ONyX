; ONyX Client — Inno Setup 6 installer script
; Compile with: ISCC.exe installer.iss
; Or use build.ps1 which patches the version automatically.

#define AppName        "ONyX Client"
#define AppVersion     "0.3.0"
#define AppPublisher   "ONyX"
#define ServiceName    "ONyXClientDaemon"
#define AppExeName     "ONyXClient.exe"
#define DaemonExeName  "ONyXClientDaemon.exe"

[Setup]
; Unique GUID — do NOT change after first release (used for upgrades/uninstall registry key)
AppId={{6F4A2B8C-3D1E-4F9A-B027-C5E8F1A23456}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\ONyX
DefaultGroupName={#AppName}
AllowNoIcons=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=assets\icons\onyx.ico
UninstallDisplayIcon={app}\{#AppExeName}
OutputDir=dist-installer
OutputBaseFilename=ONyXClientSetup-{#AppVersion}
; After build, sign with:
;   signtool sign /fd sha256 /tr http://timestamp.digicert.com /td sha256 ^
;     /f cert.pfx /p PASSWORD dist-installer\ONyXClientSetup-{#AppVersion}.exe

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
; ── GUI client (PyInstaller COLLECT output) ──
Source: "dist\ONyXClient\{#AppExeName}";       DestDir: "{app}";           Flags: ignoreversion
Source: "dist\ONyXClient\_internal\*";          DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs
; ── Daemon (PyInstaller onefile output) ──
Source: "dist\{#DaemonExeName}";                DestDir: "{app}";           Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}";              Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}";    Filename: "{uninstallexe}"
Name: "{commondesktop}\{#AppName}";      Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
; Install service (win32serviceutil registers it pointing to {app}\ONyXClientDaemon.exe)
Filename: "{app}\{#DaemonExeName}"; Parameters: "install"; \
  Flags: runhidden waituntilterminated; StatusMsg: "Installing daemon service..."
; Set service to auto-start (win32serviceutil defaults to auto, but be explicit)
Filename: "{sys}\sc.exe"; Parameters: "config {#ServiceName} start= auto"; \
  Flags: runhidden waituntilterminated
; Start the service immediately
Filename: "{sys}\sc.exe"; Parameters: "start {#ServiceName}"; \
  Flags: runhidden waituntilterminated; StatusMsg: "Starting daemon service..."
; Launch the GUI after install (optional, user can uncheck)
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName} now"; \
  Flags: nowait postinstall skipifsilent

[UninstallRun]
; Stop the daemon service first
Filename: "{sys}\sc.exe"; Parameters: "stop {#ServiceName}"; \
  Flags: runhidden waituntilterminated; RunOnceId: "StopSvc"
; Brief pause to let the service wind down
Filename: "{sys}\cmd.exe"; Parameters: "/c timeout /t 3 /nobreak >nul"; \
  Flags: runhidden waituntilterminated; RunOnceId: "WaitStop"
; Remove WireGuard/AWG tunnel services if they are still registered
Filename: "{sys}\cmd.exe"; Parameters: "/c for %s in (onyxawg0 onyxwg0) do wireguard /uninstalltunnelservice %s 2>nul"; \
  Flags: runhidden waituntilterminated; RunOnceId: "RemoveTunnels"
; Unregister the daemon service
Filename: "{app}\{#DaemonExeName}"; Parameters: "remove"; \
  Flags: runhidden waituntilterminated; RunOnceId: "RemoveSvc"

[Code]
{ Ask whether to remove user data (credentials, logs, cached configs) on uninstall. }
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  UserDataPath: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    UserDataPath := ExpandConstant('{%USERPROFILE}') + '\.onyx-client';
    if DirExists(UserDataPath) then
    begin
      if MsgBox(
        'Remove user data and configuration files?' + #13#10 + #13#10 +
        UserDataPath + #13#10 + #13#10 +
        'This includes cached credentials, logs and VPN configurations.' + #13#10 +
        'Select No to keep data for a future reinstall.',
        mbConfirmation, MB_YESNO) = IDYES then
      begin
        DelTree(UserDataPath, True, True, True);
      end;
    end;
  end;
end;
