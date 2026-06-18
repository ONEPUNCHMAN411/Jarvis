; JARVIS Setup — NSIS Installer Script
; Builds: JARVIS-Setup-v1.1.0.exe
;
; Requirements:
;   - NSIS 3.x  (winget install NSIS.NSIS)
;   - PyInstaller onedir build must exist at dist\JARVIS\ (run build_exe.py --installer first)
;
; Build command (from the jarvis\ root):
;   makensis installer\jarvis_setup.nsi

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "WinVer.nsh"

; Metadata
Name              "JARVIS"
OutFile           "JARVIS-Setup-v1.1.0.exe"
InstallDir        "$PROGRAMFILES64\JARVIS"
InstallDirRegKey  HKCU "Software\JARVIS" "InstallDir"
RequestExecutionLevel admin
Unicode           True
SetCompressor     zlib

; Version info embedded in EXE properties
VIProductVersion  "1.1.0.0"
VIAddVersionKey   "ProductName"      "JARVIS"
VIAddVersionKey   "ProductVersion"   "1.1.0"
VIAddVersionKey   "CompanyName"      "MrClipperz"
VIAddVersionKey   "LegalCopyright"   "© 2026 MrClipperz"
VIAddVersionKey   "FileDescription"  "JARVIS AI Desktop Assistant Setup"
VIAddVersionKey   "FileVersion"      "1.1.0.0"

; MUI branding
!define MUI_ABORTWARNING
!ifdef MUI_ICON
!undef MUI_ICON
!endif
!ifdef MUI_UNICON
!undef MUI_UNICON
!endif

; Welcome
!define MUI_WELCOMEPAGE_TITLE    "Welcome to JARVIS v1.1.0 Setup"
!define MUI_WELCOMEPAGE_TEXT     "JARVIS is your AI desktop assistant for Windows 11.$\r$\n$\r$\nThis installer will:$\r$\n  • Copy JARVIS to Program Files$\r$\n  • Install the Chromium browser (for web automation)$\r$\n  • Create Start Menu and Desktop shortcuts$\r$\n$\r$\nClick Next to continue."
!insertmacro MUI_PAGE_WELCOME

; License
!insertmacro MUI_PAGE_LICENSE "..\LICENSE"

; Components
!insertmacro MUI_PAGE_COMPONENTS

; Directory
!define MUI_PAGE_HEADER_TEXT    "Choose Install Location"
!define MUI_PAGE_HEADER_SUBTEXT "JARVIS will be installed in the folder below."
!insertmacro MUI_PAGE_DIRECTORY

; Install progress
!insertmacro MUI_PAGE_INSTFILES

; Finish
!define MUI_FINISHPAGE_RUN         "$INSTDIR\JARVIS.exe"
!define MUI_FINISHPAGE_RUN_TEXT    "Launch JARVIS now"
!define MUI_FINISHPAGE_TITLE       "JARVIS is installed!"
!define MUI_FINISHPAGE_TEXT        "JARVIS v1.1.0 is ready.$\r$\n$\r$\nThe first launch will open a setup wizard where you can configure your AI provider, voice settings, and API keys.$\r$\n$\r$\nClick Finish to exit the installer."
!insertmacro MUI_PAGE_FINISH

; Uninstall
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

; ── Install Section ───────────────────────────────────────────────────────────

Section "JARVIS (required)" SecMain
    SectionIn RO

    SetOutPath "$INSTDIR"
    SetOverwrite on

    ; Copy all files from PyInstaller onedir build
    File /r "..\dist\JARVIS\*"

    ; Write registry
    WriteRegStr HKCU "Software\JARVIS" "InstallDir" "$INSTDIR"
    WriteRegStr HKCU "Software\JARVIS" "Version"    "1.1.0"

    ; Uninstaller
    WriteUninstaller "$INSTDIR\Uninstall.exe"

    ; Add/Remove Programs entry
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\JARVIS" \
        "DisplayName"     "JARVIS"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\JARVIS" \
        "DisplayVersion"  "1.1.0"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\JARVIS" \
        "Publisher"       "MrClipperz"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\JARVIS" \
        "UninstallString" "$INSTDIR\Uninstall.exe"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\JARVIS" \
        "DisplayIcon"     "$INSTDIR\JARVIS.exe"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\JARVIS" \
        "InstallLocation" "$INSTDIR"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\JARVIS" \
        "URLInfoAbout"    "https://github.com/ONEPUNCHMAN411/Jarvis"
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\JARVIS" \
        "NoModify" 1
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\JARVIS" \
        "NoRepair"  1
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\JARVIS" \
        "EstimatedSize" 1900000

    ; Start Menu shortcuts
    CreateDirectory "$SMPROGRAMS\JARVIS"
    CreateShortcut  "$SMPROGRAMS\JARVIS\JARVIS.lnk"    "$INSTDIR\JARVIS.exe" "" "$INSTDIR\JARVIS.exe" 0
    CreateShortcut  "$SMPROGRAMS\JARVIS\Uninstall.lnk" "$INSTDIR\Uninstall.exe"

    ; Install Playwright Chromium — required for browser automation tools.
    ; JARVIS.exe bundles Python + Playwright; we call it with --install-playwright
    ; so users get web automation working out of the box without any manual steps.
    DetailPrint "Installing Playwright Chromium browser (needed for web automation)..."
    ExecWait '"$INSTDIR\JARVIS.exe" --install-playwright' $0
    ${If} $0 != 0
        DetailPrint "Playwright install returned $0 — web automation may require manual setup."
        DetailPrint "Run: JARVIS.exe --install-playwright   to retry later."
    ${Else}
        DetailPrint "Playwright Chromium installed successfully."
    ${EndIf}

SectionEnd

; ── Desktop Shortcut (optional) ───────────────────────────────────────────────

Section "Desktop Shortcut" SecDesktop
    CreateShortcut "$DESKTOP\JARVIS.lnk" "$INSTDIR\JARVIS.exe" "" "$INSTDIR\JARVIS.exe" 0
SectionEnd

; ── Start with Windows (optional) ────────────────────────────────────────────

Section /o "Start JARVIS with Windows" SecStartup
    WriteRegStr HKCU \
        "Software\Microsoft\Windows\CurrentVersion\Run" \
        "JARVIS" \
        '"$INSTDIR\JARVIS.exe" --minimized'
SectionEnd

; ── Section descriptions ──────────────────────────────────────────────────────

LangString DESC_SecMain    ${LANG_ENGLISH} "Core JARVIS application files. Required."
LangString DESC_SecDesktop ${LANG_ENGLISH} "Add a JARVIS shortcut to your Desktop."
LangString DESC_SecStartup ${LANG_ENGLISH} "Automatically start JARVIS when Windows boots (runs minimized in system tray)."

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
    !insertmacro MUI_DESCRIPTION_TEXT ${SecMain}    $(DESC_SecMain)
    !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop} $(DESC_SecDesktop)
    !insertmacro MUI_DESCRIPTION_TEXT ${SecStartup} $(DESC_SecStartup)
!insertmacro MUI_FUNCTION_DESCRIPTION_END

; ── Uninstall Section ─────────────────────────────────────────────────────────

Section "Uninstall"
    RMDir /r "$INSTDIR"
    RMDir /r "$SMPROGRAMS\JARVIS"
    Delete "$DESKTOP\JARVIS.lnk"
    DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "JARVIS"
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\JARVIS"
    DeleteRegKey HKCU "Software\JARVIS"
SectionEnd
