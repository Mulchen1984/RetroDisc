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

RetroDisc ist ein **Windows**-Produkt. `build.py` baut für Windows,
`prepare_vendor.py` vendort Windows-Binärdateien, und die CI baut ausschließlich
Windows-Artefakte. Es gibt weiterhin macOS-Reste im Repository
(`BUILD_MACOS.sh`, `create_dmg.py`, `retrodisc.spec`); sie sind an keinem Gate
belegt und dürfen nicht als unterstützter Pfad dargestellt werden.

## Signierung

Ohne vertrauenswürdiges Code-Signing-Zertifikat bleiben die Artefakte
unsigniert und damit nicht verlässlich weitergebbar. Details und die
Umgebungsvariablen stehen in `README.md`. Ein selbst ausgestelltes Zertifikat
löst das **nicht** — Smart App Control prüft nicht den lokalen
Zertifikatspeicher. Die Richtlinie wird nie umgangen oder verändert.
