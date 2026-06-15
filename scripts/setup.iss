; ═══════════════════════════════════════════════════
; 教师助手 — Inno Setup 安装脚本
; 编译: ISCC.exe scripts\setup.iss
; ═══════════════════════════════════════════════════

#define AppName       "教师助手"
#define AppVersion    "0.2.0"
#define AppPublisher  "teacherAssist"
#define AppURL        "http://localhost:8000"
#define OutputDir     "..\dist"
#define SourceDir     "..\build\installer"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\TeacherAssist
DefaultGroupName={#AppName}
OutputDir={#OutputDir}
OutputBaseFilename=teacherAssist-setup-{#AppVersion}
SetupIconFile=..\static\favicon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
; 安装包界面语言
ShowLanguageDialog=no
; 允许用户选择安装路径
DisableDirPage=no
; 要求管理员权限（安装到 Program Files 需要）
PrivilegesRequired=admin
; 安装程序自身也以管理员运行
PrivilegesRequiredOverridesAllowed=commandline
; 64位
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; 最小 Windows 版本
MinVersion=10.0

[Languages]
Name: "chinese"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式:"; Flags: checkedonce
Name: "startmenu";   Description: "创建开始菜单文件夹"; GroupDescription: "快捷方式:"
Name: "autostart";   Description: "开机自动启动教师助手"; GroupDescription: "其他:"

[Files]
; 整个构建目录复制到安装路径
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; VC++ 运行时（PyTorch 依赖，Win10+ 通常已自带）
; 如果目标机器缺这个，PyTorch 会加载失败
; Source: "vcredist\VC_redist.x64.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall

[Icons]
; 桌面快捷方式
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\python\python.exe"; \
  Parameters: """{app}\scripts\run_server.py"""; \
  WorkingDir: "{app}"; IconFilename: "{app}\static\favicon.ico"; \
  Tasks: desktopicon; Comment: "启动教师助手"
; 开始菜单
Name: "{autoprograms}\{#AppName}\{#AppName}"; Filename: "{app}\python\python.exe"; \
  Parameters: """{app}\scripts\run_server.py"""; \
  WorkingDir: "{app}"; IconFilename: "{app}\static\favicon.ico"; \
  Tasks: startmenu; Comment: "启动教师助手"
; 开始菜单 - 配置
Name: "{autoprograms}\{#AppName}\配置文件"; Filename: "notepad.exe"; \
  Parameters: """{app}\.env"""; Tasks: startmenu
; 开始菜单 - 数据目录
Name: "{autoprograms}\{#AppName}\数据目录"; Filename: "explorer.exe"; \
  Parameters: """{app}\data"""; Tasks: startmenu
; 开始菜单 - 卸载
Name: "{autoprograms}\{#AppName}\卸载教师助手"; Filename: "{uninstallexe}"; Tasks: startmenu

[Run]
; 安装完成后自动启动
Filename: "{app}\python\python.exe"; Parameters: """{app}\scripts\run_server.py"""; \
  Description: "启动教师助手"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\__pycache__"
Type: filesandordirs; Name: "{app}\app\__pycache__"

[Code]
// 自定义卸载时询问是否保留数据
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    if DirExists(ExpandConstant('{app}\data')) then
    begin
      if MsgBox('是否保留课堂数据和配置？' + #13#10#13#10 +
                '选"是"保留数据（下次安装可恢复）' + #13#10 +
                '选"否"彻底删除所有数据',
                mbConfirmation, MB_YESNO) = IDNO then
      begin
        DelTree(ExpandConstant('{app}\data'), True, True, True);
        DelTree(ExpandConstant('{app}\models'), True, True, True);
        DeleteFile(ExpandConstant('{app}\.env'));
      end;
    end;
  end;
end;
