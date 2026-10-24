; packaging/airmouse.iss - Inno Setup script for AirMouse-Setup-<version>.exe
;
; Build (after PyInstaller made dist\AirMouse):
;   ISCC.exe /DAppVersion=0.2.0 packaging\airmouse.iss
;
; Installs for the current user only (no administrator prompt) into
; %LOCALAPPDATA%\Programs\AirMouse, with a Start-menu shortcut, an optional
; Desktop shortcut and an optional "start with Windows" entry (the same one the
; tray menu toggles). A running AirMouse is asked to quit first, so it can put
; the Windows mouse settings back.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6F1C2B9E-3A4D-4E5B-9C7A-2D8E1F0A4B6C}
AppName=AirMouse
AppVersion={#AppVersion}
AppVerName=AirMouse {#AppVersion}
AppPublisher=AirMouse contributors
AppPublisherURL=https://github.com/eliasneto072/airmouse
AppSupportURL=https://github.com/eliasneto072/airmouse/issues
DefaultDirName={autopf}\AirMouse
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=AirMouse-Setup-{#AppVersion}
SetupIconFile=..\build\airmouse.ico
UninstallDisplayIcon={app}\AirMouse.exe
UninstallDisplayName=AirMouse
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
CloseApplications=yes
RestartApplications=no
ShowLanguageDialog=auto

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
brazilianportuguese.StartWithWindows=Iniciar o AirMouse junto com o Windows
english.StartWithWindows=Start AirMouse when I sign in to Windows
brazilianportuguese.OpenNow=Abrir o AirMouse agora (o guia de primeiros passos abre no navegador)
english.OpenNow=Open AirMouse now (the get-started guide opens in your browser)

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "startup"; Description: "{cm:StartWithWindows}"; Flags: unchecked

[InstallDelete]
; files of the previous version (libraries change between versions)
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\AirMouse\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\AirMouse"; Filename: "{app}\AirMouse.exe"
Name: "{autodesktop}\AirMouse"; Filename: "{app}\AirMouse.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "AirMouse"; ValueData: """{app}\AirMouse.exe"""; Tasks: startup

[Run]
Filename: "{app}\AirMouse.exe"; Description: "{cm:OpenNow}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; log and downloaded models (settings in %APPDATA%\AirMouse are kept for a reinstall)
Type: filesandordirs; Name: "{localappdata}\AirMouse"

[Code]
function OpenEvent(dwDesiredAccess: Cardinal; bInheritHandle: Boolean; lpName: String): THandle;
  external 'OpenEventW@kernel32.dll stdcall';
function SetEvent(hEvent: THandle): Boolean;
  external 'SetEvent@kernel32.dll stdcall';
function OpenMutex(dwDesiredAccess: Cardinal; bInheritHandle: Boolean; lpName: String): THandle;
  external 'OpenMutexW@kernel32.dll stdcall';
function CloseHandle(hObject: THandle): Boolean;
  external 'CloseHandle@kernel32.dll stdcall';

const
  EVENT_MODIFY_STATE = $0002;
  SYNCHRONIZE = $00100000;

{ Ask a running AirMouse to quit (it restores the Windows mouse settings on the
  way out) and wait up to 10 s for it to be gone. }
procedure QuitAirMouse();
var
  Handle: THandle;
  I: Integer;
begin
  Handle := OpenEvent(EVENT_MODIFY_STATE, False, 'Local\AirMouseQuit');
  if Handle = 0 then
    Exit;
  SetEvent(Handle);
  CloseHandle(Handle);
  for I := 1 to 50 do
  begin
    Handle := OpenMutex(SYNCHRONIZE, False, 'Local\AirMouseSingleInstance');
    if Handle = 0 then
      Break;
    CloseHandle(Handle);
    Sleep(200);
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  QuitAirMouse();
  Result := '';
end;

function InitializeUninstall(): Boolean;
begin
  QuitAirMouse();
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  { "Start with Windows" may also have been turned on from the tray menu }
  if CurUninstallStep = usUninstall then
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', 'AirMouse');
end;
