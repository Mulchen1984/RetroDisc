; RetroDisc — Inno Setup Installer Script
; Erstellt eine Setup.exe für Windows 10/11 (64-bit)
;
; Verwendung:
;   1. PyInstaller ausführen: pyinstaller retrodisc.spec
;   2. Inno Setup öffnen und diese Datei kompilieren
;   3. Ergebnis: Output/RetroDisc_Setup_1.0.0.exe
;
; Download Inno Setup: https://jrsoftware.org/isinfo.php

#define AppName "RetroDisc"
#define AppVersion "1.0.0"
#define AppPublisher "RetroDisc"
#define AppURL "https://github.com/marco/retrodisc"
#define AppExeName "retrodisc.exe"
#define AppDescription "All-in-One Media Suite"
#define SourceDir "dist\RetroDisc"

[Setup]
; Grundeinstellungen
AppId={{A7B3C241-D8E9-4F12-B3A5-C6D7E8F91234}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}

; Installationsverzeichnis
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes

; Zielplattform
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
MinVersion=10.0.17763   ; Windows 10 1809 minimum (WebView2 Voraussetzung)

; Ausgabe
OutputDir=Output
OutputBaseFilename=RetroDisc_Setup_{#AppVersion}
SetupIconFile=assets\retrodisc.ico

; Kompression
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes

; GUI
WizardStyle=modern
WizardSizePercent=120
DisableWelcomePage=no
DisableDirPage=no
DisableReadyPage=no

; Keine Admin-Rechte nötig wenn möglich
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; Deinstallation
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName} {#AppVersion}
CreateUninstallRegKey=yes

[Languages]
Name: "german";  MessagesFile: "compiler:Languages\German.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon";    Description: "Desktop-Verknüpfung erstellen"; GroupDescription: "Verknüpfungen:"; Flags: unchecked
Name: "quicklaunchicon"; Description: "Taskleisten-Verknüpfung erstellen"; GroupDescription: "Verknüpfungen:"; Flags: unchecked

[Files]
; Hauptprogramm (aus PyInstaller dist-Ordner)
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; Leerer tools-Ordner (FFmpeg etc. werden beim ersten Start geladen)
Source: "tools\.gitkeep"; DestDir: "{app}\tools"; Flags: ignoreversion

[Icons]
; Startmenü
Name: "{group}\{#AppName}";            Filename: "{app}\{#AppExeName}"; Comment: "{#AppDescription}"
Name: "{group}\{#AppName} deinstallieren"; Filename: "{uninstallexe}"

; Desktop (optional)
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon; Comment: "{#AppDescription}"

; Taskleiste (optional)
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: quicklaunchicon

[Run]
; Nach der Installation direkt starten (optional)
Filename: "{app}\{#AppExeName}"; Description: "{#AppName} jetzt starten"; Flags: nowait postinstall skipifsilent

[Registry]
; Dateiverknüpfungen registrieren (optional)
Root: HKCU; Subkey: "Software\RetroDisc"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\RetroDisc"; ValueType: string; ValueName: "Version"; ValueData: "{#AppVersion}"

[UninstallDelete]
; Logs und Einstellungen beim Deinstallieren löschen (nur auf Nachfrage)
; Type: filesandordirs; Name: "{localappdata}\RetroDisc"

[Code]
// Prüft ob WebView2 Runtime installiert ist (benötigt für PyWebView)
function IsWebView2Installed(): Boolean;
var
  version: String;
begin
  Result := RegQueryStringValue(
    HKLM,
    'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
    'pv',
    version
  ) and (version <> '0.0.0.0');

  if not Result then
    Result := RegQueryStringValue(
      HKCU,
      'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
      'pv',
      version
    ) and (version <> '0.0.0.0');
end;

procedure InitializeWizard();
begin
  // Willkommens-Nachricht anpassen
  WizardForm.WelcomeLabel2.Caption :=
    'Dieses Programm installiert RetroDisc ' + '{#AppVersion}' + ' auf Ihrem Computer.' + #13#10 + #13#10 +
    'RetroDisc ist eine All-in-One Media Suite zum Konvertieren, Brennen und Downloaden von Medien.' + #13#10 + #13#10 +
    'Beim ersten Start werden FFmpeg und yt-dlp automatisch heruntergeladen (~100 MB).' + #13#10 + #13#10 +
    'Es wird empfohlen, alle anderen Anwendungen zu schließen, bevor Sie mit der Installation fortfahren.';
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;

  // WebView2 prüfen bevor Installation abgeschlossen
  if CurPageID = wpReady then
  begin
    if not IsWebView2Installed() then
    begin
      if MsgBox(
        'Microsoft WebView2 Runtime wurde nicht gefunden.' + #13#10 + #13#10 +
        'RetroDisc benötigt WebView2 für die Benutzeroberfläche.' + #13#10 +
        'WebView2 ist auf Windows 11 vorinstalliert, auf Windows 10 muss es ggf. nachinstalliert werden.' + #13#10 + #13#10 +
        'Trotzdem fortfahren?',
        mbConfirmation,
        MB_YESNO
      ) = IDNO then
        Result := False;
    end;
  end;
end;
