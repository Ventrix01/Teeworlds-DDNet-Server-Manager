; Inno Setup script - turns ddnet-manager.exe into a normal Setup.exe wizard.
[Setup]
AppName=DDNet Server Manager
AppVersion=1.1
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

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "dist\ddnet-manager.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\DDNet Server Manager"; Filename: "{app}\ddnet-manager.exe"
Name: "{autodesktop}\DDNet Server Manager"; Filename: "{app}\ddnet-manager.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\ddnet-manager.exe"; Description: "Start DDNet Server Manager"; Flags: nowait postinstall skipifsilent
