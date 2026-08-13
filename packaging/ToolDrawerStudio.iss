#define AppVersion "0.1.0"
[Setup]
AppName=ToolDrawer Studio
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\ToolDrawer Studio
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\artifacts
OutputBaseFilename=ToolDrawer-Studio-{#AppVersion}-Setup

[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; Flags: unchecked

[Icons]
Name: "{group}\ToolDrawer Studio"; Filename: "{app}\ToolDrawer Studio.exe"
Name: "{userdesktop}\ToolDrawer Studio"; Filename: "{app}\ToolDrawer Studio.exe"; Tasks: desktopicon
