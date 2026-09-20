; Inno Setup script - builds DDNet-Server-Manager-Setup.exe.
; Running the finished Setup.exe again on a PC that already has the app offers UNINSTALL / REINSTALL / CANCEL.
[Setup]
AppId={{8A5C3F2E-4B7D-4E91-9C1A-D7E2B6F3A410}
AppName=DDNet Server Manager
AppVersion=1.2
AppPublisher=DDNet Server Manager
DefaultDirName={autopf}\DDNet Server Manager
DefaultGroupName=DDNet Server Manager
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=DDNet-Server-Manager-Setup
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\ddnet-manager.exe
WizardStyle=modern
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "dist\ddnet-manager.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\DDNet Server Manager"; Filename: "{app}\ddnet-manager.exe"
Name: "{autodesktop}\DDNet Server Manager"; Filename: "{app}\ddnet-manager.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\ddnet-manager.exe"; Description: "Start DDNet Server Manager"; Flags: nowait postinstall skipifsilent

[Code]
const
  UninstKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{8A5C3F2E-4B7D-4E91-9C1A-D7E2B6F3A410}_is1';
  RunKey = 'Software\Microsoft\Windows\CurrentVersion\Run';

var
  WipeData: Boolean;

{ ---------- opening the installer again: offer to uninstall ---------- }
function FindUninstaller(var Path: String): Boolean;
begin
  Result := RegQueryStringValue(HKCU, UninstKey, 'UninstallString', Path) or
            RegQueryStringValue(HKLM, UninstKey, 'UninstallString', Path);
  if Result then
  begin
    Path := RemoveQuotes(Path);
    Result := FileExists(Path);
  end;
end;

function InitializeSetup(): Boolean;
var
  Path: String;
  Code: Integer;
begin
  Result := True;
  if (not WizardSilent) and FindUninstaller(Path) then
  begin
    case MsgBox('DDNet Server Manager is already installed on this PC.' + #13#10 + #13#10 +
                'Yes  =  Uninstall it (removes the app and everything it created)' + #13#10 +
                'No   =  Reinstall / update it' + #13#10 +
                'Cancel  =  Do nothing',
                mbConfirmation, MB_YESNOCANCEL) of
      IDYES:
        begin
          Exec(Path, '', '', SW_SHOWNORMAL, ewNoWait, Code);
          Result := False;
        end;
      IDCANCEL:
        Result := False;
    end;
  end;
end;

{ ---------- uninstalling ---------- }
function ManagerRunning(): Boolean;
var
  Code: Integer;
begin
  Result := Exec('cmd.exe', '/c tasklist /FI "IMAGENAME eq ddnet-manager.exe" | find /I "ddnet-manager.exe" >nul',
                 '', SW_HIDE, ewWaitUntilTerminated, Code) and (Code = 0);
end;

function WaitForManagerToClose(): Boolean;
var
  i: Integer;
begin
  for i := 1 to 30 do
  begin
    if not ManagerRunning() then
    begin
      Result := True;
      Exit;
    end;
    Sleep(500);
  end;
  Result := not ManagerRunning();
end;

function InitializeUninstall(): Boolean;
var
  Code: Integer;
begin
  Result := True;
  WipeData := False;

  { ask the app to close politely (it will offer to stop a running server first) }
  if ManagerRunning() then
  begin
    Exec('taskkill.exe', '/IM ddnet-manager.exe', '', SW_HIDE, ewWaitUntilTerminated, Code);
    if not WaitForManagerToClose() then
    begin
      MsgBox('Please close DDNet Server Manager (stop its server if it asks), then click OK.',
             mbInformation, MB_OK);
      if not WaitForManagerToClose() then
      begin
        MsgBox('DDNet Server Manager is still open, so nothing was removed.', mbError, MB_OK);
        Result := False;
        Exit;
      end;
    end;
  end;

  if not UninstallSilent then
    WipeData := (MsgBox('Also delete your backups, saved server profiles and the server config files ' +
                        'this app wrote?' + #13#10 + #13#10 +
                        'Never touched: your game client, server ranks/saves, maps and the server program itself.',
                        mbConfirmation, MB_YESNO or MB_DEFBUTTON1) = IDYES);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Home, Roaming: String;
begin
  if CurUninstallStep <> usPostUninstall then
    Exit;

  Home := ExpandConstant('{%USERPROFILE}');
  Roaming := ExpandConstant('{userappdata}');

  { always removed: things that only exist because of this app }
  RegDeleteValue(HKCU, RunKey, 'DDNetServerManager');               { "open on login" entry }
  RegDeleteKeyIncludingSubkeys(HKCU, 'Software\ddnet-manager');     { its saved settings }
  DeleteFile(Home + '\.config\ddnet-manager-stats.json');           { lifetime stats }
  DeleteFile(ExpandConstant('{%TEMP}') + '\ddnet-manager.lock');    { single-instance lock }

  { removed if you said yes }
  if WipeData then
  begin
    DelTree(Home + '\ddnet-backups', True, True, True);
    DelTree(Home + '\ddnet-manager-profiles', True, True, True);
    DeleteFile(Roaming + '\DDNet\autoexec_server.cfg');
    DeleteFile(Roaming + '\DDNet\autoexec_server.cfg.bak');
    DeleteFile(Roaming + '\Teeworlds\teeworlds_server.cfg');
    DeleteFile(Roaming + '\Teeworlds\teeworlds_server.cfg.bak');
  end;
end;
