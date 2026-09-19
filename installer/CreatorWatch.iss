; CreatorWatch installer (Inno Setup 6)
; Build: install Inno Setup -> open this file -> Compile
; Needs: ..\dist\CreatorWatch.exe (pyinstaller build)

#ifndef AppVersion
#define AppVersion "0.2.0"
#endif

[Setup]
AppName=CreatorWatch
AppVersion={#AppVersion}
AppPublisher=ShahzaibRao
DefaultDirName={autopf}\CreatorWatch
DefaultGroupName=CreatorWatch
OutputDir=.\
OutputBaseFilename=CreatorWatch-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
PrivilegesRequired=lowest
WizardStyle=modern
DisableProgramGroupPage=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\dist\CreatorWatch.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{group}\CreatorWatch"; Filename: "{app}\CreatorWatch.exe"
Name: "{group}\Uninstall CreatorWatch"; Filename: "{uninstallexe}"
Name: "{autodesktop}\CreatorWatch"; Filename: "{app}\CreatorWatch.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Desktop shortcut"; GroupDescription: "Extra:"

[Run]
Filename: "{app}\CreatorWatch.exe"; Description: "Launch CreatorWatch now"; Flags: nowait postinstall skipifsilent runasoriginaluser
