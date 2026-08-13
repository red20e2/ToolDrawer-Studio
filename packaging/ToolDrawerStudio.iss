#define AppName "ToolDrawer Studio"
#define AppExeName "ToolDrawer Studio.exe"
#ifndef AppVersion
  #error AppVersion must be supplied by the build
#endif

[Setup]
AppId=ToolDrawerStudio
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
DefaultDirName={localappdata}\Programs\ToolDrawer Studio
DefaultGroupName=ToolDrawer Studio
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=auto
OutputDir=..\artifacts
OutputBaseFilename=ToolDrawer-Studio-{#AppVersion}-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName={#AppName} {#AppVersion}
UninstallDisplayIcon={app}\{#AppExeName}
CloseApplications=yes
RestartApplications=no

[Files]
Source: "..\dist\ToolDrawer Studio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Icons]
Name: "{group}\ToolDrawer Studio"; Filename: "{app}\{#AppExeName}"
Name: "{userdesktop}\ToolDrawer Studio"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon
