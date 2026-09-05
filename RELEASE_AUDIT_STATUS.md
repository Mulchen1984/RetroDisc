# RetroDisc Release-Audit-Status

Letzte Aktualisierung: 2026-09-05 — charmap-Blocker behoben, automatisierter Packaged-Acceptance-Harness gruen

## Verbindlicher Abschlussstatus

**NOT RELEASE READY — softwareseitig abgeschlossen und erstmals an der gepackten EXE belegt; die Weitergabe an Dritte bleibt durch die fehlende Signatur blockiert.**

Der Arbeitsbaum nach `86098fe` wurde am 2026-09-05 als `01e5fd9` eingefroren; darauf liefen alle Source-Gates, ein Clean-Build, das Artefakt-Gate und der Runtime-Gate gruen. **Ein anschliessender manueller Acceptance-Test hat diesen Stand dann widerlegt:** ein vollstaendig heruntergeladener und korrekt veroeffentlichter YouTube-Download (rund 273 MB) wurde in der Oberflaeche als FAILED angezeigt, mit `'charmap' codec can't encode character ... : character maps to <undefined>`. Kein Gate hatte das gefunden - die automatisierten Laeufe schreiben auf einen UTF-8-faehigen Kanal, die gebaute Anwendung unter Windows nicht. Der Fehler ist behoben; die Bestaetigung am gebauten Artefakt steht noch aus. Die historischen Belege zu `1c486cc` gelten weiterhin nur fuer jenen alten Stand und seine Hashes.

Aktueller Nutzerauftrag: zuerst Windows abschliessen. macOS-Unterstuetzung ist wieder gewuenscht, aber auf spaeter verschoben; sie ist derzeit nicht verifiziert. Ein physischer DVD-Brenn-/Ruecklesetest und eine vertrauenswuerdige Signatur bleiben verpflichtende offene Release-Gates. Am 2026-09-05 wurden beide physischen Laufwerke erneut ohne Medium gemeldet; als Code-Signing-Zertifikat ist nur das abgelaufene Selftest-Zertifikat vorhanden.

Begründung: Auf dem Freeze-Stand `1c486cc` sind alle automatisierbaren Gates grün und real belegt — Source-Gates (193 Tests), vollständiger Real-Media-Smoke, UI/Bridge-Vergleich, Artefakt-Gate, Installation, **Start aus der Installation**, Deinstallation, Laufwerkserkennung, `default_device`, Disc-Erkennung, Rip-Workflow und YouTube-Download. Der Runtime-Gate auf den finalen Artefakten ist bestanden, ohne ein einziges CodeIntegrity-Ereignis.

Der Releaseblocker ist unverändert und ausschließlich extern: Die Artefakte sind **nicht signiert**, auf dem Host existiert kein vertrauenswürdiges Code-Signing-Zertifikat. Ohne Signatur ist keine verlässliche Weitergabe an Dritte möglich — Smart App Control entscheidet je Datei, ein hier bestandener Start sagt nichts über einen fremden Rechner. Für die Weitergabe fehlt daher genau ein Schritt: Zertifikat bereitstellen, `python build.py --clean --sign` ausführen und die Gates auf den dann entstehenden signierten Hashes wiederholen.

Zusätzlich offen als **ausstehende Hardware-Validierung** (kein Softwaremangel, kein Blocker für den Codestand): der reale physische Brennvorgang auf einen Rohling samt Rückleseprobe. Es stand kein Medium zur Verfügung; alles softwareseitig Prüfbare ist über ein virtuell eingebundenes DVD-Abbild belegt.

## Aktueller Checkpoint

- Branch: `main`
- Letzter Freeze-Commit: `01e5fd9` (`RELEASE: isolate download publication, temp files and DVD tool paths`)
- Vorheriger Freeze-Commit: `1c486cc` (`DOCS: state the Windows-only scope and the real build path`)
- Tag des Abschlussstands: `v1.0.0-rc1`
- Baseline-Commit: `e29f41d` (`BASELINE: preserve initial RetroDisc source state`)
- Aktueller Arbeitsbaum: sauber; alle Build-Ausgaben sind ignoriert
- Plattform: **Windows-only** (Entscheidung vom 2026-09-03, siehe Journal)
- Baseline-Manifest: `BASELINE_SHA256_MANIFEST.json`
- Manifestumfang: 147 Einträge, 679158086 Bytes, Stand `e29f41d`
- Live-Verifikation gegen Manifest: 0 fehlende Einträge; 20 Einträge weichen ab. Das ist erwartet und kein Defekt: Es sind genau die Dateien, die seit `e29f41d` in den dokumentierten Arbeitsblöcken bewusst geändert wurden. Das Manifest ist der historische Ausgangsbeleg, kein Gate für den jeweils aktuellen Commit.
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

### 2026-08-31 18:26–18:51 CEST — Erster Freeze-Build invalidiert, Splash-Race geschlossen

- Der zunächst bei Commit `f706f7b` eingefrorene Source bestand erneut alle Gates und wurde mit `build.py --clean` zu EXE, Portable-ZIP und Installer gebaut.
- Die neue `dist/RetroDisc.exe` startete als eigenständiger Prozess, veröffentlichte das antwortende Fenster `RetroDisc 1.0` und entpackte die gebündelten Runtime-Dateien. Gebündelte FFmpeg-/FFprobe-/yt-dlp-Binaries starteten; FFmpeg erzeugte und konvertierte ein reales H.264/AAC-Testvideo, das FFprobe korrekt als 320×180/H.264/AAC validierte.
- Der separate Start derselben EXE aus dem frisch entpackten Portable-ZIP reproduzierte jedoch bei jedem Start einen unbehandelten `webview.errors.JavascriptException`-Traceback im Fehlerkanal. Dieser Build und seine drei Artefakte wurden damit als Releasebeleg verworfen.
- Exakte Ursache: `RetroDiscBridge.splash_complete()` ersetzte das Splash-Dokument synchron über `load_html`, bevor pywebview den JavaScript-Promise der Bridge-Methode beantworten konnte. Nach der Navigation existierte der registrierte `splash_complete`-Callback im alten Dokument nicht mehr.
- Kleinster Fix: Der Dokumentwechsel wird einmalig über einen daemonisierten 50-ms-Timer geplant. Die API-Methode antwortet damit vor der Navigation; doppelte Übergänge werden durch `_splash_transition_started` verhindert, Ladefehler werden geloggt.
- Neuer Regressionstest `test_splash_transition_returns_before_replacing_the_document` beweist, dass vor der Bridge-Antwort kein `load_html` ausgeführt wird, dass der Timer daemonisiert ist und dass ein zweiter Aufruf keine zweite Navigation plant.
- Vollständige Source-Gates nach dem Fix: `pytest -q` **67 passed in 8.61s**, `compileall` Exitcode 0, `.hermes/verify_core.py` Exitcode 0 mit realem MP3-Job, Inline-JavaScript-Syntax grün, produktiver UI/API-Vergleich mit 47 Aufrufen und 0 fehlenden Zielen/Signaturfehlern.
- Vollständiger Real-Media-Smoke `build/e2e-smoke-20260831-184856`: Exitcode 0; Trim, Merge, Upscale, Interpolation, Highlights, deutsche Faster-Whisper-SRT und DVD-ISO erfolgreich.
- Ein einzelner enger, read-only Claude-Sonnet/high-Review des Splash-Fixes und Regressionstests: **PASS, kein Release-Blocker**. Keine Parallelaufträge und keine Claude-Änderungen.

Nächster Gate: neuen Source Freeze aus dem Splash-Fix erstellen; anschließend alle drei Artefakte erneut sauber bauen und ausschließlich den neuen Build testen.

### 2026-09-01 05:05–05:36 CEST — Doppel-Disc-UI, YouTube-Evidenz und unsichtbare Windows-Hilfsprozesse

- Das Konvertieren-Symbol zeigt jetzt zwei vollständige, innerhalb des 92×80-SVG liegende und nicht überlappende Disc-Rohlinge. Ein Geometrie-Regressionstest verhindert erneutes Abschneiden oder Überlappen.
- Der gemeldete YouTube-Fehler war mit der historischen yt-dlp-Test-ID reproduzierbar, weil dieses konkrete Video nicht mehr verfügbar ist. Der gebündelte yt-dlp-Simulationslauf mit `jNQXAC9IVRw` sowie ein realer Download durch `src.core.downloader.Downloader` waren erfolgreich; die UI-/Bridge-Signatur ist korrekt. Ein URL-/Fehlertext des konkreten fehlgeschlagenen Nutzerdownloads liegt nicht vor, daher wurde keine unbelegte Spezialursache behauptet.
- Sämtliche produktiven FFmpeg-, FFprobe-, yt-dlp-, DVD-, Upscale- und PowerShell-Hilfsprozesse laufen auf Windows nun zentral mit `CREATE_NO_WINDOW`. Sichtbare Benutzeraktionen zum Öffnen von Explorer/Finder/Dateien bleiben unverändert sichtbar.
- Zentraler Wrapper: `src/utils/subprocesses.py`; synchrone und asynchrone Aufrufe erhalten den Flag nur auf Windows und bewahren vorhandene `creationflags` per bitweisem OR.
- Der vollständige Produkt-Scan enthält außerhalb dieses Wrappers keinen direkten `subprocess.run`- oder `asyncio.create_subprocess_exec`-Aufruf. Der Regressionstest verbietet zusätzlich neue direkte `subprocess.call`/`check_call`/`check_output`, `asyncio.create_subprocess_shell` und nicht explizit freigegebene `Popen`-Aufrufe.
- Ein erster unabhängiger Claude-Code-Sonnet/high-Review fand einen realen Randfehler in `retrodisc_portable.py`: `subprocess.TimeoutExpired` war nach dem Umbau ohne gebundenen Modulnamen. Der Modulimport wurde ergänzt und ein echter Timeout-Degradierungstest hinzugefügt.
- Der anschließende Claude-Code-Sonnet/high-Re-Review bewertet den korrigierten Produktfix mit **PASS**; keine verbleibenden Release-Blocker.
- Fokussierte Tests nach Härtung: **20 passed**. Die offene Hermes-Sitzung ergänzte anschließend `tests/test_subprocess_hardening.py`; der zusätzliche Lauf bestand **26/26** und deckt insbesondere sichtbare Explorer/Finder-Benutzeraktionen sowie beide PowerShell-Timeoutpfade ab.
- Vollständige aktuelle Suite nach Übernahme dieses späten Tests: `pytest -q` **100 passed in 9.45s**. Die übrigen Gates bleiben grün: `compileall` Exitcode 0; `.hermes/verify_core.py` Exitcode 0 mit realem MP3-Job; aktuelles Inline-JavaScript syntaktisch gültig; UI/API-Signaturtest grün.
- Vollständiger Real-Media-Smoke `build/e2e-smoke-20260901-053407`: Exitcode 0; Trim A/B, Merge, 2×-Upscale, 50-fps-Interpolation, Highlights, deutsche Faster-Whisper-SRT mit zwei Segmenten und DVD-ISO vollständig erfolgreich. ISO-Größe 2627584 Bytes, SRT 199 Bytes.
- Damit bleibt die ursprüngliche Dependency-Klassifikation bestätigt: **A — fehlende Release-Dependency `requests`**, nicht nur lokale `.venv` und kein Vendor-/FFmpeg-Problem. Der aktuelle Whisper-Import und reale SRT-Workflow sind grün.

Nächster Gate: neuen Source-Freeze aus diesem vollständig verifizierten Stand erstellen; danach EXE, Portable-ZIP und Installer sauber neu bauen und ausschließlich diese neuen Artefakte testen.

### 2026-09-01 14:20–14:47 CEST — Reale Artefakt-QA und letzter Installer-Blocker

- Source-Freeze `6bd0e38` wurde sauber gebaut. Erste frische Artefakte: EXE SHA-256 `52CA7750E89D24A67894DFAE6584DB740C66EEE1F66C20DDBC9AD11A5489B9D5`, Portable-ZIP `911367B1EFE17D39917780B7EB7B7CE3044BE7A3D2ADEE5ABFE7CE12FC6D13B5`, Installer `AD6B06F7B5EDEE812A03C11913A862FBD9787B7DD1B91E68D4BD4CC7805DF865`.
- Portable-ZIP vollständig gelesen und separat entpackt; enthaltene EXE ist byteidentisch zur `dist`-EXE. Start, Hauptfenster `RetroDisc 1.0`, pywebview-API und Fehlerkanal (0 Bytes) sind grün.
- Echte Artefakt-Runtime: gebündelte FFmpeg-/FFprobe-/yt-dlp-Versionen gestartet; reales MP4 erzeugt, MP3 konvertiert und geprobt; yt-dlp-Simulation und echter öffentlicher YouTube-Download (`jNQXAC9IVRw`, 498491 Bytes) erfolgreich.
- Produkt-Progress und Cancel real geprüft: Fortschrittsereignisse vorhanden, laufender nativer Prozess wurde abgebrochen, Endzustand `cancelled`, keine Restdatei. Während Konvertierung, Download, Brennererkennung und Cancel entstanden **0 neue sichtbare Konsolenfenster**.
- Trump-Startbild aus dem tatsächlichen Bundle erschien **2,402 Sekunden** und damit im gewünschten 2–3-Sekunden-Fenster. Screenshots: `C:\Users\marco\Pictures\Screenshots\RetroDisc-splash-6bd0e38-visual-agent.png` und `C:\Users\marco\Pictures\Screenshots\RetroDisc-main-6bd0e38-visual-agent.png`.
- Visuelle QA: keine abgeschnittenen/überlappenden Elemente, kein Overflow; beide Disc-Rohlinge vollständig mit 4,82 px sichtbarem Abstand. Alle vier Hauptaktionen und sechs Zusatzaktionen wurden real angeklickt und öffneten die richtigen Ansichten; 0 deaktiviert, 0 offscreen, stderr 0.
- Reale Installation in einen isolierten QA-Pfad: installierte EXE ist byteidentisch zur `dist`-EXE und startete mit Hauptfenster `RetroDisc 1.0`.
- Reproduzierter letzter Blocker: Der gebündelte Uninstaller entfernte zwar Dateien, endete aber mit Exitcode 32 und ließ den leeren Installationsordner zurück. Ursache war der synchrone Selbstlösch-/CWD-Trick im noch laufenden Batchprozess.
- Kleinster Fix: Nach Shortcut-Bereinigung und Benutzermeldung wechselt der Elternprozess nach `%TEMP%`, startet einen versteckten PowerShell-Helper, der mit `-LiteralPath` begrenzt wiederholt löscht, und beendet sich mit Exitcode 0. Ein echter isolierter Windows-Test mit Leerzeichen und `&` im Zielpfad beweist die vollständige Selbstlöschung.
- Die von Hermes ergänzte Authenticode-Pipeline signiert bei vorhandener PFX-/Thumbprint-Konfiguration zuerst die App-EXE, anschließend ZIP/Installer und verifiziert den Status. `--sign` bricht ohne Zertifikat hart ab; ein normaler Build warnt ausdrücklich vor unsignierten Artefakten. Passwort bleibt ausschließlich in der Prozessumgebung.
- Fokussierte Installer-/Signiergates: **23 passed**. Vollständige Suite nach dem Fix: **123 passed in 11.46s**.
- Enger Claude-Code-Sonnet/high-Review von Uninstaller-Quoting, asynchroner Selbstlöschung und Signierintegration: **PASS**, kein Codeblocker.
- Externer Distributionsblocker: `Get-AuthenticodeSignature` meldet für App und Installer `NotSigned`; auf dem Host sind weder Signierumgebungsvariablen noch ein Code-Signing-Zertifikat vorhanden. Windows Application Control blockiert die identische Portable-EXE aus `%TEMP%`, während sie aus dem freigegebenen Projektpfad vollständig funktioniert.

Nächster Gate: korrigierten Installer-/Signierstand einfrieren, final neu bauen, reale Install-/Deinstallations-QA wiederholen und danach Status ausschließlich anhand der neuen Hashes setzen. Eine öffentliche `RELEASE READY`-Freigabe bleibt ohne vertrauenswürdige Signatur ausgeschlossen.

### 2026-09-01 14:48–15:03 CEST — Finaler Build und Enterprise-Signaturblocker

- Finaler Source-Freeze: `80b4f3ccfc231880ff0745025e0b5b06c06177a4` (`RELEASE: harden uninstall and signing pipeline`). Arbeitsbaum abgesehen von der bewusst nicht versionierten, veralteten `AGENTS.md` sauber.
- Finaler Clean-Build aus diesem Commit erfolgreich. Die Signierpipeline meldete erwartungsgemäß ausdrücklich, dass kein Zertifikat konfiguriert ist und App/Installer unsigniert bleiben.
- Finale Artefakte:
  - `dist/RetroDisc.exe`: 538339903 Bytes, SHA-256 `3422A2CD953097FAAA3F10A944B3CB81DAB5C985C352BA66D2F32DC6C72206B9`.
  - `Output/RetroDisc_1.0.0_Portable.zip`: 535968928 Bytes, SHA-256 `D61DE5758ABA263CD7CCAEE1B876BB0AB62CF56E03E92C903FFDC8376743D342`.
  - `Output/RetroDisc_Setup_1.0.0.exe`: 544376190 Bytes, SHA-256 `89ED6F21D56D20ABB531B353D7DC2D9912C814C31861AEF0DB248572D95B48EC`.
- ZIP-Integrität PASS: enthaltene EXE ist byteidentisch zur finalen `dist`-EXE; README und START_WINDOWS vorhanden.
- Reale finale Installer-/Uninstaller-QA PASS: Installation in isolierten Zielpfad, installierte EXE byteidentisch; isolierte Desktop-/Startmenü-Links erstellt; Uninstaller-Elternprozess Exitcode 0 und stderr leer; Installationsordner nach 1535 ms vollständig entfernt; alle isolierten Links entfernt.
- Der finale direkte Runtime-Gate ist BLOCK: Sowohl `dist/RetroDisc.exe` als auch die identische ZIP-EXE werden ohne Prozessstart durch die lokale Windows-Anwendungssteuerung abgewiesen. Der Versuch in einem separaten normalen `%LOCALAPPDATA%\Programs\RetroDisc-Portable-QA-80b4f3c`-Pfad ändert das Ergebnis nicht.
- Read-only CodeIntegrity-Evidenz: Event 3033 meldet für die exakte finale EXE, dass sie das erforderliche Enterprise-Signaturniveau nicht erfüllt; Event 3077 meldet einen Verstoß gegen Policy-ID `{0283ac0f-fff1-49ae-ada1-8a933130cad6}`. `Get-AuthenticodeSignature` bestätigt `NotSigned`; kein `Zone.Identifier` und `Unblock-File` ändert die Richtlinienentscheidung nicht.
- Auch für die installierte finale Kopie existieren entsprechende 3033/3077-Ereignisse. Eine zwischenzeitliche Fensterbeobachtung wird deshalb nicht als belastbarer finaler Startbeleg gewertet.
- Die zuvor erfolgreichen Runtime-, YouTube-, Cancel-, Konsolenfenster- und visuellen Tests gelten für den unmittelbar vorherigen App-Source-gleichen Zwischenbuild, nicht als Beleg für den blockierten finalen Hash. Die alten Screenshots bleiben als Designbeleg erhalten, werden aber nicht als finaler Runtime-Gate ausgegeben.
- Kein Prozess der finalen EXE läuft; keine Policy, ACL, Signatur oder Systemeinstellung wurde umgangen oder verändert.

Verbleibender externer Gate: öffentlich/enterprise-vertrauenswürdiges Code-Signing-Zertifikat bereitstellen (oder ausdrückliche Administrator-Whitelist), `python build.py --clean --sign` ausführen und genau die neu signierten Hashes erneut durch EXE-, Portable-, Installations-, visuellen und realen Medien-Runtime-Gate führen. Bis dahin bleibt der verbindliche Status **NOT RELEASE READY**.

### 2026-09-01 15:40–15:55 CEST — Startblocker präzise identifiziert und Encoding-Härtung

Startblocker: exakte Ursache statt "Windows Application Control"

- Read-only ausgelesen: `HKLM\SYSTEM\CurrentControlSet\Control\CI\Policy` meldet `VerifiedAndReputablePolicyState = 1`. Die blockierende Policy-ID `{0283ac0f-fff1-49ae-ada1-8a933130cad6}` liegt als `{0283AC0F-FFF1-49AE-ADA1-8A933130CAD6}.cip` unter `C:\Windows\System32\CodeIntegrity\CiPolicies\Active`.
- Damit ist der Blocker konkret **Smart App Control im erzwingenden Zustand**, nicht eine per Gruppenrichtlinie ausgerollte Enterprise-WDAC-Policy. `Win32_DeviceGuard` bestätigt User-Mode-Code-Integrity-Enforcement (Status 2).
- Praktische Folge für die Freigabe: Smart App Control lässt unsignierte Artefakte ohne Reputation grundsätzlich nicht starten. Ein Abschalten ist auf Windows eine Einbahnstraße (nur per Windows-Neuinstallation reversibel) und wurde deshalb **nicht** vorgenommen; es wurde keine Policy, ACL oder Einstellung verändert.
- Der Status bleibt daher unverändert **NOT RELEASE READY**; die Entscheidung zwischen vertrauenswürdigem Zertifikat, ausdrücklicher Freigabe und Test auf einem Rechner ohne Smart App Control liegt beim Betreiber.

Realer Produktdefekt gefunden und geschlossen: cp1252-Dekodierung der Windows-Subprozessausgabe

- Beim vollständigen Testlauf fiel eine `PytestUnhandledThreadExceptionWarning` auf: `UnicodeDecodeError: 'charmap' codec can't decode byte 0x81` im `_readerthread` von `subprocess`.
- Ursache: Windows-CLI-Prozesse schreiben in die OEM-Konsolencodepage (cp850 auf diesem System, 0x81 = "ü"), `text=True` dekodiert jedoch mit der ANSI-Locale-Codepage cp1252, in der 0x81 undefiniert ist. Der Reader-Thread stirbt, `stdout`/`stderr` kommen leer zurück.
- Betroffen war produktiv die Brenner-Erkennung: `retrodisc_launcher.py:detect_burners` und `retrodisc_portable.py:detect_burners` lasen ihre PowerShell-Ausgabe mit `text=True` ohne explizites Encoding. Sobald PowerShell einen Umlaut ausgibt — Laufwerksname oder deutsche Fehlermeldung — lieferte die Erkennung leere Ausgabe statt Laufwerken.
- Real reproduziert und gegenübergestellt: Eine PowerShell-Ausgabe mit "ü" ergibt auf dem alten Pfad `''` samt Reader-Thread-Traceback, auf dem neuen Pfad korrekt `U+00FC`.
- Kleinster Fix: `src/utils/subprocesses.py` erhält `decode_console_output()` (versucht utf-8, cp850, cp1252, zuletzt `errors="replace"`; wirft nie) und `run_powershell_hidden()` (erzwingt `[Console]::OutputEncoding=UTF8`, liest Bytes, dekodiert lenient, reicht `TimeoutExpired` unverändert durch). Beide `detect_burners` nutzen jetzt diesen Helfer.
- Zusätzlich gehärtet: acht strikte `.decode()`-Aufrufe auf Werkzeugausgabe in `src/core/disc.py`, `src/core/downloader.py`, `src/core/ffmpeg.py` und `src/services/upscaler.py` dekodieren jetzt mit `errors="replace"`. Auf Fehlerpfaden hätte ein `UnicodeDecodeError` sonst die echte dvdauthor-/FFprobe-/Merge-Fehlermeldung ersetzt.

Wirkungslose Zusicherung im Installer-Test korrigiert

- `tests/test_installer.py` las die Ausgabe des realen Uninstallers ebenfalls mit `text=True`. Genau dieser Test löste die Warnung aus: Die deutschen cmd-Meldungen zerlegten den Reader-Thread, `proc.stdout`/`proc.stderr` blieben leer.
- Die bisher dokumentierte Aussage "Uninstaller-Elternprozess Exitcode 0 und stderr leer" stützte sich damit auf eine Erfassung, die selbst abgestürzt war, und die Fehlerdiagnose des Tests wäre im Fehlerfall leer geblieben.
- Der Test liest jetzt Bytes, dekodiert über `decode_console_output()` und prüft die leere stderr-Ausgabe ausdrücklich per Assertion. Die Aussage ist damit erstmals wirklich abgesichert und grün.

Neue Regressionstests

- `decode_console_output()` für cp850-/utf-8-Umlaute, `None`, bereits dekodierten Text und kaputte Bytes.
- `run_powershell_hidden()`: kein `text=`, `capture_output`, Timeout-Durchreichung, `CREATE_NO_WINDOW`, erzwungenes UTF-8 im Kommando, korrekt dekodierte cp850-Ausgabe.
- Statisch: beide Launcher-`detect_burners` ohne `text=True` und mit dem neuen Helfer; keine nackten `.decode()` mehr in den Hintergrundmodulen.

Verifikation auf diesem Stand

- `pytest -q`: **135 passed in 9.99s**, Exitcode 0 (vorher 123; die Warnung aus dem Reader-Thread ist verschwunden).
- `compileall` über `src`, beide Launcher und `tests`: Exitcode 0.
- `.hermes/verify_core.py`: Exitcode 0; echter FFmpeg-Job `done`, 100 %, MP3 403477 Bytes, Pipeline sauber gestoppt.
- Produktiver UI→`RetroDiscApi`→`RetroDiscBridge`-Vergleich: 39 Proxy-Methoden, 41 Bridge-Methoden, 0 fehlende Proxys, 0 fehlende Bridge-Ziele, 0 Arity-Mismatches.
- Aktuelles Inline-JavaScript aus `src/ui/app.html`: `node --check` Exitcode 0.
- Vollständiger Real-Media-Smoke `build/e2e-smoke-20260901-154558`: Exitcode 0; Trim A/B, Merge, 2×-Upscale, 50-fps-Interpolation, Highlights, deutsche Faster-Whisper-SRT (199 Bytes, 2 Segmente) und DVD-ISO (2627584 Bytes) — Werte identisch zu den vorherigen grünen Läufen.
- Echte Laufwerksabfrage über den neuen Helfer liefert auf diesem Rechner weiterhin beide optischen Laufwerke (`hp DVD A DH16ACSHR` / `E:`, `PIONEER BD-RW BDR-209M` / `D:`).

Folge für die Artefakte

- Die am 2026-09-01 14:48–15:03 gebauten Artefakt-Hashes gelten **nicht** mehr für diesen Source. EXE, Portable-ZIP und Installer müssen nach dem nächsten Freeze neu gebaut werden.

Nächster Gate: diesen Stand einfrieren, danach ausschließlich aus dem neuen Commit bauen. Der Runtime-Gate auf diesem Rechner bleibt bis zu einer Entscheidung über Smart App Control bzw. ein vertrauenswürdiges Zertifikat blockiert.

### 2026-09-01 16:00–16:45 CEST — Neuer Build, bestandener Runtime-Gate und Korrektur des Startblockers

Freeze und Build

- Source-Freeze: `a9b5853` (`RELEASE: decode Windows subprocess output safely`), Arbeitsbaum bis auf die weiterhin nicht versionierte `AGENTS.md` sauber.
- Clean-Build aus diesem Commit mit `python build.py --clean`, Exitcode 0. Die Signierpipeline meldete erwartungsgemäß, dass kein Zertifikat konfiguriert ist.
- Neue Artefakte:
  - `dist/RetroDisc.exe`: 537273841 Bytes, SHA-256 `F08E8325FFE12653F66878A0BC332C72B7B52F9A0A86408600C6C7183117C87E`.
  - `Output/RetroDisc_1.0.0_Portable.zip`: 534905178 Bytes, SHA-256 `FFF312D87439088FE27BCD4309CA33EB6115024FE841092629F3E840AEB56471`.
  - `Output/RetroDisc_Setup_1.0.0.exe`: 542283016 Bytes, SHA-256 `2FAF67BD54AC82054E41C91B32D3D1BF429D173180F590199F027E75177BF6BD`.
- `Get-AuthenticodeSignature` meldet für App und Installer weiterhin `NotSigned`.
- ZIP-Integrität PASS: Inhalt sind genau `RetroDisc/RetroDisc.exe`, `README.md` und `START_WINDOWS.txt`; die enthaltene EXE ist byteidentisch zur `dist`-EXE.

Startblocker: frühere Bewertung korrigiert

- Der Startversuch der **neuen** `dist/RetroDisc.exe` war erfolgreich: Prozess läuft, keine CodeIntegrity-Ereignisse 3033/3077.
- Gegenprobe auf demselben System, im selben Zustand: Die **alte** EXE des Vorgängerbuilds (`80b4f3c`, SHA-256 `3422A2CD…`, noch unter `%LOCALAPPDATA%\Programs\RetroDisc-Portable-QA-80b4f3c` vorhanden) wird weiterhin abgewiesen — `Eine Anwendungssteuerungsrichtlinie hat diese Datei blockiert`, begleitet von frischen Events 3033 und 3077.
- Eine zwischenzeitlich erwogene Erklärung wurde ausdrücklich **widerlegt**: Es liegt nicht am startenden Elternprozess. Der Start aus derselben Codex-Runtime-`pwsh.exe`, die in den alten Ereignissen als ladender Prozess auftaucht, gelingt mit der neuen EXE ebenfalls ohne Ereignis. Beide PowerShell-Binaries sind gültig signiert.
- Smart App Control ist unverändert erzwingend aktiv (`VerifiedAndReputablePolicyState = 1`). Die Entscheidung fällt also **je Datei**, nicht pauschal. Warum genau der alte Hash abgewiesen und der neue zugelassen wird, ist aus read-only-Evidenz nicht bestimmbar; hier wird bewusst keine Ursache behauptet.
- Praktische Folge: Der bestandene Start ist ein echter Beleg für genau diese Bytes auf genau diesem Rechner. Er ist **keine** Zusage für andere Rechner oder künftige Builds — verlässlich wird das erst mit einer vertrauenswürdigen Signatur.
- Es wurde keine Policy, ACL, Signatur oder Systemeinstellung verändert oder umgangen.

Runtime-Gate auf den neuen Artefakten

- Kaltstart bis Hauptfenster `RetroDisc 1.0`: 13,4 s; Folgestart 14,9 s. Die Zeit geht auf das Entpacken des 512-MB-Onefile-Bundles.
- Oberfläche real gerendert und per Screenshot belegt: Kopfzeile `RetroDisc 1.0 — All-in-One Media Suite`, Menü Datei/Extras/Hilfe, die vier Hauptaktionen Konvertieren/Brennen/Rippen/Download mit korrekt gezeichnetem Doppel-Disc-Symbol sowie die Zusatzaktionen Suche, Bearbeiten, AI Tools, Bibliothek, Job Queue, Einstellungen. Screenshot: `C:\Users\marco\Pictures\Screenshots\RetroDisc-main-a9b5853.png`.
- Während Start und Betrieb entstanden **0 zusätzliche Konsolen-/Shell-Prozesse** (Zählung vorher/nachher identisch).
- Gebündelte Werkzeuge aus dem entpackten Bundle real ausgeführt: FFmpeg und FFprobe `N-125048-gcd199a7d69-20260615`, yt-dlp `2026.07.04`.
- Echte Medienarbeit aus dem Artefakt: MP3-Konvertierung des Testvideos ergab 403477 Bytes, von FFprobe als `mp3` mit 320000 bit/s bestätigt — identisch zum Source-Ergebnis.
- Echter YouTube-Download mit **genau den produktiven Formatmustern** von `src/core/downloader.py`: `bestvideo[height<=480]+bestaudio/best[height<=480]` lieferte 474481 Bytes; `bestaudio/best` mit MP3-Extraktion lieferte 762285 Bytes.

Beobachtung zu YouTube-Format 18

- Das progressive Kombiformat 18 liefert derzeit reproduzierbar `HTTP Error 403: Forbidden` — bei mehreren Videos und unabhängig vom Zielpfad.
- RetroDisc ist davon **nicht** betroffen: Alle produktiven Formatmuster fordern getrennte Video-/Audiostreams (`bestvideo…+bestaudio/…`) beziehungsweise `bestaudio/best` an, und genau diese Pfade sind wie oben belegt grün.
- Das ist damit kein Produktdefekt, sondern eine YouTube-/Formatbeobachtung. Sie wird notiert, weil eine frühere Nutzermeldung „YouTube-Download geht nicht" in dieselbe Richtung zeigte; ein konkreter Fehlerfall des Nutzers liegt weiterhin nicht vor.

Installation und Deinstallation auf den neuen Bytes

- Stille Installation in den isolierten Pfad `%LOCALAPPDATA%\Programs\RetroDisc-QA-a9b5853`: Exitcode 0, stderr leer, installierte EXE byteidentisch zur `dist`-EXE.
- Deinstallation über den mitgelieferten `Uninstall RetroDisc.cmd`: Exitcode 0, stderr leer, Installationsordner vollständig entfernt, keine Reste.

Ausdrücklich nicht abgedeckt in diesem Block

- Kein erneuter vollständiger Klickdurchlauf durch die Oberfläche. `src/ui/app.html`, `src/ui/splash.html` und `assets/` sind seit dem visuell geprüften Build `6bd0e38` unverändert; belegt ist hier der reale Start samt gerenderter Hauptansicht.
- Keine physischen Brenn- oder Rip-Tests; die bleiben hardware- und medienabhängig und separat auszuweisen.
- Keine Signatur, damit keine Aussage über das Verhalten auf fremden Rechnern mit aktivem Smart App Control.

Verbleibender Gate: Code-Signing-Zertifikat bereitstellen und `python build.py --clean --sign` ausführen; die dann entstehenden signierten Hashes erneut durch Start-, Installations- und Medien-Gate führen. Für einen zusätzlichen unabhängigen Lauffähigkeitsbeleg steht `RUNTIME_GATE_ZWEITRECHNER.md` bereit.

### 2026-09-03 22:50–00:30 CEST — Undokumentierten Arbeitsblock auditiert, drei reale Fehler behoben, Abschluss

#### Ausgangslage

Der Arbeitsbaum enthielt einen **nie committeten und nie dokumentierten Arbeitsblock vom 2026-09-02/03**: 20 geänderte Dateien mit 1257 Einfügungen und 538 Löschungen sowie sieben neue Testdateien mit 833 Zeilen. Das Statusdokument endete zu diesem Zeitpunkt am 2026-09-01 16:45. Kein Commit, kein Kommentar und keine Notiz erklärte diesen Block. Er wurde deshalb zuerst vollständig auditiert, dann nachgebessert, dann eingefroren — nicht ungeprüft übernommen.

#### Inhalt des Arbeitsblocks (auditiert)

- `prepare_vendor.py` ist erstmals ein versionierter, hash-geprüfter Erzeuger des `vendor/`-Baums: FFmpeg, yt-dlp, die DVD-Werkzeuge aus einer still installierten DVDStyler-Version und das Faster-Whisper-Basismodell sind auf feste Versionen und SHA-256 gepinnt; `_replace_files`/`_replace_directory` ersetzen transaktional mit Rücksicherung. `retrodisc_final.spec` verlangte `vendor/dvdtools` und `vendor/whisper-base` bereits seit `f706f7b`, ohne dass ein versioniertes Skript sie erzeugte — diese Lücke ist damit geschlossen.
- `src/utils/subprocesses.py`: `iter_stream_records` (CR-/LF-begrenztes Lesen statt `readline` mit 64-KB-Grenze und verlorenem CR-Fortschritt), `terminate_process` (Windows-Prozessbaum über `taskkill /T` ohne Konsolenfenster) und `communicate_with_job` (speicherbegrenztes Draining, das den Abbruchweg offen lässt). `ffmpeg.py`, `downloader.py` und `upscaler.py` nutzen diese Helfer.
- Atomare Ausgaben: `staging_output_path`/`commit_staged_output` schreiben in eine eindeutige Nachbardatei und benennen erst nach Erfolg um; ein Abbruch hinterlässt damit keine abgeschnittene Zieldatei mehr. `settings.save` nutzt dasselbe Muster, `settings.load` fällt bei defekter Datei auf die Vorgaben zurück statt den Start abzubrechen.
- Beobachterisolierung in `models/media.py`, `core/pipeline.py` und `RetroDiscBridge._emit`: ein Fehler im Callback bricht den Backendjob nicht mehr ab.
- `app.html`: `escAttr` escaped jetzt HTML-Entities, und die betroffenen Aufrufstellen übergeben Werte über `data-`-Attribute statt in einen Inline-JS-String. Das schließt einen echten Attributausbruch über Anführungszeichen in Suchergebnis-Titeln und Bibliotheksnamen.
- `library.search` tokenisiert und quotet die FTS5-Anfrage, statt Benutzereingabe direkt als MATCH-Ausdruck zu übergeben.
- `tools/codesign.py` schreibt das temporäre PS1-Skript als `utf-8-sig` und liest die Ausgabe als Bytes; `build.yml` baut über `build.py`, erzwingt auf Tags die Signaturgeheimnisse und fährt die Source-Gates erstmals in CI.

#### Im Audit widerlegte Verdachtsmomente

Zwei Auffälligkeiten wurden geprüft und **nicht** als Fehler bestätigt; sie sind hier festgehalten, damit sie nicht erneut untersucht werden:

- Die Umstellung der Logaufrufe in `src/bootstrap.py` und `retrodisc_launcher.py` auf `%s`-Positionsargumente ist unbedenklich: structlog 26.1.0 interpoliert sie. Real geprüft — `log.info("Tool fehlt: %s", "ffmpeg.exe")` ergibt `Tool fehlt: ffmpeg.exe`.
- Das unbedingte `staging_path.unlink(missing_ok=True)` in den `finally`-Blöcken von `ffmpeg.py` ist nach erfolgreichem Commit wirkungslos, weil die Quelldatei durch das Umbenennen bereits verschwunden ist.

#### Nachbesserungen an den mitgelieferten Tests

Der Block brachte 45 neue Tests mit. Vier Stellen trugen weniger, als sie versprachen:

- `test_ui_escaping` prüfte `escAttr` nur per Substringvergleich auf dem Quelltext. Eine umsortierte `replace`-Kette hätte jede geprüfte Zeichenkette bestehen lassen und trotzdem doppelt kodiert. Der Test führt das ausgelieferte `escAttr` jetzt mit Node aus und vergleicht echte Ausgaben. Negativkontrolle real gefahren: mit `&` zuletzt liefert `<` das doppelt kodierte `&amp;lt;` statt `&lt;` — der neue Test fällt darauf, der alte nicht.
- `test_codesign` übersprang den Nicht-ASCII-Rundlauf nur nach Plattform, verlangte im Skript aber PowerShell 5.1 und wäre auf einem Windows ohne 5.1 **hart fehlgeschlagen statt zu skippen**. Die Hauptversion wird jetzt vorab ermittelt.
- `test_subprocess_hardening`: die im Block entfernte Zusicherung, dass die Launcher kein eigenes `create_hidden_subprocess` definieren, ist wieder da. Sie galt weiterhin (0 Vorkommen), war aber ersatzlos gestrichen.
- `test_settings` prüfte die UTF-8-Datei mit einem wirkungslosen `decode()`-Aufruf ohne Zusicherung; jetzt mit echter Prüfung.

#### Gates erstmals reproduzierbar gemacht

Zwei Gates liefen bisher ad hoc und ließen sich aus dem Repository nicht wiederholen — der UI/Bridge-Vergleich stammte aus einem `.audit_tmp/compare.py`, das nicht mehr existiert. Beide sind jetzt committete Skripte, die bei jedem Befund mit Exitcode 1 enden:

- `scripts/verify_ui_bridge.py` — extrahiert das Inline-JavaScript nach `build/ui-audit/inline.js`, sammelt die tatsächlichen Brückenaufrufe samt Argumentzahl und prüft gegen den produktiven Einstieg `retrodisc_launcher.py`.
- `scripts/verify_release_artifacts.py` — hasht die drei Artefakte, prüft die ZIP-Integrität gegen die `dist`-EXE, liest den Authenticode-Status und fährt Installation und Deinstallation real in einer Sandbox mit umgelenktem `USERPROFILE`, `APPDATA` und `LOCALAPPDATA`.
- `scripts/verify_disc_workflow.py` — neu, siehe Disc-Abschnitt weiter unten.

#### Drei reale Fehler gefunden und behoben

**1. YouTube-Download war kaputt.** Der Pin `yt-dlp 2026.07.04` lieferte für **die produktiven Formatmuster** reproduzierbar `HTTP Error 403: Forbidden` — nicht nur für das progressive Format 18, wie am 2026-09-01 noch angenommen. Damit war die Download-Funktion des Produkts unbrauchbar. Mit `2026.08.19` lädt dieselbe URL mit demselben Muster fehlerfrei. Pin angehoben (SHA-256 `66674953…`) und real über den produktiven `Downloader` nachgeprüft: Video 480p ergab 36260966 Bytes, die MP3-Extraktion 26388823 Bytes.

**2. `get_disc_info` meldete ein Medium in einem Laufwerk, das es nicht gibt.** `present` folgte aus der *Abwesenheit* dreier englischer Fehlermuster. Auf diesem deutschen Windows meldet `dvd+rw-mediainfo` für einen nicht vorhandenen Buchstaben aber `Z:: unable to open: Ein oder mehrere Argumente sind ungültig.` — RetroDisc behauptete daraufhin ein eingelegtes Medium. Jetzt zählt ausschließlich ein Positivbeleg (`Mounted Media`, `Disc status` oder `READ CAPACITY`).

**3. `get_disc_info` übersah ein lesbares Medium.** Für ein virtuell eingebundenes DVD-Abbild meldet dasselbe Werkzeug `unable to TEST UNIT READY`; die Erkennung gab „kein Medium" zurück, obwohl `VIDEO_TS` lesbar war und das Rippen funktionierte. Neu entscheidet unter Windows ein Dateisystem-Fallback (`_windows_volume_info`): lesbares Wurzelverzeichnis heißt Medium vorhanden, mit Typ aus `VIDEO_TS`/`BDMV`, Label über `GetVolumeInformationW`, Kapazität über `disk_usage`. Ein wirklich leeres Laufwerk fällt korrekt auf `present=False` zurück, ein lesbares aber leeres Volume gilt als Rohling.

**Nebenbefund im selben Pfad:** Die Profil-Regex verlangte Anführungszeichen (`Mounted Media: "…"`). `dvd+rw-mediainfo` schreibt das Profil unquotiert hinter den Hex-Code, die Regex konnte also nie greifen — `profile`, `type` und `rewritable` blieben für **jede** echte Disc leer. Beide Schreibweisen werden jetzt akzeptiert. Das ist mangels Rohling **nicht** an einer echten Disc geprüft und bleibt ausdrücklich Teil des offenen Hardware-Tests.

Alle drei Fehler sind in `tests/test_disc_detection.py` und den erweiterten Downloadpfaden als Regression abgedeckt.

#### Plattformentscheidung: Windows-only

Der Arbeitsblock hatte den gesamten macOS-Zweig aus `.github/workflows/build.yml` ersatzlos gestrichen (Job `build-macos` für macos-14/macos-13, DMG-Erstellung, beide Release-Artefakte, die macOS-Zeilen der Release-Notes) — ohne jede Begründung. **Marco hat die Streichung am 2026-09-03 ausdrücklich als bewusst bestätigt.** Begründung: die CI baut über `build.py` („Build RetroDisc for Windows"), `prepare_vendor.py` vendort den Windows-DVDStyler-Installer, und der gesamte Release-Audit einschließlich Signatur, Installer und Runtime-Gate ist Windows-only; ein DMG wäre ein an keinem Gate belegtes Artefakt.

Die Dokumentation wurde entsprechend korrigiert: README nennt RetroDisc jetzt ausdrücklich ein Windows-Produkt und benennt die verbliebenen macOS-Reste als nicht unterstützt; `CLAUDE.md` ersetzt eine **aktiv falsche** Bauanweisung (sie baute aus `retrodisc_portable.py` statt aus `retrodisc_final.spec`, nannte das ersetzte `openai-whisper` und bündelte weder DVD-Werkzeuge noch Whisper-Modell); `AGENTS.md` ist erstmals versioniert und verweist auf `CLAUDE.md`, statt unversioniert und veraltet im Baum zu liegen; `FUER_QWEN.md` trägt einen Veraltet-Hinweis. Die CI-Release-Notes waren bereits Windows-only und blieben unverändert.

#### Disc-Gate ohne Rohling

Ein physischer Rohling stand nicht zur Verfügung. `scripts/verify_disc_workflow.py` fährt deshalb alles, was ohne Medium prüfbar ist, gegen ein **real erzeugtes und als virtuelles Laufwerk eingebundenes** DVD-Abbild. Ergebnis **PASS**:

- Gebündelte Werkzeuge: `dvdauthor`, `mkisofs`, `growisofs`, `dvd+rw-mediainfo` vorhanden.
- Echte DVD-Erstellung über den produktiven `DVDWorkflow`: `RetroDisc_Disc_Gate.iso`, 2627584 Bytes.
- Einbinden als virtuelles Laufwerk `H:`; die produktive Laufwerkserkennung meldet es als `Microsoft virtuelles DVD-ROM-Laufwerk` mit `MediaLoaded=True`, die beiden physischen Laufwerke (`hp DVD A DH16ACSHR` / `E:`, `PIONEER BD-RW BDR-209M` / `D:`) bleiben sichtbar.
- `BurnSettings().default_device` = `D:`.
- Disc-Erkennung auf `H:`: `present=True`, `type=DVD-Video`, `label='RETRODISC_DISC_GATE'`, `readable=True`.
- Rip-Workflow vom virtuellen Laufwerk: nach ISO 2627584 Bytes, nach MKV/H.265 332249 Bytes; die gerippte Datei wurde per FFprobe als abspielbar bestätigt (720x576, 10,04 s).
- Brennaufruf als Dry-Run mit realistischen Parametern: `growisofs.exe -dvd-compat -Z D:=<ISO> -speed 8` — der Befehl wurde geprüft, aber **nicht** ausgeführt.
- Fehlerfälle: fehlendes Laufwerk `Z:` → `present=False` ohne Ausnahme; leeres Laufwerk `E:` → `present=False` ohne Ausnahme; eingebundenes Medium korrekt als nicht beschreibbar klassifiziert; Brennen mit fehlender ISO wird sauber als `DiscError` abgewiesen.

Ausdrücklich **nicht** abgedeckt: der reale physische Brennvorgang auf einen Rohling und die Rückleseprobe davon. `cdrecord` wird bewusst nicht gebündelt — die Oberfläche bietet kein CD-Brennen an, der Pfad ist nur über `burn_iso(disc_type=DiscType.CD)` erreichbar.

#### Freeze-Commits

- `04f1084` — `RELEASE: pin vendor downloads, harden process I/O and UI escaping`
- `bac7a34` — `AUDIT: make the UI/bridge and artifact gates reproducible`
- `160c0fc` — `FIX: correct optical media detection and refresh the yt-dlp pin`
- `1c486cc` — `DOCS: state the Windows-only scope and the real build path`

Arbeitsbaum danach vollständig sauber; `dist/`, `Output/`, `build/`, `vendor/` und alle Caches sind ignoriert und gelangen nicht ins Repository.

#### Source-Gates auf dem Freeze-Stand

- `pytest -q`: **193 passed in 10,58 s**, Exitcode 0 (vorher 135 am 2026-09-01).
- `compileall` über `src`, `tests`, `scripts`, beide Launcher und `prepare_vendor.py`: Exitcode 0.
- `.hermes/verify_core.py`: Exitcode 0; echter FFmpeg-Job `done`, 100 %, MP3 403477 Bytes — wertidentisch zu allen vorherigen grünen Läufen.
- `scripts/verify_ui_bridge.py`: **PASS, 0 Befunde** — 47 Aufrufstellen, 36 verschiedene UI-Methoden, 39 Proxy-Methoden, 41 Bridge-Methoden, keine fehlenden Proxys, keine fehlenden Bridge-Ziele, keine Arity-Mismatches.
- `node --check` auf dem extrahierten Inline-JavaScript (Node v22.22.3): Exitcode 0.
- `scripts/release_smoke.py`: Exitcode 0, Ausgabe `build/e2e-smoke-20260903-231139`. Alle acht Artefakte erzeugt und geprüft: Merge 20,72 s bei 1280x720/25 fps, Upscale 2560x1440, Interpolation 1280x720/50 fps, Highlights 6,013968 s, deutsche Faster-Whisper-SRT 199 Bytes, DVD-ISO 2627584 Bytes — wertidentisch zu den vorherigen grünen Läufen.
- Echte Laufwerksabfrage über den produktiven Helfer: beide optischen Laufwerke werden gemeldet.

#### Finaler Build aus `1c486cc`

`python build.py --clean`, Exitcode 0. Die Signierpipeline meldete erwartungsgemäß, dass kein Zertifikat konfiguriert ist. `prepare_vendor.py` holte die gepinnte Vendor-Runtime neu und verifizierte jede Datei per SHA-256; FFmpeg ist jetzt der Autobuild `N-126342-gf88b741dbf-20260831`, yt-dlp `2026.08.19`. Innerhalb des Builds liefen die Tests erneut vollständig grün.

Finale Artefakte:

- `dist/RetroDisc.exe`: **502901640 Bytes**, SHA-256 `F02096E77C78C307F97F16219B35FCBF8CA35DC94A3F3465A58B4D6A59AE2883`
- `Output/RetroDisc_1.0.0_Portable.zip`: **501463750 Bytes**, SHA-256 `B3B73C7621DE8BF33E83CADC871D5220534752D889632BFB4B11BB95D645B20D`
- `Output/RetroDisc_Setup_1.0.0.exe`: **508841013 Bytes**, SHA-256 `EACD6D2E0CAD91E4FFD55AAA1F6C23CF999416705E6DC03F9C8EE6A53961132D`

Die Artefakte stammen aus dem Baum von `1c486cc`. Der nachfolgende Commit dieses Journalblocks ändert ausschließlich `RELEASE_AUDIT_STATUS.md`, und diese Datei ist nicht Teil eines Artefakts — die Hashes bleiben damit gültig.

#### Artefakt-Gate auf den finalen Bytes

`scripts/verify_release_artifacts.py`: **PASS, 0 Befunde**.

- ZIP-Integrität: enthalten sind genau `RetroDisc/RetroDisc.exe`, `RetroDisc/README.md` und `RetroDisc/START_WINDOWS.txt`; die enthaltene EXE ist byteidentisch zur `dist`-EXE.
- `Get-AuthenticodeSignature` meldet für App und Installer weiterhin `NotSigned`.
- Stille Installation in eine vollständig isolierte Sandbox (umgelenktes `USERPROFILE`, `APPDATA`, `LOCALAPPDATA`): Exitcode 0, stderr leer, installierte EXE byteidentisch, isolierte Desktop- und Startmenü-Verknüpfungen angelegt.
- Deinstallation: Exitcode 0, stderr leer, Installationsordner vollständig entfernt, beide isolierten Verknüpfungen weg.

#### Runtime-Gate auf den finalen Bytes

Zusätzlich zur Sandbox real gegen eine echte Installation gefahren:

- Stille Installation nach `%LOCALAPPDATA%\Programs\RetroDisc-QA-1c486cc`: Exitcode 0; installierte EXE SHA-256 `F02096E7…`, byteidentisch zur `dist`-EXE.
- **Start aus der Installation heraus**: Hauptfenster `RetroDisc 1.0` nach 36,5 s (Kaltstart einschließlich Entpacken des rund 480-MB-Onefile-Bundles). **0 neue CodeIntegrity-Ereignisse 3033/3077** — Smart App Control weist diesen Hash nicht ab.
- Deinstallation über den mitgelieferten `Uninstall RetroDisc.cmd`: Exitcode 0, stderr leer, Installationsordner entfernt, Desktop- und Startmenüeintrag entfernt.
- Ein separater Start der portablen `dist/RetroDisc.exe` (Vorgängerbuild `bac7a34`, SHA-256 `E9A086EF…`) wurde ebenfalls belegt: sichtbares Fenster `RetroDisc 1.0`, keine CodeIntegrity-Ereignisse; Screenshot `C:\Users\marco\Pictures\Screenshots\RetroDisc-main-bac7a34.png`.

Wie schon am 2026-09-01 festgehalten: Smart App Control entscheidet **je Datei**. Ein bestandener Start belegt genau diese Bytes auf genau diesem Rechner und ist keine Zusage für andere Rechner oder künftige Builds.

Am Rande beobachtet und nicht als Produktfehler gewertet: Beim Lauf des Installers in der Sandbox erschienen zwei CodeIntegrity-Ereignisse (3033/3077) für `_bz2.pyd` aus dem entpackten Installer-Bundle. Die Installation lief trotzdem vollständig und korrekt durch — das Modul ist für den Installer nicht erforderlich. Die App-EXE selbst erzeugte in keinem Lauf ein Ereignis.

#### YouTube-Download real geprüft

Über den produktiven `Downloader` mit genau den Formatmustern aus `src/core/downloader.py`:

- `bestvideo[height<=480]+bestaudio/best[height<=480]` → 36260966 Bytes (MKV)
- `bestaudio/best` mit MP3-Extraktion → 26388823 Bytes

Mit dem vorherigen Pin schlugen **beide** Muster mit `HTTP Error 403: Forbidden` fehl. Die frühere Notiz vom 2026-09-01, wonach nur das progressive Format 18 betroffen sei und die produktiven Pfade grün seien, ist damit für den heutigen Stand von YouTube überholt.

## Abschlussstatus dieses Durchlaufs

**Softwareseitig abgeschlossen. Weitergabe an Dritte weiterhin blockiert.**

Grün und belegt: alle Source-Gates, der vollständige Real-Media-Smoke, das UI/Bridge-Gate, das Artefakt-Gate, Installation, Start aus der Installation, Deinstallation, Laufwerkserkennung, `default_device`, Disc-Erkennung, der Rip-Workflow und der YouTube-Download.

Offen bleiben genau zwei Punkte, beide extern und keiner davon durch Code lösbar:

1. **Signaturblocker (unverändert der eigentliche Releaseblocker).** Die Artefakte sind unsigniert; auf dem Host existiert kein vertrauenswürdiges Code-Signing-Zertifikat. Im Zertifikatspeicher liegt lediglich ein abgelaufenes, selbstsigniertes `CN=RetroDisc Pipeline Selftest DO NOT TRUST` (Thumbprint `C439F45F…`, `NotAfter` 2026-09-02, `UntrustedRoot`) aus einem Pipelinetest — als Signaturzertifikat unbrauchbar, und ein selbst ausgestelltes Zertifikat löst das Problem bei Smart App Control ohnehin nicht. Erforderlich ist ein öffentlich vertrauenswürdiges Zertifikat, danach `python build.py --clean --sign` und ein erneuter Durchlauf der Gates auf den dann entstehenden signierten Hashes.
2. **Physischer Brenn- und Rip-Test — ausstehende Hardware-Validierung.** Es stand kein Rohling zur Verfügung. Alles softwareseitig Prüfbare ist über ein virtuell eingebundenes DVD-Abbild belegt (siehe Disc-Gate oben); der reale Brennvorgang auf ein Medium und die Rückleseprobe davon sind nicht ersetzbar und bleiben offen. Ebenfalls offen: die Auswertung des Medienprofils an einer echten Disc, nachdem die zugehörige Regex korrigiert wurde.

Für einen zusätzlichen unabhängigen Lauffähigkeitsbeleg auf fremder Hardware steht weiterhin `RUNTIME_GATE_ZWEITRECHNER.md` bereit.


---

### 2026-09-05 14:39–15:05 CEST — Windows-Abschlusskette auf dem Freeze `01e5fd9`

Auftrag: Windows vollstaendig release-fertig abschliessen, macOS ausdruecklich nicht bearbeiten, nur bestaetigte Releaseblocker anfassen, keine kosmetischen Aenderungen, kein breiter Neu-Audit.

Drei zunaechst gestartete unabhaengige QA-Agenten wurden auf Nutzerwunsch beendet, bevor sie Befunde erzeugt hatten. Sie haben keine Datei veraendert und liefern **keinen** Auditbeleg. Die Verifikation erfolgte stattdessen direkt gegen Code und Regressionstests.

#### Die fuenf bestaetigten Restpunkte — Beleglage

1. **Automatisch erkannte DVD-Toolpfade landen nicht dauerhaft in den Einstellungen.** `RetroDiscBridge._resolve_disc_tool_paths()` loest die gebuendelten Werkzeuge pro Lauf auf, migriert alte gespeicherte PyInstaller-Extraktionspfade (`_MEIxxxx`) auf den blossen Kommandonamen und laesst eigene Benutzerpfade unangetastet. Abgedeckt von `test_save_settings_reapplies_current_bundle_without_persisting_paths`, `test_legacy_extraction_paths_resolve_to_current_bundle`, `test_custom_disc_paths_survive_initialization_save_reload_and_runtime_updates` und `test_missing_bundled_disc_tools_keep_default_commands`.
2. **Namenskollisionen trennen Video und Untertitel nicht mehr.** `Downloader._claim_target_group()` reserviert Hauptdatei und Begleitdateien als Gruppe mit demselben Kollisionszaehler, exklusiv per `O_CREAT|O_EXCL`. Abgedeckt von `test_collision_renames_the_whole_media_and_sidecar_group` und `test_playlist_sidecars_follow_their_own_longest_matching_media_stem`.
3. **Eine fehlgeschlagene Veroeffentlichung laesst keine halbfertigen Ergebnisse zurueck.** Jeder Download arbeitet in einem privaten `mkdtemp()`-Verzeichnis; bricht das Verschieben ab, entfernt `_remove_claimed_targets()` alle von diesem Aufruf beanspruchten Ziele. Abgedeckt von `test_move_failure_rolls_back_all_files_owned_by_this_call` und `test_reservation_failure_releases_current_and_previous_groups`.
4. **Die CI verdeckt keine Fehlercodes mehr.** Nach jedem Source-Gate in `.github/workflows/build.yml` steht ein `$LASTEXITCODE`-Riegel; Tag-Releases sind bei fehlender gueltiger Signatur und fehlenden Artefakten fail-closed (`fail_on_unmatched_files: true`). Abgedeckt von `test_workflow_stops_at_each_failed_source_gate` und `test_workflow_tag_release_is_fail_closed_on_signature_and_artifacts`. `build.py` gab Fehlercodes bereits korrekt weiter (`check=True`, `raise SystemExit(main())`) und wurde nicht angefasst.
5. **Vollstaendiger realistischer Windows-Medien-Smoke** — Exitcode 0, siehe unten.

Gezielter Lauf dieser drei Testdateien: **74 passed in 5,64 s**, Exitcode 0.

#### Source-Gates auf `01e5fd9`

Jeder Exitcode wurde einzeln geprueft, nicht nur die Ausgabe gelesen.

- `pytest -q`: **263 passed in 16,27 s**, Exitcode 0 (vorher 193 auf `1c486cc`). Buildinterner Wiederholungslauf: **263 passed in 15,43 s**.
- `compileall` ueber `src`, `tests`, `scripts`, `installer`, `tools`, `build.py`, beide Launcher und `prepare_vendor.py`: Exitcode 0.
- `.hermes/verify_core.py`: Exitcode 0; echter FFmpeg-Job `done`, 100 %, MP3 **402328 Bytes**. **Abweichung bewusst festgehalten:** bis `1c486cc` waren es 403477 Bytes. Ursache ist der neu gepinnte FFmpeg-Autobuild, kein Produktdefekt; die frueher benutzte Formulierung "wertidentisch" gilt fuer diesen Wert nicht mehr.
- `scripts/verify_ui_bridge.py`: **PASS, 0 Befunde** — 47 Aufrufstellen, 36 verschiedene UI-Methoden, 39 Proxy-Methoden, 41 Bridge-Methoden.
- `node --check build/ui-audit/inline.js` (Node v22.22.3): Exitcode 0.
- `scripts/release_smoke.py`: Exitcode 0, Ausgabe `build/e2e-smoke-20260905-144434`. Merge 20,72 s, Upscale 2560x1440, Interpolation 1280x720/50 fps, Highlights 6,013968 s, deutsche Faster-Whisper-SRT 199 Bytes, DVD-ISO 2627584 Bytes.
- `git diff --check`: Exitcode 0.

`.gitignore` wurde um `RetroDisc_Data/` und `.claude/settings.local.json` ergaenzt. Real geprueft: beide Pfade waren zuvor **nicht** getrackt, und `git check-ignore` bestaetigt, dass `RELEASE_NOTES_1.0.0.md` und `tests/test_download_publish.py` **nicht** ignoriert werden.

#### Build, Artefakt-Gate und Runtime-Gate auf `01e5fd9`

`python build.py --clean`, Exitcode 0. `prepare_vendor.py` meldete alle vier gepinnten Vendor-Baeume als bereits bereit. Damit ist real belegt, dass der neue `_marker_metadata_matches()`-Guard den Whisper-Baum **nicht** faelschlich als veraltet verwirft und keine Neu-Download-Schleife ausloest.

- `dist/RetroDisc.exe`: **502905831 Bytes**, SHA-256 `CDE62A311E06C0B11862C686A267EAC2C461FF6535CAADB95FBDF05972D6D752`
- `Output/RetroDisc_1.0.0_Portable.zip`: **501468103 Bytes**, SHA-256 `CEE984780993963155EB4B8D6AD44FD2EED796677FE53A8F952B45516B5AEBBF`
- `Output/RetroDisc_Setup_1.0.0.exe`: **508844345 Bytes**, SHA-256 `F3D2A59C1043F728FF02E2F59734E35334E38A693E32AB512EBE4EC2B9509EA1`

`scripts/verify_release_artifacts.py`: **PASS, 0 Befunde**, Exitcode 0 — ZIP-Inhalt byteidentisch zur `dist`-EXE, `NotSigned` als Hinweis, stille Installation und Deinstallation in einer isolierten Sandbox mit umgelenktem `USERPROFILE`/`APPDATA`/`LOCALAPPDATA` vollstaendig durchgelaufen.

Runtime-Gate: Hauptfenster `RetroDisc 1.0` nach 10,2 s, **0 CodeIntegrity-Ereignisse 3033/3077**. **Messmethodik festgehalten**, weil ein erster Versuch daran scheiterte: Bei einem PyInstaller-Onefile besitzt der *Kindprozess* das Fenster; `MainWindowTitle` am gestarteten Bootloader bleibt dauerhaft leer und meldete faelschlich "kein Fenster nach 120 s". Gemessen werden muss ueber `Get-Process -Name RetroDisc | Where-Object { $_.MainWindowTitle }`. Die 10,2 s sind ein **Warmstart** und nicht mit den 36,5 s Kaltstart aus dem `1c486cc`-Lauf vergleichbar.

---

### 2026-09-05 15:00–15:10 CEST — charmap-Releaseblocker aus dem manuellen Acceptance-Test

**Dieser Block widerlegt den vorstehenden Abschluss.** Alle Gates auf `01e5fd9` waren gruen; ein manueller Acceptance-Test am gebauten Produkt fand trotzdem einen echten, reproduzierbaren Windows-Releaseblocker.

#### Befund

Ein YouTube-Download erreichte 100 %, die Datei lag korrekt und vollstaendig unter `C:\Users\marco\Downloads\RetroDisc\` (rund 273 MB) — die Oberflaeche zeigte den Job trotzdem rot, mit `'charmap' codec can't encode character ... : character maps to <undefined>` in der Statusleiste.

#### Ursache, real reproduziert

1. Windows gibt einem Prozess Standardstroeme mit der ANSI-Codepage (cp1252, `charmap`).
2. `retrodisc_launcher.py` konfigurierte **structlog gar nicht**. structlog benutzte damit seine Default-`PrintLoggerFactory`, die genau auf diesen cp1252-Strom schreibt. Zusaetzlich haengte `logging.basicConfig` einen `StreamHandler(sys.stdout)` ohne Encoding daneben — die Logdatei war mit `encoding="utf-8"` geschuetzt, der Konsolenkanal nicht.
3. `Downloader.download()` rief `log.info("Download abgeschlossen", path=str(final_path))` **innerhalb** seines `try` auf.
4. Ein Emoji im YouTube-Titel steht im Dateinamen. Das blosse Loggen dieses Namens warf `UnicodeEncodeError`; der umschliessende `except BaseException: raise` machte daraus einen gescheiterten Job — obwohl die Datei laengst korrekt veroeffentlicht war.

Isoliert nachgestellt: `structlog` auf einen `cp1252`/`strict`-Strom gebunden, `log.info(..., path="… \U0001F600 …")` → `UnicodeEncodeError: 'charmap' codec can't encode characters`.

**Warum kein Gate das gefunden hat:** pytest, Smoke und `verify_core` laufen alle auf einem UTF-8-faehigen Kanal. Der Defekt existiert nur dort, wo das Produkt tatsaechlich lebt — als gebaute Anwendung unter Windows mit cp1252-Stroemen. Das ist die Luecke, die der geplante Acceptance-Harness schliessen soll.

#### Fix

Wurzel zuerst, in `src/utils/logging_setup.py` (neu, bewusst klein: keine Formatter, keine Handler, keine Level):

- `make_stream_utf8_safe()` stellt einen Strom auf UTF-8 mit `errors="replace"` um. `None` bleibt `None` (PyInstaller-Windowed-Build ohne Standardstroeme); fuer Stroeme ohne `reconfigure` gibt es den `buffer`-Fallback ueber einen neuen `TextIOWrapper`.
- `configure_console_encoding()` wendet das auf `sys.stdout` und `sys.stderr` an.
- `configure_structlog()` bindet structlog explizit an diesen sicheren Strom, statt sich auf die Default-Factory zu verlassen; das Rendering bleibt unveraendert. Ohne Konsole faellt es auf `open_null_stream()` zurueck.

`retrodisc_launcher.py` ruft beides auf, **bevor** `logging.basicConfig` die Stroeme einsammelt, und uebergibt den gesicherten Strom an den `StreamHandler`.

`src/core/downloader.py` bekommt zusaetzlich einen bewusst **engen** Riegel: Der Erfolgs-Log steht jetzt ausserhalb des `try` und faengt ausschliesslich `UnicodeEncodeError`. Der Vorfall wird nicht verschluckt, sondern ASCII-sicher ueber `ascii(str(final_path))` als Warnung gemeldet, damit die Meldung ueber denselben Kanal nicht erneut scheitert. Jeder andere Fehler laeuft unveraendert in den `except BaseException`-Pfad.

Wichtige Zwischenerkenntnis, die den Fix geformt hat: Den Logaufruf nur aus dem `try` herauszuziehen **reicht nicht**. Die `UnicodeEncodeError` wuerde weiterhin aus `download()` herausfliegen und den Job scheitern lassen. Traegt allein der sichere Strom plus der enge Riegel.

#### Regressionstest mit Negativkontrolle

`tests/test_windows_console_encoding.py`, 7 Tests. Der zentrale Test bindet structlog bewusst an einen `cp1252`/`strict`-Strom und faehrt einen vollstaendigen Download mit `\U0001F600` im Dateinamen durch den echten Produktpfad. Geprueft wird der fachliche Endzustand, nicht der Fortschritt: Rueckgabepfad, Datei existiert, Inhalt stimmt, Untertitel liegt beim Video, Arbeitsverzeichnis ist weg.

Ein erster Test stellt ausdruecklich sicher, dass der cp1252-Strom das Zeichen wirklich ablehnt — sonst waere der Regressionstest gruen, weil das Zeichen harmlos ist, statt weil der Fix wirkt.

**Negativkontrolle real gefahren:** Mit temporaer entferntem Riegel faellt genau dieser Test mit `UnicodeEncodeError: 'charmap' codec can't encode character '\U0001f600' in position 184: character maps to <undefined>` — also exakt der vom Nutzer gemeldeten Fehlermeldung. Mit Fix: 7 passed.

#### Gates nach dem Fix

- `pytest -q`: **270 passed in 16,10 s**, Exitcode 0.
- `compileall`: Exitcode 0.
- `scripts/verify_ui_bridge.py`: PASS, 0 Befunde, Exitcode 0.
- `node --check`: Exitcode 0.
- `scripts/release_smoke.py`: Exitcode 0, Ausgabe `build/e2e-smoke-20260905-150558`; SRT 199 Bytes, DVD-ISO 2627584 Bytes — wertidentisch zu den vorherigen gruenen Laeufen.
- `git diff --check`: Exitcode 0.
- Launcher-Import real geprueft: `sys.stdout` und `sys.stderr` melden anschliessend `utf-8` / `replace`.

#### Bekannte, bewusst nicht behobene Beobachtungen (keine Blocker)

- `Downloader._claim_unique_target` (`src/core/downloader.py`) wird von keinem Produktpfad aufgerufen, nur von `tests/test_media_process_streams.py`. Toter Produktcode, Kandidat fuer den naechsten Aufraeumdurchlauf.
- Die Arbeitsdateien im Ausgabeordner (`.retrodisc-dl-*`, `.<stem>.retrodisc-concat-*.txt`, `.<stem>.retrodisc-upscale-*`) sind unter Windows waehrend eines Laufs sichtbar, da Windows fuehrende Punkte nicht ausblendet. Sie werden im `finally` entfernt; bei hartem Prozessabbruch koennen Reste bleiben.

#### Stand

**Windows ist ausdruecklich NICHT bei 100 %.** Der Fix ist auf Source-Ebene vollstaendig belegt, aber noch **nicht am gebauten Artefakt** bestaetigt. Offen und zwingend vor jeder 100-%-Aussage:

1. Neuer Freeze, frischer Build, Artefakt- und Runtime-Gate auf den neuen Hashes.
2. **Wiederholung genau des realen Downloads mit Unicode-Titel an der gebauten EXE.** PASS nur, wenn die Datei vorhanden ist, der Job DONE/gruen zeigt und kein charmap-/UnicodeEncodeError erscheint.
3. Der automatisierte Windows-Acceptance-Harness, der genau diese Luecke dauerhaft schliesst.

Unveraendert offen bleiben die beiden bekannten externen Punkte: die fehlende vertrauenswuerdige Code-Signatur und der physische Brenn- und Rueckleseteset ohne verfuegbaren Rohling.

---

### 2026-09-05 15:10–15:20 CEST — Bestaetigung des charmap-Fixes am gebauten Artefakt

#### Neuer Freeze und Build

- Freeze: `6fc623b` — `FIX: keep a Windows console codepage from failing finished jobs`
- `python build.py --clean` aus diesem Commit: Exitcode 0.

Artefakte:

- `dist/RetroDisc.exe`: **502909660 Bytes**, SHA-256 `F7378986678F91975862B8D6DF4A2CA43DE93A0AD240E94221A264D9F9B2A4CC`
- `Output/RetroDisc_1.0.0_Portable.zip`: **501470621 Bytes**, SHA-256 `10A46060152E7B040D9EC14AA052A2905AC7B95223D2D0EAAE4221475E04D04D`
- `Output/RetroDisc_Setup_1.0.0.exe`: **508847057 Bytes**, SHA-256 `E1688E35DB51EC2C1781C737FABFD7E17AAFA0A80BAA0B462112210DF911FDCB`

#### Neues Gate: `scripts/verify_unicode_download.py`

Das Gate schliesst genau die Luecke, durch die der Blocker geschluepft ist. Es stellt `sys.stdout` und `sys.stderr` **vor** dem Import des Launchers auf `cp1252`/`strict` - also auf das ungeschuetzte Windows-Verhalten - und faehrt danach einen echten Download ueber den produktiven Bridge-Pfad (`RetroDiscBridge.download_url` → Pipeline → Job).

Es enthaelt eine eingebaute Vorbedingung: enthaelt der Titel **kein** in cp1252 undarstellbares Zeichen, endet der Lauf mit FAIL statt gruen zu sein, ohne etwas zu beweisen. Bewertet wird ausschliesslich der fachliche Endzustand.

**Ergebnis: PASS**, Exitcode 0.

- URL: `https://www.youtube.com/watch?v=9bZkp7q19f0`
- Titel: `PSY - GANGNAM STYLE(강남스타일) M/V`; undarstellbare Zeichen: `강남스타일`
- Jobstatus: **`done`**, Progress 100,0
- Ausgabedatei vorhanden, **26736119 Bytes**, Dateiname traegt die Hangul-Zeichen
- transiente Reste: keine; nicht aufgeraeumte Arbeitsverzeichnisse: keine
- kein charmap-/UnicodeEncodeError
- Dauer 11,4 s

#### Artefakt-Gate und Runtime-Gate auf den neuen Bytes

`scripts/verify_release_artifacts.py`: **PASS, 0 Befunde**, Exitcode 0. ZIP byteidentisch zur `dist`-EXE, Installation und Deinstallation in der isolierten Sandbox vollstaendig durchgelaufen, `NotSigned` als Hinweis.

Runtime-Gate auf `F7378986…`: Hauptfenster `RetroDisc 1.0` nach 10,1 s, Splash-Uebergang und Haupt-UI sauber, **0 CodeIntegrity-Ereignisse 3033/3077**. Im Anwendungslog dieses Laufs (18 Zeilen): **0** Treffer auf `charmap`, `UnicodeEncodeError`, `Traceback` oder `ERROR`.

**Messhinweis, damit spaetere Laeufe nicht falsch bewertet werden:** `%LOCALAPPDATA%\RetroDisc\logs\retrodisc.log` ist kumulativ und enthaelt alte Eintraege - unter anderem `Traceback`-Zeilen eines pywebview-Fehlers vom 2026-06-16, der laengst behoben ist. Eine Logpruefung muss auf den aktuellen Lauf eingegrenzt werden, sonst meldet sie Altlasten als Befund.

#### Relevanter Nebenbefund zum Fix

`retrodisc_final.spec` baut mit `console=False`. Die gepackte Anwendung ist damit **windowed**, und `sys.stdout` kann im gefrorenen Prozess `None` sein. Der `None`-Zweig in `logging_setup.py` ist deshalb kein Beiwerk, sondern ein produktiver Pfad; er ist von `test_make_stream_utf8_safe_tolerates_absent_streams` und `test_configure_structlog_falls_back_when_there_is_no_stream` abgedeckt.

#### Stand

Der charmap-Blocker ist behoben und auf dem gebauten Artefakt bestaetigt. **Windows ist trotzdem noch nicht als 100 % zu melden**, solange der automatisierte Windows-Acceptance-Harness fehlt: Der reale Download wurde ueber den produktiven Bridge-Pfad gefahren, aber nicht durch die Oberflaeche der gepackten EXE geklickt. Genau diese letzte Luecke soll der Harness schliessen.

Unveraendert offen: die fehlende vertrauenswuerdige Code-Signatur und der physische Brenn- und Rueckleseteset.

---

### 2026-09-05 15:20–15:40 CEST — Automatisierter Windows-Acceptance-Harness

Auftrag: minimal bauen, keine neue Testplattform, kein allgemeines Remote-Control-System, fuer die gepackte EXE hoechstens ein schmaler und ausschliesslich explizit aktivierbarer Hook. Der normale Produktbetrieb darf sich nicht aendern.

#### Warum

Am selben Tag waren alle Source-Gates auf `01e5fd9` gruen und ein manueller Test fand trotzdem einen echten Releaseblocker (charmap). Die Ursache der Audit-Luecke ist strukturell: pytest, Smoke und `verify_core` laufen auf einem UTF-8-faehigen Kanal, die gebaute Anwendung unter Windows nicht. Ein Gate, das nur den Quellstand kennt, kann diese Klasse von Fehlern nicht finden.

#### Aufbau

Die Faelle stehen **einmal** in `src/acceptance.py` und werden von zwei Ebenen benutzt - keine Duplikate:

- **source** — `scripts/run_acceptance.py --source-only` faehrt sie in diesem Prozess und stellt `sys.stdout`/`sys.stderr` vorher bewusst auf `cp1252`/`strict`, also auf das ungeschuetzte Windows-Verhalten.
- **packaged** — dieselben Faelle laufen in der gebauten `dist/RetroDisc.exe` im eigenen gefrorenen Prozess.

Der Hook im Produkt ist vier Zeilen am Anfang von `retrodisc_launcher.main()`: nur wenn `--acceptance-selftest` in `sys.argv` steht, wird der Zweig betreten und `src.acceptance` ueberhaupt importiert. Der Bericht geht als JSON und Text in eine Datei (`--report`), weil `retrodisc_final.spec` mit `console=False` baut und die EXE damit windowed ist und keinen Standardkanal hat.

`scripts/verify_unicode_download.py` ist auf einen schmalen Alias desselben Falls reduziert; die Logik existiert nur noch an einer Stelle.

#### Faelle und Ergebnisse

Bewertet wird ausschliesslich der **fachliche Endzustand**. 100 % Fortschritt allein ist nie ein Erfolg.

**source: PASS** — startup 1,97 s, settings 0,00 s, conversion 0,39 s, error_handling 0,11 s, unicode_download 9,62 s.

**packaged: PASS**, Exitcode 0, 52,9 s gesamt:

| Fall | Status | Belegte Messwerte |
| --- | --- | --- |
| startup | PASS | `frozen=True`, ffmpeg rc 0, yt-dlp rc 0, **stdout `utf-8` / `replace`** |
| settings | PASS | Wert ueber `save_settings` geschrieben, per frischem `AppSettings.load()` bestaetigt, Ausgangswert wiederhergestellt |
| conversion | PASS | echtes Video erzeugt, Job `done`, Ausgabe 82590 Bytes, FFprobe liest `mp3` |
| error_handling | PASS | ungueltige URL und fehlende Datei kontrolliert abgewiesen, App danach weiter benutzbar |
| unicode_download | PASS | Titel `PSY - GANGNAM STYLE(강남스타일) M/V`, Job `done`, 26736119 Bytes, keine transienten Reste, keine Arbeitsverzeichnisse |
| restart | PASS | zweiter Start der EXE Exitcode 0, startup erneut PASS nach 17,0 s |

Dass `stdout` **in der gepackten EXE** `utf-8`/`replace` meldet, ist der eigentliche Beleg: der charmap-Fix ist im ausgelieferten Artefakt wirksam, nicht nur im Quellstand.

#### Normaler Produktbetrieb unveraendert

- Start der gebauten EXE **ohne** Flag: Hauptfenster `RetroDisc 1.0` nach 10,1 s, 0 CodeIntegrity-Ereignisse 3033/3077.
- `test_importing_the_launcher_does_not_pull_in_the_harness` beweist in einem eigenen Prozess, dass `src.acceptance` nach dem Import des Launchers **nicht** in `sys.modules` steht.
- `test_launcher_hook_only_runs_behind_the_explicit_flag` prueft am Syntaxbaum, dass es keinen Import auf Modulebene gibt.

#### Der Harness darf nicht gruen werden, ohne etwas zu beweisen

`case_unicode_download` bricht mit FAIL ab, wenn der Titel **kein** in cp1252 undarstellbares Zeichen enthaelt. Ohne diese Vorbedingung waere der Fall gruen, ohne den Blocker zu reproduzieren. `test_unicode_case_fails_when_the_title_proves_nothing` sichert das ab. Weitere Tests decken ab, dass eine werfende Pruefung als FAIL statt als Absturz gemeldet wird und dass ein einzelner Fehlschlag das gesamte Release auf FAIL zieht.

#### Zwei Funde waehrend des Baus, beide im Testcode

- Der erste `startup`-Lauf meldete FAIL mit `ffmpeg startet nicht (rc=2880417800)`. Ursache war mein Schalter: FFmpeg kennt nur `-version` mit einem Strich, yt-dlp nur `--version`. Real nachgeprueft: `-version` → 0, `--version` → 1. Der Harness haette ein funktionierendes FFmpeg als kaputt ausgewiesen.
- `src/acceptance.py` benutzte zunaechst direktes `subprocess.run` und verletzte damit die Subprocess-Haertungsregel. Der bestehende Test `test_product_code_has_no_unwrapped_background_cli_launches` hat das gefangen; alle drei Aufrufe laufen jetzt ueber `run_hidden`, damit unter Windows kein Konsolenfenster aufblitzt.

#### Gates auf diesem Stand

- `pytest -q`: **276 passed in 16,25 s**, Exitcode 0 (vorher 270).
- `compileall`: Exitcode 0.
- `.hermes/verify_core.py`: Exitcode 0.
- `scripts/verify_ui_bridge.py`: PASS, 0 Befunde, Exitcode 0.
- `node --check`: Exitcode 0.
- `scripts/release_smoke.py`: Exitcode 0, Ausgabe `build/e2e-smoke-20260905-153446`; SRT 199 Bytes, DVD-ISO 2627584 Bytes.
- `git diff --check`: Exitcode 0.
- `scripts/verify_release_artifacts.py`: **PASS, 0 Befunde**, Exitcode 0.

#### Artefakte

Gebaut aus dem Stand dieses Blocks; die danach ergaenzte `tests/test_acceptance_harness.py` ist reiner Testcode und in keinem Artefakt enthalten, die Hashes bleiben also gueltig.

- `dist/RetroDisc.exe`: **502962945 Bytes**, SHA-256 `0F2EB78B862F8163AFC3BB3AE65EB0F844D46AEC3139F30AFC25D847A7F16F9F`
- `Output/RetroDisc_1.0.0_Portable.zip`: **501523758 Bytes**, SHA-256 `9958096327C899D810B9F5AA4C4D5CCE35212B4C2279E707606832FC61AD43A1`
- `Output/RetroDisc_Setup_1.0.0.exe`: **508900314 Bytes**, SHA-256 `6BB3BADEC368D00BA9ECEDAA3C72BB2FEC8CD4E93C7E29D08103CADEF0E14038`

#### Noch nicht automatisiert

Bewusst zurueckgestellt, bis diese Kette steht: Cancel, Collision, Whisper und der optische Teil (Laufwerkserkennung, Brennen nur bei ausdruecklicher Konfiguration). Der Collision-Fall ist auf Quellebene bereits durch `tests/test_download_publish.py` abgedeckt, fehlt aber noch als Packaged-Fall.

#### Stand

Die Packaged-Acceptance-Kette ist **PASS**. Damit ist die Luecke geschlossen, die den charmap-Blocker durchgelassen hat, und ein Download gilt erst dann als erfolgreich, wenn Jobstatus, Datei, Groesse und Restfreiheit stimmen.

Unveraendert offen und weiterhin nicht durch Code loesbar: die fehlende vertrauenswuerdige Code-Signatur (`NotSigned`, keine Weitergabe an Dritte) und der physische Brenn- und Rueckleseteset ohne verfuegbaren Rohling.


### 2026-09-05 — Disc-Copy: isolierte Images, leerer Scan-Cache und Medienwechsel

Auftrag im Worktree `RetroDisc-codex`, Branch `codex-crossplatform`, auf dem
frisch gefetchten `origin/crossplatform-2026` bei `8b4392b`. Drei bestaetigte
Review-Findings gemeinsam behoben, ohne zweite Rip-/Brennimplementierung.

- Jeder Kopierjob bekommt eine echte Job-ID und einen ISO-Namen mit dieser ID.
  Der bisherige positionale `Job(JobType.RIP_DVD, ...)`-Aufruf setzte versehentlich
  die ID statt des Typs; jetzt wird `job_type=` explizit uebergeben. Exklusive
  Dateireservierung beim Jobstart weicht auch bereits vorhandenen Dateien aus.
  Teil-Images werden bei Rip-Fehler/Abbruch entfernt, vollstaendige Images bleiben
  bei spaeterem Abbruch oder Brennfehler erhalten.
- Erfolgreiche `drives: []`-Antworten werden fuer die Sitzung gecacht. Fehler
  bleiben wiederholbar, auch nach einem fehlgeschlagenen erzwungenen Refresh.
  Verhalten wird mit dem echten UI-JavaScript unter Node geprueft.
- Bei gleichem Quell-/Ziellaufwerk wartet der Job nach dem Rippen auf eine
  ausdrueckliche Bestaetigung in der Queue. Die UI fordert zum Entfernen der
  Quelldisc und Einlegen eines leeren Rohlings auf. Erst der Klick auf
  "Rohling pruefen und fortsetzen" fragt `DiscTools.get_disc_info` ab.
  Nur `present` und `blank` erlauben das Fortsetzen; beschriebene wiederbeschreibbare
  Medien werden mit dem Hinweis auf vorheriges Leeren abgewiesen. Keine automatische
  Loeschung und keine periodische Suche oder feste Wartezeit als Freigabekriterium.
  Das vorhandene `burn_iso` wird nach Freigabe benutzt. Bei verschiedenen Laufwerken
  folgt es weiterhin direkt auf den vorhandenen `DiscRipper`-Pfad.
- Pipeline-Abbruch beendet den wartenden Job; ein gleichzeitig laufender Mediencheck
  darf ihn danach nicht mehr zum Brennen freigeben. Ein abgelaufener API-Aufruf
  storniert seine Pruefung. Medienfehler lassen den Job fuer einen neuen Versuch warten.

Verifikation auf dem finalen Source:

- Fokussiert: `test_disc_copy_flow.py`, `test_drive_detection_ui.py`,
  `test_disc_flows.py`, `test_webview_navigation.py`: **56 passed in 6.46 s**.
- Gesamte Suite: **318 passed in 32.37 s**.
- Verhaltenstests: Rip/Burn-Reihenfolge, Warten und Bestaetigen ueber den echten
  API-Proxy, ungeeignete Medien, unterschiedliche Job-IDs/ISO-Pfade, vorhandene
  Benutzerdatei, Rip-/Brennfehler, Abbruch beim Warten und waehrend der Medienpruefung.
  JavaScript-Tests sichern Scan-Cache/Retry und Queue-Anzeige/API-Aktion ab.
- `compileall`: Exitcode 0. `scripts/verify_ui_bridge.py`: PASS, 0 Befunde.
  `node --check build/ui-audit/inline.js`: Exitcode 0.
- `.hermes/verify_core.py`: PASS; Job `done`, MP3 402328 Bytes, Codec mp3.
- `scripts/release_smoke.py`: PASS, Ausgabe `build/e2e-smoke-20260905-194633`;
  unter anderem Upscale 2560x1440, Interpolation 50 fps, deutsche SRT 199 Bytes,
  DVD-ISO 2627584 Bytes. Vorhandene Vendor-Dateien wurden fuer dieses Gate in
  den ignorierten Vendor-Ordner dieses Worktrees kopiert.
- `git diff --check`: Exitcode 0.

Kein Release-Build und kein physischer Medienwechsel/Brennvorgang ausgefuehrt.
Die neuen optischen Verhaltenstests simulieren die Hardwareantworten; fruehere
Artefakt-Hashes sind kein Nachweis fuer diesen geaenderten Source. Die bekannten
Signatur- und Hardware-Gates bleiben unveraendert offen.
