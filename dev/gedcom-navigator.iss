; cspell: disable
#define MyAppName "GEDCOM Navigator"
#define MyAppVersion "1.9.7"
#define MyAppPublisher "Adam Kessel"
#define MyAppURL "https://github.com/ajkessel/gedcom-navigator"
#define MyAppExeName "gedcom-navigator.exe"
#define MyAppCliName "gedcom_navigator_cli.exe"

[Setup]
AppId={{D3F7B0B6-A2E4-4D6F-9C4B-6A5D5F5E5D5C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
;AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes
LicenseFile=..\dist\LICENSE.txt
PrivilegesRequired=lowest
OutputBaseFilename=gedcom-navigator-setup
SetupIconFile=..\icons\gedcom_navigator.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern
VersionInfoVersion={#MyAppVersion}.0
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\{#MyAppCliName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\docs\*"; DestDir: "{app}\docs"; Flags: ignoreversion recursesubdirs createallsubdirs

[Registry]
; Register the app as the .ged handler (per-user; matches PrivilegesRequired=lowest).
; ProgID must match PROGID in src/gedcom_file_association.py.
Root: HKCU; Subkey: "Software\Classes\.ged"; ValueType: string; ValueName: ""; ValueData: "ajkessel.gedcom-navigator.ged"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\.ged\OpenWithProgids"; ValueType: none; ValueName: "ajkessel.gedcom-navigator.ged"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\ajkessel.gedcom-navigator.ged"; ValueType: string; ValueName: ""; ValueData: "GEDCOM File"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\ajkessel.gedcom-navigator.ged\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"
Root: HKCU; Subkey: "Software\Classes\ajkessel.gedcom-navigator.ged\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall
