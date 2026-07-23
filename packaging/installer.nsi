!include "MUI2.nsh"

; ---- Basic info ----
Name "Job Hunter"
OutFile "dist\job_hunter-setup.exe"
InstallDir "$LOCALAPPDATA\jobhunter"
RequestExecutionLevel user

!define MUI_ABORTWARNING
!define MUI_ICON "${NSISDIR}\Contrib\Graphics\Icons\modern-install.ico"
!define MUI_UNICON "${NSISDIR}\Contrib\Graphics\Icons\modern-uninstall.ico"

; ---- Pages ----
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_WELCOME
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH

!insertmacro MUI_LANGUAGE "English"

; ---- Install section ----
Section "Install"
  SetOutPath "$INSTDIR"
  ; PyInstaller outputs to dist\job_hunter\ as one-folder mode
  File /r "dist\job_hunter\*.*"

  ; Start menu shortcuts
  CreateDirectory "$SMPROGRAMS\JobHunter"
  CreateShortCut "$SMPROGRAMS\JobHunter\JobHunter.lnk" "$INSTDIR\job_hunter.exe"
  CreateShortCut "$SMPROGRAMS\JobHunter\Uninstall.lnk" "$INSTDIR\uninstall.exe"

  ; Desktop shortcut
  CreateShortCut "$DESKTOP\JobHunter.lnk" "$INSTDIR\job_hunter.exe"

  ; Uninstaller info
  WriteUninstaller "$INSTDIR\uninstall.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\jobhunter" "DisplayName" "Job Hunter"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\jobhunter" "UninstallString" "$INSTDIR\uninstall.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\jobhunter" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\jobhunter" "DisplayIcon" "$INSTDIR\job_hunter.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\jobhunter" "Publisher" "job_hunter"
SectionEnd

; ---- Uninstall section ----
Section "Uninstall"
  Delete "$SMPROGRAMS\JobHunter\JobHunter.lnk"
  Delete "$SMPROGRAMS\JobHunter\Uninstall.lnk"
  RMDir "$SMPROGRAMS\JobHunter"
  Delete "$DESKTOP\JobHunter.lnk"
  RMDir /r "$INSTDIR"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\jobhunter"
SectionEnd
