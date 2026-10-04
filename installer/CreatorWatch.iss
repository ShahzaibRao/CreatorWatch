; CreatorWatch installer (Inno Setup 6)
; Build: install Inno Setup -> open this file -> Compile
; Needs: ..\dist\CreatorWatch.exe (pyinstaller build)

#ifndef AppVersion
#define AppVersion "0.4.1"
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
DisableDirPage=no
SetupIconFile=..\assets\icon.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\dist\CreatorWatch\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{group}\CreatorWatch"; Filename: "{app}\CreatorWatch.exe"
Name: "{group}\Uninstall CreatorWatch"; Filename: "{uninstallexe}"
Name: "{autodesktop}\CreatorWatch"; Filename: "{app}\CreatorWatch.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Desktop shortcut"; GroupDescription: "Extra:"

[Run]
Filename: "{app}\CreatorWatch.exe"; Description: "Launch CreatorWatch now"; Flags: nowait postinstall skipifsilent runasoriginaluser

[UninstallDelete]
; Runtime me bani hui cheezen (download engines waghera) — hamesha saaf karo
Type: filesandordirs; Name: "{app}\tools"

[Code]
var
  DeleteUserData: Boolean;

function InitializeUninstall(): Boolean;
begin
  Result := True;
  DeleteUserData := False;
  if MsgBox('Kya USER DATA bhi delete karein?' + #13#10 + #13#10 +
            'Is me shamil hai:' + #13#10 +
            '- Download history aur prospect list' + #13#10 +
            '- Cookies (login)' + #13#10 +
            '- App settings' + #13#10 + #13#10 +
            'Downloads folder (Downloads/CreatorWatch) MEHFOOZ rahega.',
            mbConfirmation, MB_YESNO) = IDYES then
    DeleteUserData := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  // %APPDATA%\CreatorWatch (data.db, cookies.txt, settings) — sirf agar user ne YES kaha
  if (CurUninstallStep = usPostUninstall) and DeleteUserData then
  begin
    DelTree(ExpandConstant('{userappdata}\CreatorWatch'), True, True, True);
  end;
end;
