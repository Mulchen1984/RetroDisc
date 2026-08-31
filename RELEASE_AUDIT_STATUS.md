# RetroDisc Release-Audit-Status

Letzte Aktualisierung: 2026-08-31 18:25 CEST

## Verbindlicher Abschlussstatus

NOT RELEASE READY

Begründung: Source-Audit und unabhängige QA sind geschlossen; Source-Freeze, Neubau und reale Artefakttests sind noch nicht abgeschlossen. Vorhandene Dateien in `dist/` und `Output/` sind Altartefakte und gelten nicht als validiert.

## Aktueller Checkpoint

- Branch: `main`
- Aktueller HEAD: `4127261dcd81badb8780bc9a81c7402440f443ee` (`AUDIT: document verified release baseline`)
- Baseline-Commit: `e29f41d` (`BASELINE: preserve initial RetroDisc source state`)
- Aktueller Arbeitsbaum: elf dokumentierte und vollständig verifizierte Dateien; Source-Audit und unabhängige QA PASS, Source-Freeze-Commit als nächster Schritt
- Baseline-Manifest: `BASELINE_SHA256_MANIFEST.json`
- Manifestumfang: 147 Einträge, 679158086 Bytes
- Live-Verifikation gegen Manifest: 0 fehlende oder abweichende Einträge
- Das Manifest umfasst Source/UI/Tests/Build-Konfiguration/Assets und benötigte Vendor-Runtimes; Build-Ausgaben, Caches und Umgebungen sind ausgeschlossen.

## Eingelesener Bestand

- Git-Status und Commit-Historie
- `BASELINE_SHA256_MANIFEST.json`
- `.audit_tmp/` einschließlich `ui_inventory.json`, extrahiertem JavaScript und API-Signaturvergleich
- `.hermes/verify_core.py`
- `scripts/release_smoke.py`
- Test-Suite und vorhandene Build-/Installer-Skripte
- PyInstaller-Spec `retrodisc_final.spec`
- Vorhandene `dist/`-/`Output/`-Artefakte (noch nicht als Releasebeleg anerkannt)

## Bereits verifizierte Ausgangslage

- UI-Inventar: 117 IDs / 117 eindeutig; 87 JavaScript-Funktionen / 87 eindeutig; keine undefinierten Inline-Handler; keine API-Aufrufe ohne Proxy-Methode.
- Der vorhandene Signaturvergleich JavaScript -> `src/ui/desktop.py:RetroDiscAPI` meldete keine Mismatches, prüfte aber nicht den produktiven PyInstaller-Einstieg `retrodisc_launcher.py:RetroDiscApi/RetroDiscBridge`; diese Audit-Lücke wurde im aktuellen Arbeitsblock erkannt.
- Extrahiertes Inline-JavaScript: `node --check` erfolgreich.
- `pytest -q`: **59 passed in 7.07s** (erneut bestätigt 2026-08-30 19:49 CEST).
- `compileall`: erfolgreich, Exitcode 0.
- `.hermes/verify_core.py`: erneut erfolgreich; echte MP3-Konvertierung beendet mit Jobstatus `done`, Progress 100 %, Ausgabedatei 403477 Bytes, Audio-Codec MP3; Pipeline sauber gestoppt.
- Baseline-Manifest erneut geprüft: 147/147 Einträge vorhanden und SHA256-/größenidentisch; 0 Abweichungen.
- Extrahiertes Inline-JavaScript erneut mit `node --check` geprüft; API-Signaturvergleich weiterhin ohne Mismatch.

## Release-Smoke-Reproduktion

- Der erneute Lauf von `scripts/release_smoke.py` auf dem unveränderten Baseline-Stand endete mit Exitcode 0.
- Ausgabe: `build/e2e-smoke-20260830-193542`.
- Zweiter Wiederholungslauf ebenfalls Exitcode 0; Ausgabe: `build/e2e-smoke-20260830-194956`.
- Erzeugt und validiert: Trim A/B, Merge, 2x-Upscale, 50-fps-Interpolation, Highlights, echte deutsche Faster-Whisper-SRT und DVD-ISO.
- Das frühere Verzeichnis `build/e2e-smoke-20260830-144811` endet nach `highlights.mp4`; Traceback/stdout/stderr des damaligen Exitcodes 1 wurden nicht persistiert.
- Bis zum 2026-08-30 war der frühere Fehler mangels damaligem Traceback **nicht reproduzierbar**; zu diesem Zeitpunkt wurde bewusst keine Ursache behauptet.
- Nach Wiederaufnahme am 2026-08-31 wurde der historische Abbruchpunkt unmittelbar nach `highlights.mp4` reproduziert: `faster-whisper 1.2.0` importierte `requests`, das weder upstream als Paketabhängigkeit noch in RetroDiscs Release-Abhängigkeiten deklariert war. Vollständiger Traceback: `ModuleNotFoundError: No module named 'requests'` aus `faster_whisper.utils`.
- Nach der Release-Dependency-/Packaging-Korrektur lief `scripts/release_smoke.py` auf dem aktuellen Source vollständig mit Exitcode 0. Ausgabe: `build/e2e-smoke-20260831-181318`; alle acht erwarteten Artefakte inklusive deutscher SRT und DVD-ISO wurden erzeugt und validiert.
- Nach Schließung des verbleibenden Convert-/Download-/Watch-Folder-Handlerpfads lief der vollständige Smoke auf dem finalen Source erneut mit Exitcode 0. Ausgabe: `build/e2e-smoke-20260831-182105`.

## Offene Release-Blocker / Nachweise

- Source Freeze noch nicht erstellt.
- EXE/Portable/Installer noch nicht aus dem späteren Source Freeze neu gebaut.
- Gepackte EXE, Portable ZIP, Installation und Deinstallation noch nicht real end-to-end getestet.
- Physische Burn-/Rip-Tests sind hardware- und medienabhängig und müssen separat ausgewiesen werden.

## Claude-Code-Einsatz

- Claude Code 2.1.251 ist installiert.
- Ein echter Claude-Code-Lead wurde mit `claude -p --model opus --effort max ...` gestartet.
- Vier echte spezialisierte Opus-Audits wurden zusätzlich parallel mit `claude -p --model opus --effort xhigh ...` gestartet: Frontend/UI/PyWebView, Backend/Media-Pipeline, Release-Smoke/Packaging und Special Features.
- Alle fünf Aufrufe wurden vom Claude-Dienst ohne Analyseergebnis mit `You've hit your session limit · resets 12:30am (Europe/Berlin)` beendet. Sie haben keine Produktdateien geändert und keine Auditberichte erzeugt.
- `claude ultrareview` endete ohne Review, weil der Vergleich gegen den aktuellen HEAD leer war; daraus wurde kein QA-Ergebnis abgeleitet.
- Der früher dokumentierte Hintergrund-Runner hinterließ bis 2026-08-31 18:06 CEST weder Prozesslog noch Review und lief nicht mehr; er wurde daher nicht als Auditbeleg gewertet.
- Genau ein neuer, strikt read-only und auf sechs Dateien begrenzter Claude-Sonnet-Review mit `--effort high` prüfte Klassifikation, Dependency-/Packaging-Fix, Regressionstest und Smoke-Bootstrap. Ergebnis: **PASS**, kein Blocker, keine Dateiänderung. Keine parallelen Claude-Code-Audits wurden gestartet.
- Nach dem letzten per-Job-Handler-Fix prüfte genau ein weiterer serieller Claude-Sonnet/high-Auftrag den finalen Arbeitsbaum read-only. Ergebnis: **PASS, keine Release-Blocker**. Geprüft wurden Handler, Cancel/Shutdown, UI/Bridge, Settings, Whisper/Packaging, Regressionstests und direkte Verifikationsskripte. Keine Dateiänderung.
- Der alte Hermes-Cronjob `RetroDisc Claude Opus continuation` wurde entfernt; `cronjob list` meldete danach 0 Jobs. Es startet daher kein alter Claude-Cronjob parallel.

## Änderungs- und Testjournal

### 2026-08-30 19:35 CEST — Phase 1

- Bestehenden Stand eingelesen; keine Arbeit verworfen oder neu begonnen.
- Sauberen Git-Baseline-Checkpoint `e29f41d` und Manifestkonsistenz bestätigt.
- Basistests und Kern-Bridge-Integration erfolgreich ausgeführt.
- Vorhandene Release-Artefakte ausdrücklich als nicht final/ungeprüft markiert.

### 2026-08-30 19:37 CEST — Release-Smoke-Reproduktion

- `scripts/release_smoke.py` vollständig mit Exitcode 0 ausgeführt.
- Reale Medienwerte: Merge 20,72 s bei 1280x720/25 fps; Upscale 2560x1440/25 fps; Interpolation 1280x720/50 fps; Highlights 6,013968 s.
- Faster Whisper lud das gebündelte Base-Modell und erzeugte 2 deutsche SRT-Segmente.
- `dvdauthor` und `mkisofs` erzeugten eine DVD-Struktur und `RetroDisc_Smoke.iso` mit 2627584 Bytes.

### 2026-08-30 19:42–19:48 CEST — Claude-Code-Aufrufe

- Claude Lead und vier spezialisierte, dateiseitig getrennte Audit-Aufrufe real gestartet.
- Alle Aufrufe durch das serverseitige Claude-Sessionlimit blockiert; Reset laut CLI um 00:30 Europe/Berlin.
- Keine Agentenaussage als geprüft übernommen; keine Claude-basierten Fixes behauptet.

### 2026-08-30 19:49–19:51 CEST — Wiederaufnahme / aktueller Checkpoint

- HEAD `4127261dcd81badb8780bc9a81c7402440f443ee` und den ausschließlich durch diese Statuspflege geänderten Arbeitsbaum bestätigt.
- Baseline-Manifest: 147/147 Einträge, 0 fehlend, 0 Größen-/SHA256-Abweichungen.
- `pytest -q`: 59 passed in 7.07s.
- `compileall`: Exitcode 0.
- `.hermes/verify_core.py`: Exitcode 0; echter FFmpeg-Konvertierungsjob `done`, 100 %, MP3 403477 Bytes; Pipeline sauber gestoppt.
- `node --check .audit_tmp/inline.js` und `.audit_tmp/compare.py`: Exitcode 0, keine JS/API-Signaturmismatches.
- `scripts/release_smoke.py`: erneut Exitcode 0; alle acht erwarteten Medien-/Untertitel-/ISO-Artefakte erzeugt und geprobt.
- Phase 1 ist damit ohne Wiederholung bereits erledigter Produktarbeit aktuell verifiziert. Der historische Smoke-Fehler bleibt mangels damaligem Traceback nicht reproduzierbar; als nächster enger Auftrag folgt Claude-Analyse der Smoke-Robustheit/Diagnostik.

### 2026-08-30 19:52 CEST — Enger Claude-Smoke-Auftrag

- Genau ein Claude-Code-Prozess wurde mit Sonnet und `--effort high` für die eng begrenzte Analyse von `scripts/release_smoke.py` gestartet.
- Der Claude-Dienst beendete den Auftrag vor jeder Analyse unverändert mit Exitcode 1: `You've hit your session limit · resets 12:30am (Europe/Berlin)`.
- Keine Claude-Aussage, keine Produktänderung und kein Testergebnis wurden daraus abgeleitet. Der Auftrag muss nach dem angegebenen Reset seriell wiederholt werden.

### 2026-08-30 19:53–20:31 CEST — Kompakter UI/Bridge/Queue-Arbeitsblock

Bestätigte Befunde und Änderungen:

- Audit-Ziel korrigiert: Die produktive EXE verwendet `retrodisc_launcher.py:RetroDiscApi/RetroDiscBridge`, nicht die zuvor allein verglichene Klasse in `src/ui/desktop.py`.
- Einen echten UI/API-Fehler entfernt: „Ausgewähltes auf DVD“ rief `download_url` mit einer vom produktiven Proxy nicht unterstützten Fünf-Argument-Signatur auf und besaß keinen belastbaren Download-zu-DVD-Workflow. Toter Button/Handler wurden entfernt statt Funktionalität vorzutäuschen.
- Nicht wirksame DVD-Menü-Template-API und zugehörige tote UI-Verkabelung entfernt; DVD-Authoring/ISO selbst bleibt unverändert produktiv.
- Pipeline-Race behoben: Dynamische Handler werden jetzt pro Job gespeichert, damit mehrere gleichartige wartende Jobs nicht durch die jeweils neueste Closure überschrieben werden.
- Cancel/Shutdown gehärtet: Laufende native Prozesse und zugehörige Async-Tasks werden beendet; wartende Jobs werden beim Shutdown abgebrochen; Handler-/Task-Registrierungen werden bereinigt.
- UI-Cancel zeigt einen Job nur nach bestätigtem Backend-Abbruch als `cancelled`; Fehler bleiben sichtbar. „Queue leeren“ wurde korrekt zu „Erledigte entfernen“ eingegrenzt und lässt wartende/laufende Jobs stehen.
- Settings werden partiell tief zusammengeführt, ohne versteckte Werte zurückzusetzen, gespeichert und sofort auf aktive FFmpeg-/FFprobe-/yt-dlp-/Disc-/Verzeichnis-/Concurrency-Abhängigkeiten angewandt. DVD-Standard und Whisper-Modell werden mit den produktiven Workflow-Feldern synchronisiert.
- Doppelte Fertig-Sound-Auslösung und irreführende globale Burn-Animation entfernt; Burn-Animation läuft nur noch für Jobs vom Typ `burn_dvd`. Irreführende UI-Texte zu ISO-Kopie und Watch-Folder-Brennen wurden präzisiert.

Neue Regressionstests decken ab:

- getrennte Handler für mehrere Jobs desselben Typs,
- Abbruch eines laufenden Jobs mit echtem Kindprozess,
- Shutdown mit laufendem und wartendem Job,
- partielles Settings-Merge und sofortige Runtime-Anwendung,
- Abwesenheit der entfernten Fake-/Totpfade.

Verifikation nach diesen Änderungen:

- `pytest -q`: **64 passed in 7.40s**, Exitcode 0.
- `compileall`: Exitcode 0.
- Aktuelles aus `src/ui/app.html` extrahiertes JavaScript: `node --check` Exitcode 0. Ein direkter `node --check app.html`-Versuch war erwartungsgemäß ungeeignet (`ERR_UNKNOWN_FILE_EXTENSION`) und ist kein Produktfehler.
- `.hermes/verify_core.py`: Exitcode 0; echter gebündelter FFmpeg-Konvertierungsjob `done`, 100 %, MP3 403477 Bytes; Pipeline sauber gestoppt.
- `scripts/release_smoke.py` wurde in diesem Block nicht erneut verändert oder ausgeführt; die zwei unmittelbar zuvor dokumentierten vollständigen Läufe bleiben beide grün.

Claude-Serialisierung:

- `.audit_tmp/run_claude_after_reset.sh` ist verbindlich auf `--model sonnet --effort high` gesetzt; kein Opus/max für den engen Smoke-Review.
- Genau ein frisch aus der korrigierten Datei gestarteter lokaler Runner ist aktiv (`proc_ff343e6736ce`); der ältere wartende Shell-Prozess wurde beendet, damit garantiert keine bereits eingelesene Opus/max-Konfiguration weiterläuft. Der aktive Runner schläft bis 00:31 CEST und startet erst danach einen Claude-Prozess.
- Der zusätzlich vorhandene alte Claude-Opus-Cronjob wurde nach vorherigem `list` entfernt; anschließender `list`-Stand: 0 Cronjobs. Frühere Claude-Prozesse sind beendet, nicht laufend.

### 2026-08-31 18:06–18:15 CEST — Reproduzierter Whisper-Dependency-Blocker geschlossen

Eindeutige Klassifikation:

- **A — Release-Dependency fehlt im Projekt**, mit direkter Packaging-Auswirkung.
- Nicht nur lokale `.venv`: `requirements.txt` und die kanonische `build.py:RUNTIME_DEPS` enthielten `requests` nicht.
- Kein FFmpeg-/Vendor-Problem: Der Fehler entstand erst beim Python-Import von `faster_whisper` nach erfolgreich erzeugtem `highlights.mp4`.
- `faster-whisper 1.2.0` importiert `requests` in `faster_whisper.utils`, deklariert es in den installierten `Requires-Dist`-Metadaten jedoch nicht. Eine saubere Neuinstallation nach den bisherigen RetroDisc-Definitionen konnte daher denselben Defekt erzeugen.

Kleinster belastbarer Fix:

- `requests>=2.31.0` explizit in `requirements.txt` aufgenommen.
- `requests` in die kanonischen Runtime-Installations- und Import-Gates von `build.py` aufgenommen.
- `requests` explizit als PyInstaller-Hidden-Import in `retrodisc_final.spec` aufgenommen.
- `scripts/release_smoke.py` und `.hermes/verify_core.py` können ihren Repository-Root beim dokumentierten direkten Skriptaufruf selbst auflösen.
- Regressionstest `test_whisper_runtime_dependency_is_declared_packaged_and_importable` prüft Deklaration, Buildliste, Spec und reale Imports von `requests`/`faster_whisper`.

Verifikation auf dem aktuellen Source:

- `pytest -q`: **65 passed in 8.80s**, Exitcode 0.
- `compileall`: Exitcode 0.
- `.hermes/verify_core.py`: Exitcode 0; echter MP3-Job `done`, 100 %, 403477 Bytes; Pipeline sauber gestoppt.
- Aktuelles Inline-JavaScript aus `src/ui/app.html`: Syntaxcheck erfolgreich.
- Produktiver UI→`RetroDiscApi`→`RetroDiscBridge`-Check: 47 JavaScript-Aufrufe, 39 Proxy-Methoden, 41 Bridge-Methoden; 0 fehlende Proxy-Methoden, 0 fehlende Bridge-Ziele, 0 Signaturfehler.
- `scripts/release_smoke.py`: Exitcode 0; Trim A/B, Merge, 2x-Upscale, 50-fps-Interpolation, Highlights, Faster-Whisper-SRT mit 2 deutschen Segmenten und DVD-ISO vollständig erfolgreich.
- Smoke-Ausgabe: `build/e2e-smoke-20260831-181318`; ISO-Größe 2627584 Bytes; SRT 199 Bytes; geprobte Medienwerte entsprechen den vorherigen erfolgreichen Läufen.
- Ein einzelner Claude Sonnet/high Read-only-Review: **PASS**, kein Blocker; keine Produktdateien geändert.
- Windows Application Control blockierte den direkten Start der Projekt-`.venv` und des dort gefundenen `uv.exe`; die Gates wurden deshalb ohne Policy-Umgehung mit der freigegebenen Python-3.11-Runtime und exakt den Projekt-Site-Packages ausgeführt.

### 2026-08-31 18:16–18:25 CEST — Restlicher Source-Audit und unabhängige QA geschlossen

- Enger Diff-Audit fand einen verbleibenden realen Race-Pfad: `convert_file`, `download_url` und der Watch-Folder registrierten trotz des neuen Pipeline-Mechanismus weiterhin Handler global pro Jobtyp.
- Kleinster Fix: alle drei produktiven Pfade übergeben ihre Closure jetzt direkt als `handler=` beim jeweiligen Job-Submit; Convert und Download verwenden die gemeinsame `_submit_job`-Hilfe.
- Neuer Bridge-Regressionstest beweist distinkte Handler für Convert/Download und prüft den Watch-Folder-Submit.
- Vollständige Gate-Wiederholung auf dem finalen Source: `pytest -q` **66 passed in 8.74s**, `compileall` Exitcode 0, `.hermes/verify_core.py` Exitcode 0, UI-JavaScript/API-Check ohne Fehler.
- Finaler Real-Media-Smoke `build/e2e-smoke-20260831-182105`: Exitcode 0; Trim, Merge, Upscale, Interpolation, Highlights, deutsche Faster-Whisper-SRT und DVD-ISO vollständig erfolgreich.
- Unabhängige QA durch einen einzelnen, read-only Claude-Sonnet/high-Auftrag: **PASS, keine Release-Blocker**. Eine mögliche längere Shutdown-Dauer bei mehreren gleichzeitig hängenden nativen Prozessen wurde als nicht blockierende Härtungsoption dokumentiert; aktuelle Cancel-/Shutdown-Regressionen sind grün.

Nächster Gate: Source Freeze erstellen, danach ausschließlich aus diesem Commit frische Release-Artefakte bauen und testen.
