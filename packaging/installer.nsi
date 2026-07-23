Unicode True
!include "MUI2.nsh"

; ---- 基本信息 ----
Name "半自动找工作工具"
OutFile "..\dist\job_hunter-setup.exe"
InstallDir "$LOCALAPPDATA\jobhunter"
RequestExecutionLevel user

!define MUI_ABORTWARNING
!define MUI_ICON "${NSISDIR}\Contrib\Graphics\Icons\modern-install.ico"
!define MUI_UNICON "${NSISDIR}\Contrib\Graphics\Icons\modern-uninstall.ico"

; ---- 页面 ----
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_WELCOME
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH

!insertmacro MUI_LANGUAGE "SimpChinese"

; ---- 安装段 ----
Section "Install"
  SetOutPath "$INSTDIR"
  ; PyInstaller 输出在仓库根的 dist\job_hunter\（one-folder 模式）
  ; 本 .nsi 位于 packaging/ 子目录，需 ..\ 回到仓库根再引用 dist
  File /r "..\dist\job_hunter"

  ; 开始菜单
  CreateDirectory "$SMPROGRAMS\半自动找工作工具"
  CreateShortCut "$SMPROGRAMS\半自动找工作工具\半自动找工作工具.lnk" "$INSTDIR\job_hunter.exe"
  CreateShortCut "$SMPROGRAMS\半自动找工作工具\卸载.lnk" "$INSTDIR\uninstall.exe"

  ; 桌面快捷方式
  CreateShortCut "$DESKTOP\半自动找工作工具.lnk" "$INSTDIR\job_hunter.exe"

  ; 卸载信息
  WriteUninstaller "$INSTDIR\uninstall.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\jobhunter" "DisplayName" "半自动找工作工具"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\jobhunter" "UninstallString" "$INSTDIR\uninstall.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\jobhunter" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\jobhunter" "DisplayIcon" "$INSTDIR\job_hunter.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\jobhunter" "Publisher" "job_hunter"
SectionEnd

; ---- 卸载段 ----
Section "Uninstall"
  Delete "$SMPROGRAMS\半自动找工作工具\半自动找工作工具.lnk"
  Delete "$SMPROGRAMS\半自动找工作工具\卸载.lnk"
  RMDir "$SMPROGRAMS\半自动找工作工具"
  Delete "$DESKTOP\半自动找工作工具.lnk"
  ; 注意：默认会把安装目录（含用户数据 data\）一并删除。
  ; 若想保留简历/投递记录，卸载前请先备份 $LOCALAPPDATA\jobhunter\data
  RMDir /r "$INSTDIR"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\jobhunter"
SectionEnd
