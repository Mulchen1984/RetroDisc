# CLAUDE.md — Arbeitsanweisungen für RetroDisc

Diese Datei beschreibt, wie in diesem Repository gearbeitet wird. Sie ersetzt
eine ältere Fassung, die eine von Hand gepflegte PyInstaller-Kommandozeile
enthielt. Diese Kommandozeile war nicht mehr der Bauweg: sie baute aus
`retrodisc_portable.py` statt aus dem produktiven Einstieg, nannte das längst
ersetzte `openai-whisper` und bündelte weder die DVD-Werkzeuge noch das
Whisper-Modell.

## Zuerst lesen

`RELEASE_AUDIT_STATUS.md` ist das verbindliche Status- und Journaldokument.
Vor jeder Arbeit lesen, Arbeitsblöcke hinten anhängen, den Status nur mit
echten Belegen ändern. Unbelegte Aussagen gehören dort nicht hinein: eine
Aussage über ein Artefakt gilt immer nur für den konkreten SHA-256, an dem sie
gemessen wurde.

## Runtime: nicht die `.venv`-EXE benutzen

Smart App Control ist auf dem Entwicklungsrechner erzwingend aktiv und
blockiert die kopierte `.venv\Scripts\python.exe`. Alle Läufe deshalb mit der
freigegebenen Python-3.11-Runtime und der venv als Pfad:

```bat
set PYTHONPATH=.venv\Lib\site-packages
C:\Users\marco\.local\bin\python3.11.exe -m pytest -q
```

Dasselbe Muster gilt für `build.py`, `prepare_vendor.py`, die Skripte unter
`scripts/` und `.hermes/verify_core.py`.

## Aufbau

- `retrodisc_launcher.py` — produktiver Einstieg der gepackten EXE. Enthält
  `RetroDiscBridge` (Implementierung) und `RetroDiscApi` (schlanker Proxy, den
  PyWebView tatsächlich bekommt). **Nicht** `src/ui/desktop.py` prüfen: das
  verwendet die gepackte EXE nicht.
- `src/ui/app.html` — die gesamte Oberfläche samt Inline-JavaScript.
- `src/core`, `src/services`, `src/config`, `src/models` — Medienpipeline,
  Werkzeuge und Einstellungen.
- `src/utils/subprocesses.py` — jeder Hintergrundprozess läuft über diese
  Helfer: verstecktes Fenster, lenientes Dekodieren der Konsolenausgabe,
  begrenztes Streamen, Prozessbaum-Abbruch und atomare Ausgabedateien.
- `prepare_vendor.py` — erzeugt `vendor/` vollständig und auf feste Versionen
  und SHA-256 gepinnt: FFmpeg, FFprobe, yt-dlp, `dvdtools/` und
  `whisper-base/`.
- `build.py` — der Bauweg. Baut über `retrodisc_final.spec`.

## Gates

Alle fünf müssen grün sein, bevor ein Stand eingefroren wird:

```bat
C:\Users\marco\.local\bin\python3.11.exe -m pytest -q
C:\Users\marco\.local\bin\python3.11.exe -m compileall -q src tests retrodisc_launcher.py retrodisc_portable.py
C:\Users\marco\.local\bin\python3.11.exe .hermes\verify_core.py
C:\Users\marco\.local\bin\python3.11.exe scripts\verify_ui_bridge.py
C:\Users\marco\.local\bin\python3.11.exe scripts\release_smoke.py
node --check build\ui-audit\inline.js
```

`verify_ui_bridge.py` prüft die Kette UI → `RetroDiscApi` → `RetroDiscBridge`
auf fehlende Proxys, fehlende Bridge-Ziele und Arity-Mismatches und legt
nebenbei das extrahierte Inline-JavaScript für `node --check` ab.
`release_smoke.py` fährt echte Medienarbeit: Trim, Merge, 2×-Upscale,
50-fps-Interpolation, Highlights, deutsche Faster-Whisper-SRT und eine
DVD-ISO.

## Bauen und Artefakte prüfen

Immer aus einem eingefrorenen Commit bauen, nie aus einem schmutzigen
Arbeitsbaum:

```bat
C:\Users\marco\.local\bin\python3.11.exe build.py --clean
C:\Users\marco\.local\bin\python3.11.exe scripts\verify_release_artifacts.py
```

Ergebnis sind `dist\RetroDisc.exe`, `Output\RetroDisc_1.0.0_Portable.zip` und
`Output\RetroDisc_Setup_1.0.0.exe`. `verify_release_artifacts.py` hasht die
drei Artefakte, prüft die ZIP-Integrität gegen die `dist`-EXE, liest den
Authenticode-Status und fährt Installation und Deinstallation real in einer
Sandbox, in der `USERPROFILE`, `APPDATA` und `LOCALAPPDATA` umgelenkt sind.
Die gemessenen Hashes gehören anschließend ins Journal.

## Plattform

Aktueller Nutzerauftrag vom 2026-09-05: zuerst Windows fertigstellen;
macOS danach auf denselben Funktionsstand bringen. Die folgenden Angaben
beschreiben den derzeit belegten Bauweg, keine dauerhafte Absage an macOS.

RetroDisc ist ein **Windows**-Produkt. `build.py` baut für Windows,
`prepare_vendor.py` vendort Windows-Binärdateien, und
`.github/workflows/build.yml` enthält genau einen Buildjob (`build-windows`).
Der macOS-Job wurde am 2026-09-03 bewusst gestrichen; die Entscheidung steht im
Journal.

Verbliebene macOS-Reste im Repository — an keinem Gate belegt, von keinem
Buildpfad referenziert, nicht unterstützt:

- `BUILD_MACOS.sh`
- `create_dmg.py`
- `assets/retrodisc.icns` (wird ausschließlich von `BUILD_MACOS.sh` benutzt)

`retrodisc.spec` und `retrodisc_onefile.spec` sind **keine** macOS-Reste,
sondern ältere Windows-Specs. Produktiv ist ausschließlich
`retrodisc_final.spec` über `build.py`. `retrodisc_portable.py` und
`src/ui/desktop.py` enthalten weiterhin Plattformzweige für Darwin/Linux;
beide sind nicht der produktive Einstieg der gepackten EXE.

## Signierung

Ohne vertrauenswürdiges Code-Signing-Zertifikat bleiben die Artefakte
unsigniert und damit nicht verlässlich weitergebbar. Details und die
Umgebungsvariablen stehen in `README.md`. Ein selbst ausgestelltes Zertifikat
löst das **nicht** — Smart App Control prüft nicht den lokalen
Zertifikatspeicher. Die Richtlinie wird nie umgangen oder verändert.

## Aktuelle UI-/UX- und Produktvorgaben

Diese Vorgaben stammen aus der laufenden Produktabnahme und gelten bis zu einer
expliziten Änderung durch den Nutzer:

- Die Startseite hat vier Primäraktionen in dieser Reihenfolge (Stand
  2026-09-11, korrigiert vom Nutzer): **Rippen, Disc kopieren, Konvertieren,
  Brennen**. Rippen ist bewusst der erste, visuelle Einstiegspunkt; Brennen
  steht bewusst zuletzt, da es bereits vorhandenen Inhalt voraussetzt. Die
  Bibliothek ist **kein** eigener Medien-/ISO-Workflow und darf nicht als
  Hauptaktion dargestellt werden - sie bleibt ausschließlich sekundär unter
  "Weitere Werkzeuge". Download ist ebenfalls keine gleichwertige Hauptaktion
  und liegt unter den Werkzeugen (sekundäre Aktionen). Alle vier
  Hauptaktionen müssen in der vorgesehenen Fenstergröße vollständig sichtbar
  sein; kein Abschneiden oder horizontaler Scroll-Zwang.
- Blu-ray ist in der UI sichtbar, nicht nur im Backend: Rippen zeigt nach
  Laufwerksauswahl/-analyse erkannten Medientyp (DVD/Blu-ray), Label und
  Größe. Brennen zeigt eine echte Zielmedienauswahl (DVD-5, DVD-9, BD-25,
  BD-50, BDXL-100, BDXL-128, Custom) und Laufwerks-Fähigkeitsbadges
  (DVD/Blu-ray/BDXL lesen/schreiben), abgeleitet aus dem bestehenden
  `inspect_drive`/`DriveCapabilities`-Backend.
- BDMV-Authoring ist seit 2026-09-11 real implementiert (`src/services/
  bluray_authoring.py` + `bluray_workflow.py`, Bridge-Methoden `create_bluray`
  und `burn_existing_iso`), nicht nur simuliert: FFmpeg erzeugt BD-konforme
  M2TS-Clips (BDAV-192-Byte-Pakete via `-mpegts_m2ts_mode`, feste PIDs
  0x1011/0x1100), `bluray_authoring.py` schreibt PLAYLIST/CLIPINF/index.bdmv/
  MovieObject.bdmv drumherum. MPLS ist byte-exakt zum bereits produktiven
  Leser (`bluray_mpls.py`) und wird per echtem Round-Trip getestet; CLPI/
  index.bdmv/MovieObject.bdmv sind strukturell konsistent, aber ohne
  unabhängigen Referenz-Decoder nicht bit-für-bit spec-verifiziert (das
  MovieObject trägt bewusst keine HDMV-Navigationsbefehle - siehe Moduldoku
  in `bluray_authoring.py` für die genaue Abgrenzung). `DiscTools.create_iso`
  ist für Blu-ray gehärtet: Flag-Fallback (`-allow-limited-size` ->
  `-udf -iso-level 3`, real gegen einen dvdrtools-mkisofs-Fork getestet, der
  das erste Flag nicht kennt) plus eine Größenprüfung nach der Erstellung,
  die einen stillschweigend verworfenen >4-GiB-Clip als Fehler statt als
  falschen Erfolg meldet. Zielmedien-Verfügbarkeit (`list_target_media`s
  `authoring_available`, `check_target_medium`, `target_medium_capability_issue`
  in `src/config/target_media.py`) prüft echte Backend- UND Laufwerks-
  fähigkeit, bevor die UI ein Ziel aktiviert oder `create_bluray`/
  `burn_existing_iso` überhaupt einreiht (Verteidigung in der Tiefe, nicht
  nur UI-Anzeige); fehlende Fähigkeiten (kein Blu-ray-Lesen/-Schreiben, kein
  BDXL) deaktivieren die entsprechenden Optionen weiterhin - keine
  Unterstützung vortäuschen.
- Die visuelle Sprache darf klar an klassische CloneCD-artige Disc-Utilities
  erinnern, aber es werden **keine originalen CloneCD-Assets oder GIFs 1:1
  übernommen**. Eigene SVGs/Animationen zeichnen.
- Disc-Funktionen verwenden eine einheitliche goldene/orange Disc-Sprache.
  **Brennen/Schreiben = Disc + Stift/Bleistift**. **Rippen/Lesen = Disc +
  Brille**. **Disc kopieren = zwei Discs mit klarer Kopierbeziehung**.
  Konvertieren bleibt ein eigenes Medien-/Format-Symbol ohne Disc-Zwang.
- Dezente Retro-Animationen sind erwünscht: beim Brennen darf der Stift eine
  kleine Schreibbewegung machen, beim Rippen darf die Brille eine kleine
  Lese-/Scanbewegung machen. Keine blinkenden oder hektischen Effekte.
- Die Endnutzer-/Release-Anwendung darf beim normalen Start **kein sichtbares
  Python-, CMD- oder PowerShell-Konsolenfenster** zeigen. Ein Source-Run über
  `python3.11.exe` ist nur Developer Mode und kein gültiger visueller
  Produktnachweis.
- Der Release-Build muss im äußeren Windows-Titelbalken und in der Taskleiste
  das **RetroDisc-Icon**, nicht das Python-Icon zeigen. Die vorhandene
  `retrodisc_final.spec`-Konfiguration mit `console=False` und
  `assets/retrodisc.ico` ist der Referenzweg.
- Beim normalen Programmstart werden **keine optischen Laufwerke erkannt** und
  dafür keine PowerShell-/CMD-Helfer gestartet. Laufwerke ausschließlich lazy
  beim Öffnen von Disc kopieren, Brennen oder Rippen bzw. über "Neu suchen"
  erkennen; innerhalb der Sitzung cachen, keine periodische Hintergrundsuche.
- Browser-/WebView-History darf RetroDisc nicht verlassen. Maus-Zurück/-Vorwärts
  darf die WebView-History nicht auf Splash oder andere Dokumente bewegen; die
  eigene interne Navigation muss funktionieren.
- "Disc kopieren" darf einen Abbild-Workflow anbieten, aber **echtes
  On-the-fly** nur dann so nennen, wenn tatsächlich direkt von Quelllaufwerk zu
  Ziellaufwerk gestreamt wird. Ein sequenzielles Rippen in ein temporäres Image
  und anschließendes Brennen ist kein On-the-fly und darf nicht so beschriftet
  werden.
- Physische Disc-Brenn-/Kopierpfade gelten ohne echte Laufwerke und Medien nicht
  als hardwareverifiziert. Das in Status/Journals klar kennzeichnen.
- Seit 2026-09-12 gibt es einen echten Vorschau-/Preview-Player ("Vorschau",
  eigener Tab + "Vorschau"-Button je Titel im Rippen-Bereich): `src/services/
  player.py` steuert eine echte `mpv`-Instanz per JSON-IPC (`--input-ipc-
  server`, derselbe Subprozess-Pfad wie FFmpeg/dvdauthor/growisofs) - kein
  HTML5-`<video>`-Tag, keine eigene Decoder-Implementierung. Engine-Wahl
  (mpv vs. VLC/libVLC vs. HTML5) inklusive der Begründung steht im
  Moduldocstring von `player.py`; `python-mpv`s ctypes-Bindings stürzen in
  dieser Entwicklungsumgebung real reproduzierbar ab und wurden deshalb
  verworfen. `src/services/player_source.py` löst einen DiscContent-Titel-
  Index zu einer abspielbaren Datei-/Segmentliste auf (wiederverwendet
  `dvd_ifo.parse_tt_srpt`/`bluray_mpls.parse_mpls`, keine parallele Disc-
  Analyse) - mehrsegmentige Titel (mehrere VOB-Dateien, mehrere MPLS-Clips)
  laufen über mpvs `edl://`-Protokoll als EINE zusammenhängende Zeitleiste.
  `src/services/iso_mount.py` mountet DVD-/Blu-ray-ISOs temporär (macOS
  `hdiutil`, Windows `Mount-DiskImage` - Windows-Zweig in dieser Umgebung
  nicht laufzeitgeprüft) und hängt sie garantiert wieder aus. DVD-/Blu-ray-
  Menüs (HDMV/BD-J) sind ausdrücklich NICHT Teil dieses Blocks - der Player
  spielt logische Titel/Kapitel/Streams, keine Menü-Navigation. CSS/AACS/
  BD+ werden nicht unterstützt und nicht vorgetäuscht (siehe
  `src/services/drm_capabilities.py`); kopiergeschützte Medien benötigen
  weiterhin ein externes Werkzeug (z. B. MakeMKV, dieselbe Haltung wie
  `ripper.py`). Für Windows-Produktionsbuilds muss `mpv` noch wie FFmpeg/
  dvdauthor über `prepare_vendor.py` vendort werden - bisher nur über
  Homebrew auf dem macOS-Entwicklungsrechner installiert und getestet.
