Unicode True
!include "MUI2.nsh"

; === Basic Info ===
Name "Job Hunter"
OutFile "..\dist\job_hunter-setup.exe"
InstallDir "$LOCALAPPDATA\jobhunter"
RequestExecutionLevel user

!define MUI_ABORTWARNING
!define MUI_ICON "${NSISDIR}\Contrib\Graphics\Icons\modern-install.ico"
!define MUI_UNICON "${NSISDIR}\Contrib\Graphics\Icons\modern-uninstall.ico"

; === Pages ===
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_WELCOME
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH

!insertmacro MUI_LANGUAGE "English"

; === Install Section ===
Section "Install"
  SetOutPath "$INSTDIR"
  ; PyInstaller outputs to dist/job_hunter/ (one-folder mode)
  ; This .nsi lives in packaging/ subdirectory, so use ..\ to reach repo root
  File /r "..\dist\job_hunter"

  ; Start Menu shortcuts
  CreateDirectory "$SMPROGRAMS\Job Hunter"
  CreateShortCut "$SMPROGRAMS\Job Hunter\Job Hunter.lnk" "$INSTDIR\job_hunter.exe"
  CreateShortCut "$SMPROGRAMS\Job Hunter\Uninstall.lnk" "$INSTDIR\uninstall.exe"

  ; Desktop shortcut
  CreateShortCut "$DESKTOP\Job Hunter.lnk" "$INSTDIR\job_hunter.exe"

  ; Uninstaller registry info
  WriteUninstaller "$INSTDIR\uninstall.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\jobhunter" "DisplayName" "Job Hunter"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\jobhunter" "UninstallString" "$INSTDIR\uninstall.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\jobhunter" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\jobhunter" "DisplayIcon" "$INSTDIR\job_hunter.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\jobhunter" "Publisher" "job_hunter"
SectionEnd

; === Uninstall Section ===
Section "Uninstall"
  Delete "$SMPROGRAMS\Job Hunter\Job Hunter.lnk"
  Delete "$SMPROGRAMS\Job Hunter\Uninstall.lnk"
  RMDir "$SMPROGRAMS\Job Hunter"
  Delete "$DESKTOP\Job Hunter.lnk"
  RMDir /r "$INSTDIR"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\jobhunter"
SectionEnd
