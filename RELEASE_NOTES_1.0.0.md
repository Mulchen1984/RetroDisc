# RetroDisc 1.0.0 — Release Notes

> **Freigabestatus: NOT RELEASE READY — aktueller Windows-Patch in Pruefung.**
> Die unten genannten Hashes und Ergebnisse dokumentieren den historischen
> Build aus `1c486cc`. Sie belegen nicht die danach geaenderten Quellen.
> Ein frischer Build und erneute Artefaktpruefungen sind erforderlich.
> Details unter „Bekannte Einschränkungen".

Verbindliche Beleglage: `RELEASE_AUDIT_STATUS.md`. Jede Aussage über ein
Artefakt gilt nur für den hier genannten SHA-256.

## Stand

- Freeze-Commit: `1c486cc` (`DOCS: state the Windows-only scope and the real build path`)
- Tag: `v1.0.0-rc1`
- Bauweg: `python build.py --clean` über `retrodisc_final.spec`
- Signaturstatus: `Get-AuthenticodeSignature` meldet für App und Installer `NotSigned`

### Artefakte

| Artefakt | Größe (Bytes) | SHA-256 |
|---|---|---|
| `dist\RetroDisc.exe` | 502901640 | `F02096E77C78C307F97F16219B35FCBF8CA35DC94A3F3465A58B4D6A59AE2883` |
| `Output\RetroDisc_1.0.0_Portable.zip` | 501463750 | `B3B73C7621DE8BF33E83CADC871D5220534752D889632BFB4B11BB95D645B20D` |
| `Output\RetroDisc_Setup_1.0.0.exe` | 508841013 | `EACD6D2E0CAD91E4FFD55AAA1F6C23CF999416705E6DC03F9C8EE6A53961132D` |

Die im ZIP enthaltene `RetroDisc.exe` ist byteidentisch zur `dist`-EXE; das ZIP
enthält zusätzlich nur `README.md` und `START_WINDOWS.txt`. Der Installer bettet
ausschließlich die App-EXE ein.

### Gebündelte Werkzeuge

Alles Nötige liegt in der EXE; beim ersten Start wird nichts nachgeladen. Jede
Datei ist in `prepare_vendor.py` auf Version und SHA-256 gepinnt:

- FFmpeg / FFprobe — Autobuild `N-126342-gf88b741dbf-20260831`
- yt-dlp — `2026.08.19`
- DVD-Werkzeuge aus DVDStyler 3.2.1 — `dvdauthor.exe`, `mkisofs.exe`, `growisofs.exe`, `dvd+rw-mediainfo.exe`
- Faster-Whisper-Basismodell — `Systran/faster-whisper-base`

## Funktionsumfang

### Im Release-Audit real belegt

- **Konvertieren** — FFmpeg-Konvertierung mit 19 Presets (Video, Audio, Geräte,
  Disc) aus `src/config/presets.py`. Fortschrittsanzeige und Abbruch eines
  laufenden Jobs sind real geprüft; ein Abbruch hinterlässt keine Restdatei.
- **Bearbeiten** — Trim und Merge, 2×-Upscale, Frame-Interpolation auf 50 fps
  und automatische Highlight-Erkennung. Alle im vollständigen Real-Media-Smoke
  erzeugt und per FFprobe validiert.
- **Untertitel** — deutsche SRT über das gebündelte Faster-Whisper-Basismodell,
  ohne Internet und ohne separaten Modelldownload.
- **DVD-Authoring** — DVD-Struktur und ISO über `dvdauthor` und `mkisofs`
  (erzeugte Test-ISO: 2627584 Bytes).
- **Laufwerks- und Disc-Erkennung** — beide optischen Laufwerke dieses Rechners
  werden mit Name und Buchstaben gemeldet; an einem virtuell eingebundenen
  DVD-Abbild wurden Medium, Typ (`DVD-Video`), Label und Lesbarkeit korrekt
  erkannt. Ein fehlendes und ein leeres Laufwerk werden ohne Ausnahme korrekt
  als „kein Medium" gemeldet.
- **Rippen** — Rip-Workflow vom virtuellen Laufwerk nach ISO und weiter nach
  MKV/H.265; die gerippte Datei wurde per FFprobe als abspielbar bestätigt.
- **Download** — YouTube/Mediathek-Download über das gebündelte yt-dlp mit genau
  den produktiven Formatmustern aus `src/core/downloader.py`; Video- und
  MP3-Extraktionspfad real geprüft.
- **Job-Queue** — mehrere gleichartige Jobs laufen mit getrennten Handlern;
  Abbruch und Shutdown beenden laufende native Prozesse samt Prozessbaum.
- **Oberfläche** — die vier Hauptaktionen (Konvertieren, Brennen, Rippen,
  Download) und die Zusatzaktionen (Suche, Bearbeiten, AI Tools, Bibliothek,
  Job Queue, Einstellungen) wurden real angeklickt und öffnen die richtigen
  Ansichten. Während Start und Betrieb entsteht kein sichtbares Konsolenfenster.

### Enthalten, aber ohne eigenes Release-Gate

Diese Funktionen sind im Produkt vorhanden und von der Testsuite abgedeckt, aber
nicht als eigener End-to-End-Gate auf den finalen Artefakten belegt:

- **Mediensuche** über YouTube und die öffentlich-rechtlichen Mediatheken
  (ARD, ZDF, Arte, 3sat, phoenix und weitere).
- **Medienbibliothek** (SQLite mit FTS5-Volltextsuche).
- **Watch-Folder** für automatische Verarbeitung.
- **KI-Assistent** — benötigt ein **lokal laufendes Ollama** unter
  `http://localhost:11434`. Ollama ist nicht Teil der Auslieferung; ohne
  laufenden Dienst ist die Funktion nicht verfügbar.
- **Brennen auf einen Rohling** — der Brennaufruf
  (`growisofs.exe -dvd-compat -Z <Laufwerk>=<ISO> -speed 8`) wurde als Dry-Run
  geprüft, aber mangels Rohling **nie ausgeführt**. Siehe „Nicht getestet".

## Systemvoraussetzungen

- **Windows, 64-bit.** RetroDisc ist Windows-only; macOS und Linux werden nicht
  unterstützt und nicht gebaut (Plattformentscheidung vom 2026-09-03).
- Gebaut und geprüft wurde ausschließlich auf **Windows 11**. Windows 10 ist
  nicht geprüft.
- **Microsoft Edge WebView2 Runtime** — unter Windows 11 vorinstalliert. Ohne
  WebView2 öffnet sich kein Fenster.
- Rund **1 GB freier Speicher** für die Installation; die EXE entpackt sich
  beim Start zusätzlich temporär nach `%TEMP%`.
- Benutzerdaten, Logs und Einstellungen liegen unter `%LOCALAPPDATA%\RetroDisc`.
- Kein Internet für Konvertieren, Bearbeiten, Untertitel und DVD-Authoring —
  alle Werkzeuge sind gebündelt. Internet wird nur für Download, Suche und
  Assistent benötigt.
- Ein optisches Laufwerk wird nur für Brennen und Rippen gebraucht.
- Es werden keine Administratorrechte benötigt: Installation und Daten liegen im
  Benutzerprofil.

## Installation

### Installer

```bat
Output\RetroDisc_Setup_1.0.0.exe
```

Installiert standardmäßig nach `%LOCALAPPDATA%\Programs\RetroDisc` und legt
Desktop- und Startmenü-Verknüpfung an. Optionen:

| Option | Wirkung |
|---|---|
| `--dir <Pfad>` | abweichender Installationsordner |
| `--silent` | ohne Rückfrage installieren |
| `--no-desktop` | keine Desktop-Verknüpfung |
| `--no-start-menu` | keine Startmenü-Verknüpfung |
| `--launch` | RetroDisc nach der Installation starten |

Deinstalliert wird über den mitgelieferten `Uninstall RetroDisc.cmd` im
Installationsordner. Er entfernt Programmordner, Desktop- und
Startmenüverknüpfung vollständig.

### Portable

`RetroDisc_1.0.0_Portable.zip` entpacken und `RetroDisc.exe` starten. Keine
Installation, keine Registry-Einträge.

### Integrität prüfen

Vor dem ersten Start den SHA-256 gegen die Tabelle oben abgleichen:

```powershell
Get-FileHash .\RetroDisc_Setup_1.0.0.exe -Algorithm SHA256
```

Weicht der Hash ab, gilt keine der Aussagen in diesem Dokument.

## Getestet — mit Beleg im Journal

Alle Punkte sind in `RELEASE_AUDIT_STATUS.md` mit Datum, Werten und Ausgabepfad
dokumentiert:

- **Source-Gates** auf dem Freeze-Stand: 193 Tests grün, `compileall` Exitcode 0,
  `.hermes/verify_core.py` mit echter FFmpeg-Konvertierung.
- **UI/Bridge-Gate** (`scripts/verify_ui_bridge.py`): PASS, 0 Befunde — keine
  fehlenden Proxys, keine fehlenden Bridge-Ziele, keine Arity-Mismatches;
  `node --check` auf dem extrahierten Inline-JavaScript grün.
- **Real-Media-Smoke** (`scripts/release_smoke.py`): Exitcode 0, alle acht
  erwarteten Artefakte erzeugt und geprüft.
- **Artefakt-Gate** (`scripts/verify_release_artifacts.py`) auf den oben
  genannten Hashes: PASS, 0 Befunde — ZIP-Integrität, Authenticode-Status,
  Installation und Deinstallation in einer isolierten Sandbox.
- **Installation, Start aus der Installation, Deinstallation** zusätzlich real
  außerhalb der Sandbox: installierte EXE byteidentisch, Hauptfenster
  `RetroDisc 1.0`, Deinstallation rückstandsfrei mit Exitcode 0.
- **Disc-Gate** (`scripts/verify_disc_workflow.py`) gegen ein real erzeugtes und
  als virtuelles Laufwerk eingebundenes DVD-Abbild: PASS.
- **YouTube-Download** über den produktiven `Downloader`: PASS.

## Nicht getestet — ausdrücklich offen

- **Physischer Brennvorgang auf einen Rohling und die Rückleseprobe davon.** Es
  stand kein Medium zur Verfügung. Alles softwareseitig Prüfbare ist über das
  virtuelle DVD-Abbild belegt; der reale Brennvorgang ist dadurch **nicht**
  ersetzt. Das ist eine ausstehende Hardware-Validierung, kein bekannter
  Softwaremangel — aber auch kein Beleg, dass das Brennen funktioniert.
- **Auswertung des Medienprofils an einer echten Disc.** Die zugehörige Regex
  war fehlerhaft (sie verlangte Anführungszeichen, die `dvd+rw-mediainfo` nicht
  schreibt) und wurde korrigiert. Die Korrektur ist mangels Rohling nicht an
  einer echten Disc geprüft.
- **Windows 10.** Nur Windows 11 wurde verwendet.
- **Fremde Rechner.** Der Lauffähigkeitsbeleg auf einem Zweitrechner wurde nicht
  gefahren; die Anleitung dafür steht in `RUNTIME_GATE_ZWEITRECHNER.md`.
- **CD-Brennen.** `cdrecord` wird bewusst nicht gebündelt; die Oberfläche bietet
  kein CD-Brennen an. Der Pfad ist nur programmatisch über
  `burn_iso(disc_type=DiscType.CD)` erreichbar und ist ungetestet.
- **Signierte Artefakte.** Es existieren keine; entsprechend gibt es zum
  Verhalten signierter Builds keinerlei Messung.

## Bekannte Einschränkungen

### 1. Die Artefakte sind unsigniert — das ist der Releaseblocker

Auf dem Host existiert **kein vertrauenswürdiges Code-Signing-Zertifikat**. Im
Zertifikatspeicher liegt lediglich ein abgelaufenes, selbstsigniertes
`CN=RetroDisc Pipeline Selftest DO NOT TRUST` (`NotAfter` 2026-09-02,
`UntrustedRoot`) aus einem Pipelinetest. Als Signaturzertifikat ist es
unbrauchbar.

Ein selbst ausgestelltes Zertifikat löst das Problem grundsätzlich nicht: Smart
App Control prüft nicht den lokalen Zertifikatspeicher, sondern die eigene
Richtlinie und Microsofts Reputationsdienst. Erforderlich ist ein öffentlich
vertrauenswürdiges Code-Signing-Zertifikat.

**Folge: Eine Weitergabe an Dritte ist blockiert.** Der Bauweg für die Freigabe
steht bereit — Zertifikat hinterlegen, `python build.py --clean --sign` bauen und
alle Gates auf den dann entstehenden signierten Hashes wiederholen. `--sign`
bricht ohne Zertifikat hart ab, ein unbemerkt unsigniertes Release ist damit
ausgeschlossen.

### 2. Smart App Control entscheidet je Datei

Auf dem Entwicklungsrechner ist Smart App Control erzwingend aktiv
(`VerifiedAndReputablePolicyState = 1`). Die hier gemessenen finalen Artefakte
starteten ohne ein einziges CodeIntegrity-Ereignis — ein Vorgängerbuild wurde auf
demselben System im selben Zustand abgewiesen (Events 3033/3077).

**Ein bestandener Start belegt genau diese Bytes auf genau diesem Rechner.** Er
ist keine Zusage für andere Rechner oder künftige Builds. Smart App Control wurde
nicht abgeschaltet und keine Richtlinie umgangen; ein Abschalten ist unter
Windows nur durch eine Neuinstallation reversibel.

### 3. Startzeit und Größe

Die EXE ist ein Onefile-Bundle von rund 480 MB und entpackt sich bei jedem Start
nach `%TEMP%`. Gemessene Zeit bis zum Hauptfenster: 13,4 s beim portablen Start,
36,5 s beim Kaltstart aus der Installation. Das ist Entpackzeit, kein Hänger.

### 4. yt-dlp ist auf eine Version gepinnt

Der Download hängt an `yt-dlp 2026.08.19`. YouTube-seitige Änderungen können ihn
jederzeit brechen — genau das ist mit dem Vorgängerpin passiert
(`HTTP Error 403: Forbidden` auf allen produktiven Formatmustern). Der Pin muss
gepflegt werden; ein Update erfolgt über `prepare_vendor.py` und erfordert einen
neuen Build.

### 5. Antivirus und SmartScreen

Unsignierte PyInstaller-Builds lösen bei Virenscannern regelmäßig Fehlalarme aus,
und SmartScreen warnt beim ersten Start. Beides verschwindet erst mit einer
vertrauenswürdigen Signatur.

### 6. Randbeobachtung beim Installer

Beim Lauf des Installers in der Sandbox erschienen zwei CodeIntegrity-Ereignisse
(3033/3077) für `_bz2.pyd` aus dem entpackten Installer-Bundle. Die Installation
lief trotzdem vollständig und korrekt durch; das Modul ist für den Installer
nicht erforderlich. Die App-EXE selbst erzeugte in keinem Lauf ein Ereignis.
