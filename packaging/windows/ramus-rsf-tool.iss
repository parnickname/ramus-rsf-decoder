; Скрипт Inno Setup для "Редактора Ramus RSF" -- собирает один
; самодостаточный setup.exe (установка в один клик, без прав
; администратора по умолчанию) из результата PyInstaller-сборки.
;
; Сборка (обычно выполняется в CI, см. .github/workflows/release.yml):
;   1. pyinstaller packaging/pyinstaller/ramus-rsf-gui.spec --noconfirm
;      -> результат в dist/RamusRSFEditor/
;   2. iscc packaging/windows/ramus-rsf-tool.iss /DAppVersion=X.Y.Z
;      -> результат в dist/installer/RamusRSFEditor-Setup-X.Y.Z.exe
;
; Локально (Windows, с установленным Inno Setup 6):
;   iscc packaging\windows\ramus-rsf-tool.iss

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

#define AppName "Редактор Ramus RSF"
#define AppExeName "RamusRSFEditor.exe"
#define AppPublisher "ramus-rsf-tool"
#define AppURL "https://github.com/parnickname/ramus-rsf-decoder"
; Постоянный GUID -- не менять между версиями, иначе Windows будет видеть
; каждый релиз как отдельное, а не обновляемое приложение.
#define AppId "{8C6C6C63-6E27-4C0B-9C4E-9C6B8D9C6A11}"

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
; Установка без прав администратора по умолчанию (в профиль пользователя)
; -- ближе всего к "в один клик"; пользователь с правами администратора
; может переключить на общую установку прямо в мастере.
DefaultDirName={autopf}\RamusRSFEditor
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DisableProgramGroupPage=yes
OutputDir=..\..\dist\installer
OutputBaseFilename=RamusRSFEditor-Setup-{#AppVersion}
SetupIconFile=..\icons\ramus-rsf-tool.ico
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#AppName}
LicenseFile=..\..\LICENSE

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "fileassoc"; Description: "Открывать файлы .rsf этим приложением"; GroupDescription: "Ассоциации файлов:"; Flags: checkedonce

[Files]
; Всё дерево PyInstaller-сборки (onedir): сам .exe + библиотеки Qt/Python.
Source: "..\..\dist\RamusRSFEditor\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Registry]
; Ассоциация .rsf -> "Редактор Ramus RSF" (только для текущего
; пользователя -- HKCU, не требует прав администратора).
Root: HKCU; Subkey: "Software\Classes\.rsf"; ValueType: string; ValueName: ""; ValueData: "RamusRSFTool.rsf"; Flags: uninsdeletevalue; Tasks: fileassoc
Root: HKCU; Subkey: "Software\Classes\RamusRSFTool.rsf"; ValueType: string; ValueName: ""; ValueData: "Модель Ramus IDEF0/DFD"; Flags: uninsdeletekey; Tasks: fileassoc
Root: HKCU; Subkey: "Software\Classes\RamusRSFTool.rsf\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExeName},0"; Tasks: fileassoc
Root: HKCU; Subkey: "Software\Classes\RamusRSFTool.rsf\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExeName}"" ""%1"""; Tasks: fileassoc

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
