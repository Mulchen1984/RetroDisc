# RetroDisc Release-Audit-Status

Letzte Aktualisierung: 2026-09-05 20:50 CEST — sieben tote Bridge-Aktionen behoben (positionales `Job()`), Fix am gebauten Artefakt belegt

## Verbindlicher Abschlussstatus

**NOT RELEASE READY — softwareseitig abgeschlossen und erstmals an der gepackten EXE belegt; die Weitergabe an Dritte bleibt durch die fehlende Signatur blockiert.**

Der Arbeitsbaum nach `86098fe` wurde am 2026-09-05 als `01e5fd9` eingefroren; darauf liefen alle Source-Gates, ein Clean-Build, das Artefakt-Gate und der Runtime-Gate gruen. **Ein anschliessender manueller Acceptance-Test hat diesen Stand dann widerlegt:** ein vollstaendig heruntergeladener und korrekt veroeffentlichter YouTube-Download (rund 273 MB) wurde in der Oberflaeche als FAILED angezeigt, mit `'charmap' codec can't encode character ... : character maps to <undefined>`. Kein Gate hatte das gefunden - die automatisierten Laeufe schreiben auf einen UTF-8-faehigen Kanal, die gebaute Anwendung unter Windows nicht. Der Fehler ist behoben; die Bestaetigung am gebauten Artefakt steht noch aus. Die historischen Belege zu `1c486cc` gelten weiterhin nur fuer jenen alten Stand und seine Hashes.

Aktueller Nutzerauftrag: zuerst Windows abschliessen. macOS-Unterstuetzung ist wieder gewuenscht, aber auf spaeter verschoben; sie ist derzeit nicht verifiziert. Ein physischer DVD-Brenn-/Ruecklesetest und eine vertrauenswuerdige Signatur bleiben verpflichtende offene Release-Gates. Am 2026-09-05 wurden beide physischen Laufwerke erneut ohne Medium gemeldet; als Code-Signing-Zertifikat ist nur das abgelaufene Selftest-Zertifikat vorhanden.

Begründung: Auf dem Freeze-Stand `1c486cc` sind alle automatisierbaren Gates grün und real belegt — Source-Gates (193 Tests), vollständiger Real-Media-Smoke, UI/Bridge-Vergleich, Artefakt-Gate, Installation, **Start aus der Installation**, Deinstallation, Laufwerkserkennung, `default_device`, Disc-Erkennung, Rip-Workflow und YouTube-Download. Der Runtime-Gate auf den finalen Artefakten ist bestanden, ohne ein einziges CodeIntegrity-Ereignis.

Der Releaseblocker ist unverändert und ausschließlich extern: Die Artefakte sind **nicht signiert**, auf dem Host existiert kein vertrauenswürdiges Code-Signing-Zertifikat. Ohne Signatur ist keine verlässliche Weitergabe an Dritte möglich — Smart App Control entscheidet je Datei, ein hier bestandener Start sagt nichts über einen fremden Rechner. Für die Weitergabe fehlt daher genau ein Schritt: Zertifikat bereitstellen, `python build.py --clean --sign` ausführen und die Gates auf den dann entstehenden signierten Hashes wiederholen.

Zusätzlich offen als **ausstehende Hardware-Validierung** (kein Softwaremangel, kein Blocker für den Codestand): der reale physische Brennvorgang auf einen Rohling samt Rückleseprobe. Es stand kein Medium zur Verfügung; alles softwareseitig Prüfbare ist über ein virtuell eingebundenes DVD-Abbild belegt.

## Aktueller Checkpoint

- Branch: `crossplatform-2026`
- Letzter Freeze-Commit: `e07a6f4` (`Fix seven dead UI actions built from a positional Job()`) — dies ist der Stand, auf dem die aktuell gueltigen Artefakt-Hashes gemessen wurden
- Vorheriger Freeze-Commit: `6fc623b` (`FIX: keep a Windows console codepage from failing finished jobs`)
- Aeltere Freezes (historisch): `01e5fd9`, `1c486cc`
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


### 2026-09-05 19:54 CEST — Vorhandenen Disc-Copy-Fix kontrolliert geprueft und Rohling-Freigabe gehaertet

Ausgangslage und Zusammenarbeit:

- Zu Beginn HEAD `8b4392b`, mit den vier angekuendigten lokalen Dateien:
  `retrodisc_launcher.py`, `src/ui/app.html`, `tests/test_disc_copy_flow.py`
  und der neuen `tests/test_drive_detection_ui.py`. Der gesamte vorhandene
  Diff wurde zuerst lesend geprueft; nichts verworfen oder neu implementiert.
- Brauchbar und uebernommen: Job-ID im ISO-Namen, exklusive Dateireservierung,
  korrekter `job_type=`-Aufruf, Medienwechsel-Event mit Queue-Bestaetigung,
  Fehler-/Abbruchbehandlung sowie Session-Cache fuer erfolgreiche leere Scans.
  Die bereits vorhandenen fokussierten Tests bestanden: 33 passed in 6.27 s.
- Waehrend dieser Sitzung hat eine andere Sitzung diesen Ausgangsdiff samt
  Journal als `120619ba6596f467787cf8afe6de0ddfbcfd2819` committet und gepusht.
  Reflog, Commit-Diff und Remote wurden geprueft: derselbe Ausgangsdiff,
  kein Konflikt mit den folgenden Ergaenzungen. Kein Pull, Rebase oder
  Ueberschreiben fremder Aenderungen war erforderlich. Wiederholte Fetches
  bestaetigten lokalen HEAD und Remote identisch auf `120619b`.

Bestaetigte Restluecke und gezielte Ergaenzung:

- `present` und `blank` allein sind kein Beschreibbarkeitsbeleg: Der bestehende
  Windows-Dateisystem-Fallback kann ein leeres eingebundenes Volume als blank
  melden. Die Copy-Bestaetigung verlangt jetzt zusaetzlich ein beschreibbares
  DVD-/Blu-ray-Profil fuer den vorhandenen growisofs-Brennpfad. Unbekannte
  Profile, ROMs und CDs werden abgewiesen; eine gemeldete Kapazitaet kleiner
  als das Image ebenso. Beschriebene RW-Medien werden weiterhin nicht geloescht.
- Negative Gegenprobe vor dem Produktfix: sechs neue Verhaltenstests schlugen
  fehl, weil unbekannte/ROM-/CD-Profile und zu kleine Medien freigegeben wurden.
  Nach dem Fix sind diese Faelle gruen. Weitere Tests sichern unterstuetzte
  Profile, erneute Pruefung nach einer Probe-Ausnahme und die Entfernung der
  reservierten Teil-ISO beim Abbruch waehrend des Rippens ab.
- Zusaetzliche Produktaenderung nur in `retrodisc_launcher.py` (13 Zeilen).
  `src/ui/app.html` und der vorhandene Drive-Cache-Test blieben unveraendert;
  keine Startseiten-, Design- oder anderen UI-Arbeiten.

Eigene Verifikation nach der Ergaenzung, alle Exitcodes 0:

- `pytest -q tests/test_disc_copy_flow.py tests/test_drive_detection_ui.py`:
  **45 passed in 7.08 s**.
- Vollstaendiges `pytest -q`: **330 passed in 32.57 s**.
- `compileall` ueber src, tests und beide Launcher: PASS.
- `scripts/verify_ui_bridge.py`: PASS, 0 Befunde, 49 Aufrufstellen,
  38 verschiedene UI-Methoden, 41 API- und 43 Bridge-Methoden.
- `node --check build/ui-audit/inline.js` und `git diff --check`: PASS.
- `.hermes/verify_core.py`: PASS, echter MP3-Job done, 402328 Bytes, Codec mp3.
- `scripts/release_smoke.py`: PASS, `build/e2e-smoke-20260905-195311`;
  Upscale 2560x1440, Interpolation 50 fps, deutsche SRT 199 Bytes,
  DVD-ISO 2627584 Bytes.
- Runtime: freigegebenes `C:\Users\marco\.local\bin\python3.11.exe` mit
  PYTHONPATH auf die vorhandenen Site-Packages des RetroDisc-Hauptworktrees;
  keine Ausfuehrung der blockierten venv-EXE.

Kein Release-Build und kein physischer Brenn-/Medienwechseltest. Die optischen
Verhaltenstests simulieren Hardwareantworten; sie ersetzen keine physische
Validierung. Die bestehenden Signatur- und Hardware-Release-Gates bleiben offen.


### 2026-09-05 20:10–20:35 CEST — Sieben tote Bridge-Aktionen: `Job()` positional gebaut

Ausgangslage: `git fetch origin`, lokaler HEAD und `origin/crossplatform-2026`
identisch auf `888b867`, Arbeitsbaum sauber. Erst der Ist-Zustand gemessen:
`pytest -q` 340 passed, `compileall` 0, `verify_ui_bridge` PASS/0 Befunde,
`node --check` 0. Kein bestehender Fix wurde angefasst oder neu geschrieben.

#### Der Befund

`Job` ist eine Dataclass, deren **erstes** Feld `id` heisst, nicht `job_type`.
Der Disc-Copy-Block vom selben Tag hatte genau diesen Fehler an einer Stelle
korrigiert. Er stand jedoch an **neun** weiteren Stellen im produktiven
Launcher und war dort nie aufgefallen.

Ein positionales `Job(JobType.TRIM, ...)` legt den Enum in `id` ab und laesst
`job_type` auf dem Vorgabewert `CONVERT` stehen. Die Folge ist kein
Schoenheitsfehler:

- `_submit_job` endet mit `json.dumps({"job_id": job.id, ...})`. Ein Enum ist
  nicht JSON-serialisierbar, der Aufruf fliegt mit `TypeError: Object of type
  JobType is not JSON serializable` aus der Bridge heraus.
- `get_queue` haette an derselben Stelle die **gesamte** Queue-Ansicht
  mitgerissen, sobald ein solcher Job darin gelandet waere.
- Alle Jobs einer Art teilten sich eine ID. `Pipeline._tasks` und
  `_job_handlers` sind ID-indiziert; zwei gleichzeitige Auto-Jobs des
  Watch-Folders haetten sich gegenseitig den Handler ueberschrieben.
- Queue-Beschriftung und Brennanimation lesen `job_type` und haetten
  durchgehend `convert` gesehen.

Betroffen waren sieben UI-Aktionen — **Rippen, Highlights, Untertitel,
Upscale, Interpolation, Trim, Merge** — sowie beide Watch-Folder-Pfade.
Alle sieben sind in `src/ui/app.html` verdrahtet und je genau einmal
aufgerufen. Sechs davon haben **kein** `try/catch` um den Aufruf: das
abgelehnte Promise beendet die JS-Funktion stillschweigend, der Nutzer sieht
gar nichts, und der Statustext bleibt auf „Trim läuft…" bzw.
„Video-Upscaling wird gestartet…" stehen. Nur `startRip` faengt und meldet.

#### Warum kein Gate das gefunden hat

Dieselbe strukturelle Luecke wie beim charmap-Blocker, eine Schicht tiefer:
`scripts/release_smoke.py` ruft `FFmpeg` und `VideoUpscaler` **direkt** auf und
laesst die Bridge aus. `verify_ui_bridge.py` vergleicht Namen und Aritaeten und
ist deshalb korrekt gruen geblieben — die Signaturen stimmten ja. Der
Acceptance-Harness fuhr die Bridge, aber nur fuer Konvertieren und Download.
Zwischen „Dienst funktioniert" und „Schaltflaeche funktioniert" hat schlicht
nichts gemessen.

#### Reproduktion vor der Aenderung

Ueber den echten Konstruktor `RetroDiscBridge()` mit laufendem Loop-Thread,
isolierten Settings und ohne Fenster; alle sieben Aufrufe endeten mit
`TypeError: Object of type JobType is not JSON serializable`. Nach dem Fix
liefern alle sieben `{"job_id": "<8 Hex>", "status": "queued"}`.

#### Fix

Neun Zeilen in `retrodisc_launcher.py`, ausschliesslich `JobType.X` →
`job_type=JobType.X`: `rip_disc`, `create_highlights`, `generate_subtitles`,
`upscale_video`, `interpolate_video`, `trim_video`, `merge_videos` und die
beiden Jobs in `set_watch_folder._submit_watched`. Keine Signatur, kein
Verhalten und keine UI wurde sonst geaendert.

#### Regressionsabsicherung, auf zwei Ebenen

`tests/test_job_submission.py` (neu, 3 Tests):

- Alle **elf** einreihenden Bridge-Methoden liefern eine echte String-Job-ID,
  parken einen Job mit dem **erwarteten** `JobType`, und keine zwei IDs
  kollidieren. Gefahren wird der Produktkonstruktor; die Pipeline wird als
  „laufend" markiert, ohne einen Worker zu starten, damit die Jobs in der
  Queue stehen bleiben und ohne FFmpeg/yt-dlp/Laufwerk pruefbar sind.
- Zwei Trim-Jobs bekommen verschiedene IDs und **verschiedene** Handler-Objekte
  in `Pipeline._job_handlers`.
- Eine AST-Regel ueber `retrodisc_launcher.py` und ganz `src/`: kein `Job(...)`
  darf ueberhaupt ein positionales Argument bekommen.

`src/acceptance.py`: neuer Fall **`media_tools`**, der Trim A, Trim B, Merge,
2×-Upscale und 30-fps-Interpolation ueber den Bridge-Pfad end-to-end faehrt.
Bewertet wird nur der fachliche Endzustand: Job `done`, Datei vorhanden und
nicht leer, FFprobe liest die Ausgabe wirklich, und die Upscale-Breite ist
mindestens verdoppelt. Damit gilt derselbe Fall auch fuer die gepackte EXE.
Zwei zusaetzliche Tests in `tests/test_acceptance_harness.py` sichern, dass der
Fall registriert ist, wirklich ueber `ctx.bridge.*` laeuft und gegen eine
Bridge, die nur Fehler liefert, FAIL meldet statt gruen zu werden.

#### Negative Gegenprobe

Mit zurueckgesetztem `retrodisc_launcher.py` und unveraendertem Testcode:

- `pytest -q tests/test_job_submission.py`: **3 failed** — alle drei.
- `run_acceptance.py --source-only --cases media_tools`: **FAIL**,
  Exitcode 1, Befund `TypeError: Object of type JobType is not JSON
  serializable`, `release: FAIL`.

#### Gates auf dem finalen Source, alle Exitcode 0

- `pytest -q`: **345 passed in 17,90 s** (vorher 340).
- `compileall` ueber `src`, `tests` und beide Launcher: PASS.
- `.hermes/verify_core.py`: PASS; echter MP3-Job `done`, 402328 Bytes, Codec `mp3`.
- `scripts/verify_ui_bridge.py`: PASS, 0 Befunde; 49 Aufrufstellen,
  38 UI-Methoden, 41 API-, 43 Bridge-Methoden.
- `node --check build/ui-audit/inline.js`: PASS.
- `scripts/release_smoke.py`: PASS; Upscale 2560x1440, Interpolation 50 fps,
  Highlights 6,013968 s, deutsche SRT, DVD-ISO.
- `scripts/run_acceptance.py --source-only`: **PASS, alle sechs Faelle** —
  startup 2,00 s, settings 0,02 s, conversion 0,39 s, error_handling 0,14 s,
  **media_tools 2,39 s**, unicode_download 14,08 s.
- `scripts/verify_home_layout.py`: **PASS, 10/10 Messungen**, realer
  pywebview-/WebView2-Lauf bei 100/125/150 %. Der HEAD-Commit `888b867` hatte
  dieses Gate zwar ausgefuehrt, aber **keinen Journalblock hinterlassen**; das
  Ergebnis ist hiermit auf dem aktuellen Stand nachgemessen und eingetragen.
- `git diff --check`: PASS.

#### Zusaetzlich geprueft, ohne Befund

Alle uebrigen ueber `RetroDiscApi` erreichbaren Methoden wurden gegen eine
echte Bridge aufgerufen (`get_presets`, `get_queue`, `get_settings`,
`get_tool_status`, `check_tools`, `get_watch_folders`, `probe_file`,
`clear_completed`, `cancel_job`, `save_settings`, `convert_batch`, `copy_disc`,
`create_dvd`, `search_media`, `run_assistant`, `set_watch_folder`,
Bibliotheksmethoden, Fehlereingaben): jede liefert gueltiges JSON, keine wirft.
Ausserdem geprueft und **in Ordnung**: `WatchRule` und `DVDProject` werden
positional bzw. per Keyword korrekt gebaut, `DiscTools.mediainfo` faellt nie
auf `None` zurueck, und `DiscRipper`s `mkv_copy`-Verschiebezweig greift nur auf
die eigene Temp-Datei, nie auf eine Datei der Quelldisc.

#### Stand

Der Fix ist auf Source-Ebene vollstaendig belegt. **Die Artefakt-Hashes des
Blocks vom 2026-09-05 15:20–15:40 gelten fuer diesen Stand nicht mehr**: es
wurde produktiver Code geaendert. Ein Build aus dem eingefrorenen Commit
dieses Blocks und die Wiederholung von Artefakt-Gate und Packaged Acceptance
auf den neuen Hashes stehen aus und folgen unmittelbar.

Unveraendert offen und nicht durch Code loesbar: die fehlende
vertrauenswuerdige Code-Signatur und der physische Brenn- und Rueckleseteset
ohne verfuegbaren Rohling. Die optischen Verhaltenstests simulieren weiterhin
Hardwareantworten.

---

### 2026-09-05 20:35–20:50 CEST — Build, Artefakt-Gate, Packaged Acceptance und Runtime-Gate auf den neuen Hashes

Gebaut aus dem eingefrorenen Commit `e07a6f4`
(`Fix seven dead UI actions built from a positional Job()`), Arbeitsbaum sauber.
`python build.py --clean`: Exitcode 0. Signierung uebersprungen — nicht
konfiguriert, kein vertrauenswuerdiges Zertifikat vorhanden.

#### Artefakte

- `dist\RetroDisc.exe`: **502988544 Bytes**,
  SHA-256 `2DCF220D115FF171EB02D190B333FBC0CE5027BE54BBABCCE1180C7402FA508B`
- `Output\RetroDisc_1.0.0_Portable.zip`: **501542969 Bytes**,
  SHA-256 `0F9D137378DE98447791E2E3CAF2810ED88E015BDA3FE1787CB24DDB400EF327`
- `Output\RetroDisc_Setup_1.0.0.exe`: **508919714 Bytes**,
  SHA-256 `EAE2037298915CE8F5557EEA57550124F2B7044C1677108B75169584324A43D8`

Die Hashes des Blocks vom 15:20–15:40 sind damit abgeloest.

#### `scripts/verify_release_artifacts.py`: PASS, 0 Befunde, Exitcode 0

Alle drei Artefakte gehasht, ZIP-Inhalt geprueft und die enthaltene EXE
**byteidentisch** zur `dist`-EXE, Installation und Deinstallation vollstaendig
in der isolierten Sandbox durchlaufen (Installer rc 0, installierte EXE
byteidentisch, Verknuepfungen angelegt und wieder entfernt, Installationsordner
restlos geloescht). Authenticode: `NotSigned` fuer EXE und Installer — als
Hinweis gefuehrt, kein Gate-Fehler, aber weiterhin der Weitergabe-Blocker.

#### `scripts/run_acceptance.py`: PASS, Exitcode 0

**source: PASS 6/6** — startup 3,72 s, settings 0,00 s, conversion 0,41 s,
error_handling 0,11 s, **media_tools 2,58 s**, unicode_download 9,44 s.

**packaged: PASS 7/7**, 29,7 s gesamt, im echten gefrorenen Prozess:

| Fall | Status | Belegte Messwerte |
| --- | --- | --- |
| startup | PASS | `frozen=True`, ffmpeg rc 0, yt-dlp rc 0, stdout `utf-8` / `replace` |
| settings | PASS | ueber `save_settings` geschrieben, per frischem `AppSettings.load()` bestaetigt, Ausgangswert wiederhergestellt |
| conversion | PASS | Job `done`, Ausgabe 82590 Bytes, FFprobe liest `mp3` |
| error_handling | PASS | ungueltige URL und fehlende Datei kontrolliert abgewiesen, App danach weiter benutzbar |
| **media_tools** | **PASS** | Trim A `done` 31272 B, Trim B `done` 14420 B, Merge `done` 31859 B, Upscale `done` **640x360** (verdoppelt), Interpolation `done` **30,0 fps** |
| unicode_download | PASS | Titel `PSY - GANGNAM STYLE(강남스타일) M/V`, Job `done`, 26736119 Bytes, keine transienten Reste, keine Arbeitsverzeichnisse |
| restart | PASS | zweiter Start der EXE Exitcode 0, startup erneut PASS nach 18,2 s |

Damit ist der Fix **am gebauten Artefakt** belegt, nicht nur im Quellstand:
Trim, Merge, Upscale und Interpolation laufen in der ausgelieferten EXE ueber
denselben Bridge-Pfad, den die Oberflaeche benutzt, und liefern jeweils eine von
FFprobe lesbare Datei.

#### Runtime-Gate auf `2DCF220D…`

Normaler Start **ohne** Flag, also genau wie beim Endnutzer:

- Hauptfenster **`RetroDisc 1.0`** erschienen; 0,6 s bei warmem Start (das
  `_MEI`-Verzeichnis war vom vorherigen Lauf bereits entpackt, deshalb ist der
  Wert nicht mit den frueher gemessenen ~10 s Kaltstart vergleichbar).
- Zwei `RetroDisc`-Prozesse: PyInstaller-Bootloader plus Anwendung — bei
  Onefile erwartet. Das Fenster gehoert dem **Kindprozess**; eine Messung ueber
  `MainWindowTitle` des von `Start-Process` gelieferten Objekts findet es
  deshalb nie und darf nicht als Fehlschlag gewertet werden.
- **Kein** neuer `conhost`-, `cmd`- oder `powershell`-Prozess: kein sichtbares
  Konsolenfenster, wie von den Produktvorgaben verlangt.
- **0** CodeIntegrity-Ereignisse 3033/3077.
- Im Anwendungslog dieses Laufs (19 neue Zeilen, auf den Lauf eingegrenzt):
  **0** Treffer auf `ERROR`, `Traceback`, `charmap` oder `UnicodeEncodeError`.
  Protokolliert sind Bundle-Werkzeuge, `Bridge initialisiert`, aktive
  WebView2-Navigationssperre und der Uebergang `Splash fertig - lade Haupt-UI`.
- Nach dem Beenden verblieben 0 `RetroDisc`-Prozesse.

#### Stand

Softwareseitig ist dieser Stand vollstaendig belegt: alle Source-Gates, der
Artefakt-Gate, die Packaged Acceptance mit sieben Faellen und der Runtime-Gate
sind auf den oben genannten Hashes gruen.

Weiterhin offen und **nicht durch Code loesbar**:

1. **Keine vertrauenswuerdige Code-Signatur.** `NotSigned` fuer EXE und
   Installer; auf dem Host existiert nur ein abgelaufenes Selftest-Zertifikat.
   Ohne Signatur ist keine verlaessliche Weitergabe an Dritte moeglich — Smart
   App Control entscheidet je Datei, ein hier bestandener Start sagt nichts
   ueber einen fremden Rechner. Fehlender Schritt: Zertifikat bereitstellen,
   `python build.py --clean --sign`, Gates auf den dann entstehenden signierten
   Hashes wiederholen.
2. **Kein physischer Brenn- und Rueckleseteset.** Es stand kein Rohling zur
   Verfuegung; beide Laufwerke meldeten erneut kein Medium. Die optischen
   Verhaltenstests simulieren Hardwareantworten und ersetzen das nicht.

Noch nicht als Packaged-Fall automatisiert, bewusst zurueckgestellt: Cancel,
Collision (auf Quellebene durch `tests/test_download_publish.py` abgedeckt),
Whisper-Untertitel und der optische Teil. `rip_disc` ist durch den neuen
Submit-Test auf Bridge-Ebene abgesichert, end-to-end aber weiterhin nur mit
echter Hardware pruefbar.

---

### 2026-09-05 20:50–20:55 CEST — Fremde Blu-ray-Korrektur integriert, eigene Artefakt-Hashes dadurch ungueltig

`git fetch origin` unmittelbar vor dem Push meldete zwei neue Commits auf
`origin/crossplatform-2026`, die waehrend dieses Arbeitsblocks entstanden sind:

- `0ae5069` — `Fix Blu-ray ISO classification in disc ripper`
- `17f42c3` — `Add regression coverage for Blu-ray ISO classification`

Sie aendern `src/services/ripper.py` und ergaenzen
`tests/test_ripper_iso_types.py`: beim ISO-Rippen wird eine Blu-ray jetzt an
`BDMV` erkannt und als `DiscType.BLURAY` an `create_iso` gereicht, statt wie
bisher hinter `VIDEO_TS` auf `DiscType.CD` zu fallen. Der Diff wurde gelesen
und ist fachlich richtig.

Es gibt **keine Ueberschneidung** mit den Dateien dieses Blocks
(`retrodisc_launcher.py`, `src/acceptance.py`,
`tests/test_acceptance_harness.py`, `tests/test_job_submission.py`,
`RELEASE_AUDIT_STATUS.md`). Die beiden eigenen Commits wurden per Rebase auf
`17f42c3` gesetzt; kein Konflikt, kein Force-Push, nichts Fremdes
ueberschrieben. `pytest -q` auf dem integrierten Stand: **348 passed in
17,55 s** (345 aus diesem Block plus die drei neuen Ripper-Tests).
`compileall`, `verify_ui_bridge` (PASS, 0 Befunde), `node --check` und
`git diff --check`: alle Exitcode 0.

**Konsequenz fuer die Artefakte, ausdruecklich festgehalten:** die im
vorangegangenen Block genannten Hashes
(`2DCF220D…`, `0F9D1373…`, `EAE20372…`) wurden auf einem Source gemessen, der
die Blu-ray-Korrektur **nicht** enthaelt, und der Commit `e07a6f4`, den jener
Block nennt, existiert nach dem Rebase nicht mehr. Die Messwerte jenes Blocks
bleiben als historischer Beleg fuer den damals gemessenen Zustand richtig, sind
aber **kein Nachweis fuer den jetzigen HEAD**. Es wird deshalb aus dem
integrierten Stand neu gebaut und komplett neu gemessen.

---

### 2026-09-05 20:55–21:15 CEST — Gueltige Artefakte: Neubau aus dem integrierten Stand

Gebaut aus dem eingefrorenen Commit `ba9805b`
(`Integrate the Blu-ray ripper fix and void my artifact hashes`), Arbeitsbaum
sauber. `python build.py --clean`: Exitcode 0. Signierung uebersprungen — nicht
konfiguriert.

**Dies sind die aktuell gueltigen Artefakt-Hashes.** Sie loesen sowohl die des
Blocks vom 15:20–15:40 als auch die des Blocks vom 20:35–20:50 ab; jene bleiben
nur als historischer Beleg fuer ihren jeweiligen Source stehen.

- `dist\RetroDisc.exe`: **502988285 Bytes**,
  SHA-256 `9B401B0C74B1BE1CCB213A18ED8E56686D848739978B526A2BCF886B2897F302`
- `Output\RetroDisc_1.0.0_Portable.zip`: **501543016 Bytes**,
  SHA-256 `A46009AB3C25935FC5474ECAAE0BDCBBCB391E7CF2C29BA09B5AB38AA9B24587`
- `Output\RetroDisc_Setup_1.0.0.exe`: **508919403 Bytes**,
  SHA-256 `2BCFAF4F4BD11DA75DB79797AFC515691BFC958A83746409D356858C3A8D56E6`

#### `scripts/verify_release_artifacts.py`: PASS, 0 Befunde, Exitcode 0

ZIP-Inhalt vollstaendig, enthaltene EXE **byteidentisch** zur `dist`-EXE,
Installation und Deinstallation in der isolierten Sandbox komplett durchlaufen
(Installer rc 0, installierte EXE byteidentisch, Verknuepfungen angelegt und
wieder entfernt, Installationsordner restlos geloescht). Authenticode:
`NotSigned` fuer EXE und Installer — Hinweis, kein Gate-Fehler, aber
unveraendert der Weitergabe-Blocker.

#### `scripts/run_acceptance.py`: PASS, Exitcode 0

**packaged: PASS 7/7** im echten gefrorenen Prozess:

| Fall | Status | Belegte Messwerte |
| --- | --- | --- |
| startup | PASS | `frozen=True`, ffmpeg rc 0, yt-dlp rc 0, stdout `utf-8` / `replace` (6,08 s) |
| settings | PASS | geschrieben, per frischem `AppSettings.load()` bestaetigt, Ausgangswert wiederhergestellt |
| conversion | PASS | Job `done`, Ausgabe 82590 Bytes, FFprobe liest `mp3` |
| error_handling | PASS | ungueltige URL und fehlende Datei kontrolliert abgewiesen, App danach benutzbar |
| **media_tools** | **PASS** | Trim A `done` 31272 B, Trim B `done` 14420 B, Merge `done` 31859 B, Upscale `done` **640x360**, Interpolation `done` **30,0 fps** (2,55 s) |
| unicode_download | PASS | Titel mit Hangul, Job `done`, 26736119 Bytes, keine transienten Reste, keine Arbeitsverzeichnisse |
| restart | PASS | zweiter Start Exitcode 0, startup erneut PASS nach 15,7 s |

`media_tools` ist damit auch auf diesen Bytes gruen: die vier zuvor toten
Werkzeuge laufen in der ausgelieferten EXE ueber denselben Bridge-Pfad wie die
Oberflaeche und liefern jeweils eine von FFprobe lesbare Datei.

#### Runtime-Gate auf `9B401B0C…` (Kaltstart, frisch entpacktes Bundle)

- Hauptfenster **`RetroDisc 1.0`** nach **8,7 s**.
- **Kein** neuer `conhost`-, `cmd`- oder `powershell`-Prozess: kein sichtbares
  Konsolenfenster.
- **0** CodeIntegrity-Ereignisse 3033/3077.
- Anwendungslog dieses Laufs, auf den Lauf eingegrenzt: 19 Zeilen, **0** Treffer
  auf `ERROR`, `Traceback`, `charmap` oder `UnicodeEncodeError`; je einmal
  `Navigationssperre aktiv` und `Splash fertig - lade Haupt-UI`.
- Nach dem Beenden 0 verbliebene `RetroDisc`-Prozesse.

#### Verbleibende offene Release-Gates

Softwareseitig ist dieser Stand vollstaendig belegt. Was noch fehlt, ist **nicht
durch Code loesbar**:

1. **Vertrauenswuerdige Code-Signatur.** `NotSigned` fuer EXE und Installer; auf
   dem Host existiert nur ein abgelaufenes Selftest-Zertifikat. Ein selbst
   ausgestelltes Zertifikat loest das nicht. Fehlender Schritt: Zertifikat
   bereitstellen, `python build.py --clean --sign`, danach Artefakt-,
   Acceptance- und Runtime-Gate auf den dann entstehenden signierten Hashes
   wiederholen.
2. **Physischer Brenn- und Rueckleseteset.** Kein Rohling verfuegbar; beide
   Laufwerke melden weiterhin kein Medium. Die optischen Verhaltenstests
   simulieren Hardwareantworten und ersetzen das nicht.

Bewusst noch nicht als Packaged-Fall automatisiert: Cancel, Collision (auf
Quellebene durch `tests/test_download_publish.py` abgedeckt),
Whisper-Untertitel und der optische Teil. `rip_disc` ist seit diesem Block auf
Bridge-Ebene abgesichert, end-to-end aber nur mit echter Hardware pruefbar.

### 2026-09-08 — macOS: Download-Templates plattformunabhaengig pruefen

- Grundlage: `origin/crossplatform-2026` bei `44af8d2`, isolierter Worktree
  auf `codex/retrodisc-download-paths`. Aktueller Nutzerauftrag autorisiert
  die Weiterentwicklung auf macOS; keine Build-/Release-Aenderung.
- Befund: Die native `Path`-Pruefung akzeptierte unter macOS fuenf bereits
  durch Tests ausgeschlossene Windows-Pfadformen (Traversal, Laufwerk,
  laufwerksrelativer Pfad, Root und UNC). Reproduktion: 5 failed, 4 passed.
- Fix: Windows-Syntax zusaetzlich mit `PureWindowsPath` pruefen, bevor yt-dlp
  startet. Bestehende native Pfad- und Zielverzeichnispruefung bleibt bestehen.
- Test-Mock wirft bei unerwartetem Prozessstart sofort einen AssertionError,
  damit dieser Fehler keinen haengenden Mock-Stream mehr verursacht.
- Verifikation auf macOS mit vorhandener Python-3.11-Umgebung:
  `python -m pytest -q tests/test_download_publish.py tests/test_core_flows.py
  -k 'download or collision or playlist or publication or publish'`
  → **35 passed, 10 deselected in 0.20s**, Exitcode 0.
- Kein Windows-Lauf, kein echter Netzwerkdownload, kein Build durchgefuehrt;
  daraus folgt keine neue Artefakt- oder Windows-Runtime-Freigabe.
- Naechster sinnvoller Punkt: Download und anschliessende Audioextraktion mit
  echten macOS-Tools gegen den gemeinsamen Acceptance-Harness pruefen.

### 2026-09-08 — macOS: Video-Download mit separater Audioausgabe

- Zentrale Defaults in `src/config/settings.py` erweitert: macOS-Video und
  Downloads unter `~/Movies/RetroDisc`, Audio unter `~/Music/RetroDisc`.
  Explizit konfigurierte Pfade bleiben erhalten; Windows/Linux-Defaults bleiben
  unveraendert. Downloader verwendet dieselbe zentrale Default-Funktion.
- Produktive Download-Bridge extrahiert auf macOS nach einem Video-Download
  MP3 mit dem vorhandenen `FFmpeg.extract_audio`. Audio-Namen enthalten die
  Job-ID; vorhandene Zieldateien werden vom FFmpeg-Wrapper abgewiesen.
  Bei Extraktionsfehler bleibt das fertige Video samt Ergebnispfad erhalten.
  Audio-only verwendet auf macOS den Audioordner. Windows-Verkettung unveraendert.
- Vorhandene Tool-Erkennung wiederverwendet; macOS ignoriert Windows-EXEs.
- Beide Ergebnispfade werden in Queue/Event ausgegeben und in der vorhandenen
  Warteschlange als kopierbarer, HTML-escapter Text angezeigt.
- Echter macOS-Test: lokaler HTTP-Server mit versioniertem Testvideo → echte
  yt-dlp-Binary → Video → echte ffmpeg-MP3-Extraktion; ffprobe bestaetigt
  Videostream und reine Audioausgabe mit passender Dauer. Audio-only ebenfalls
  real geprueft. Home/Temp/Appdaten fuer den Test in den Worktree umgeleitet.
  `tests/test_macos_download_workflow.py`: 6 passed in 1.69s (inkl. Realtest).
  Danach zusaetzlicher Tool-Erkennungstest: 6 passed, 1 deselected in 0.09s.
- Download-/Settings-/Completion-Regressionen gezielt: 44 passed,
  11 deselected in 0.16s. UI-Bridge-Pruefung PASS (0 findings),
  `node --check build/ui-audit/inline.js` erfolgreich.
- Reale Testdateien unter
  `build/macos-download-check/verified-results/test_real_macos_download_and_a0/`:
  Video: `Movies/RetroDisc/test_video [test_video].mp4`;
  Audio: `Music/RetroDisc/test_video [test_video]_fbe13892.mp3`.
- Grenzen: lokaler HTTP-Download statt YouTube-Netztest, keine GUI-Sichtpruefung,
  kein Windows-Runtime-Test, kein Build/Commit. Keine neuen Dependencies.
- Naechster offener Punkt: externe YouTube-Quelle mit vorhandener yt-dlp-Version
  pruefen; bei Playlists wird derzeit nur fuer das zurueckgegebene Hauptvideo
  die separate MP3 erzeugt.

### 2026-09-08 — Kleine macOS-/Queue-Korrekturen vor VideoToolbox

- Ausgabeordner: macOS verwendet `open` mit separatem Pfadargument, Timeout und
  Exitcode-Pruefung; Windows verwendet weiterhin `os.startfile`.
- Fehlende macOS-Tools starten keinen Windows-EXE-Download mehr; klare Diagnose
  verweist auf native Tools in PATH/vendor. Darwin hat keinen erfundenen
  `/dev/sr0`-Default mehr, sondern verlangt eine Laufwerksauswahl.
- Queue: Jobnamen HTML-escapen; vorhandene Ergebnispfade explizit mit
  Video/Audio beschriften. Lange Unicode-Pfade per echtem Node-Rendering getestet.
- Gezielt 15 passed. Visuelle macOS-Abnahme bleibt offen (Computer Use konnte
  das Entwicklungsfenster nicht adressieren); keine weiteren Computer-Use-Versuche.
- Native optische Erkennung/Brennen bleiben ohne Hardwarebeleg offen.

### 2026-09-08 — VideoToolbox: H.264/HEVC mit CPU-Fallback

- `FFmpeg.available_video_encoders()` fragt das konfigurierte Binary ab,
  mit Timeout, Prozess-Cleanup und Cache pro Toolpfad.
- Converter bevorzugt auf macOS fuer libx264/libx265 die Encoder
  h264_videotoolbox/hevc_videotoolbox. `-allow_sw 0` erzwingt echte Hardware;
  fehlender Encoder oder FFmpeg-Fehler wiederholt mit dem bisherigen CPU-Preset.
  Abbruch wird nicht als Fallback behandelt. Windows-Encoderwahl bleibt unveraendert.
- Vorhandene Bitraten bleiben erhalten (H.264 720p: 3M, HEVC 4K: 15M).
  Beim HEVC-Preset ohne feste Aufloesung wird die 4K/15M-Referenz nach
  Quellpixelzahl skaliert (1080p: 3.75M, mindestens 250k). Dies ist keine
  CRF-Gleichsetzung; fuer exakte CRF-Kontrolle bleibt CPU verfuegbar.
  CPU-spezifisches preset/crf entfaellt nur im Hardwarelauf, H.264-Level wird
  in die VideoToolbox-Zahlendarstellung umgerechnet. HEVC-MP4 verwendet hvc1.
- UI auf macOS: „Apple Hardware – schnell“ (Vorgabe) / „CPU – maximale
  Qualitaetskontrolle“, fuer Einzel- und Batch-Konvertierung. Andere Plattformen
  zeigen keine Apple-Option. Keine neue Dependency, keine Presetmutation.
- Real auf macOS: H.264 720p, iPhone 1080p, HEVC Originalgroesse und HEVC 4K
  mit Hardware erfolgreich. ffprobe bestaetigt Codec, Aufloesung, Audio und
  Dauer. CPU-Fallback bei fehlender Encoderanzeige und echtem FFmpeg-Fehler
  ebenfalls bis zur gueltigen Ausgabedatei geprueft.
- 2-Sekunden-Testclip (720p): H.264 Hardware 0.432s / CPU 0.380s;
  HEVC Hardware 0.513s / CPU 0.717s. Kein belastbarer Benchmark: Startkosten
  dominieren, Bitratenregelung und CPU-CRF sind nicht qualitaetsgleich.
- Reproduktion: `build/videotoolbox-check/run.py`, `verify_extra.py`;
  Messungen in `result.json` und `extra-result.json`, alles im Worktree.
- Gezielt: 50 passed, 1 deselected (Whisper-Runtime-Test: faster_whisper fehlt
  in der vorhandenen Mac-Testumgebung). UI-Bridge PASS (0 findings), Node-Syntax
  erfolgreich. Keine komplette Suite, kein Windows-/GUI-/Release-Nachweis.

### 2026-09-08 — Gemeinsame Uebergaben ueber Recent Media

- Kleine Ergebnishistorie in der vorhandenen MediaLibrary-SQLite-Datei:
  `recent_outputs` speichert maximal zehn Pfade mit Vorgang und Zeitpunkt;
  Dateiname/Medientyp werden ohne ffprobe abgeleitet. Keine zweite Bibliothek,
  kein Scan und keine neuen Dependencies. Eigene kurze DB-Transaktionen fuer
  Job-Thread/UI; Pfade werden dedupliziert und beim Start/Abruf bereinigt.
- Zentraler Completion-Hook registriert nur DONE-Outputs aus output_path und
  output_paths. Fehlende/leere Dateien, Download-Arbeitsordner, Staging-Dateien,
  konfigurierte Temp-Verzeichnisse und Thumbnails werden ausgeschlossen.
- Download/Video-Konvertierung/Rip → Konvertieren und DVD-Brennen;
  extrahiertes Audio → Audio-Konvertierung. Neueste passende Ausgabe gewinnt.
  DVD-Vorschlaege verwenden die Videoformate des vorhandenen Converters;
  die bestehende DVD-Pipeline konvertiert sie selbst nach DVD-MPEG.
  Andere erkannte Videos bieten „Vor dem Brennen konvertieren“ mit vorhandenem
  H.264-Preset. Audio und ISO werden nicht als DVD-Video-Eingabe vorgeschlagen.
- UI: kompakter „Zuletzt erstellt“-Bereich mit Name, Typ, Herkunft,
  aufklappbarem vollstaendigem Pfad und Uebernahmebutton. Vorschlaege ersetzen
  niemals automatisch eine manuelle Auswahl. Vor Uebernahme erneut Existenz
  pruefen. Dateinamen/Pfade sind HTML-escaped und umbrechbar.
- Mac-Encoderwahl: Auto (Apple bevorzugt), Apple Hardware, CPU. Vorhandene
  Encoder-/Fallback-Implementierung wiederverwendet; Windows-Auswahl unveraendert.
- Gezielt 66 passed, 1 deselected (unveraendert fehlendes faster_whisper im
  fachfremden Runtime-Test). Einschliesslich echter Queue-Completion,
  SQLite-Neustart, fehlgeschlagenem Job, Sonderzeichen, manuellem Auswahl-Schutz,
  gerenderten UI-Uebergaben in Node sowie Auto/Hardware/CPU-Fallback.
  UI-Bridge PASS (0 findings), Node-Syntax und git diff --check sauber.
- Keine Computer-Use-/Web-Aufrufe, keine Commits. Visuelle Abnahme und reales
  macOS-Brennen mit Laufwerk/Rohling bleiben extern zu pruefen.

### 2026-09-08 — Tatsächlichen Konvertierungsoutput im Finder öffnen

- Ursache: Convert setzt Job.output_path; Queue/UI übernahmen bisher nur
  output_paths. Der Öffnen-Button verwendete ausschließlich den Standardordner.
- Queue liefert jetzt auch output; UI führt beide Ergebnisfelder dedupliziert
  zusammen. Jeder erfolgreiche Output und Recent-Media-Vorschlag erhält einen
  eigenen Öffnen-Button mit HTML-escaped Datenattribut und Fehleranzeige.
- Zentrale reveal_output-Funktion: macOS open -R für Dateien, open für Ordner;
  fehlende Dateien führen zum vorhandenen Elternordner. Windows öffnet weiter
  Ordner über os.startfile. Keine Shell und keine festgelegten Benutzerpfade.
- 26 gezielte Tests bestanden (Bridge, Recent Media, UI-Escaping/Node),
  UI-Bridge 0 findings, Node-Syntax und diff --check sauber. Native Aufrufe
  gemockt; keine visuelle Finder-/Windows-Abnahme und keine Commits.
- Separater bestehender os.startfile-Aufruf in der Clip-Vorschau gehört nicht
  zur Ausgabeort-Funktion und wurde in diesem Ticket nicht geändert.

### 2026-09-08 — KI-Regisseur: lokale Planung, Fallback und echter Schnitt

- Bestehende MediaLibrary um Asset-Metadaten/Transkripte erweitert; Director-
  Projekte speichern Prompt, Quellen, Timeline, Sprechertexte und Ergebnisse.
  Fehlende Quellen werden beim Laden markiert, beim Rendern erneut geprüft.
- Ollama erhält Pydantic-JSON-Schema mit erlaubten Asset-IDs. Genau ein
  Reparaturversuch, danach gekennzeichneter deterministischer Fallback.
  Zeitbereiche bleiben an tatsächliche Quelllängen gebunden; Zielpositionen
  werden aus den Schnittlängen berechnet. Explizit zitierter Sprechertext
  bleibt im Fallback erhalten; keine erfundenen Übersetzungen/Inhalte.
- Reale lokale Prüfung mit installiertem llama3.2:3b: zwei Antworten lieferten
  ungültige Timeline-Positionen; Fallback wurde verwendet. Danach keine weiteren
  Modellversuche. Die anschließend ergänzte Positionsableitung ist per Test
  belegt, noch nicht durch einen neuen realen LLM-Aufruf.
- Reales Ergebnis: zwei lokale Quellen → 8.0s H.264 VideoToolbox + AAC;
  Anna-Systemstimme separat als WAV, Originalton während Voiceover abgesenkt.
  ffprobe, Recent-Media-Übergabe Konvertieren/Brennen und Projektladen PASS.
  Video build/director-check/Output/Director_d89759e3_3284f34f.mp4
  SHA-256 f9e031f8960422cf8245e103be3941ff66c223837f4fa046afa0fb08f97357b9
  Voice build/director-check/Audio/Director_d89759e3_60e0d1fc.wav
  SHA-256 8092bb8476faee9e00d0efd4ce91c23b2f5a01d43960799de512c9c258687ded
  Bericht: build/director-check/llm-e2e-result.json; gespeicherter Fallback:
  llm-plan.json, Render-Reproduktion ohne weitere Modellaufrufe: llm-e2e.py.
- Systemstimmen werden ermittelt, Anna nur falls vorhanden bevorzugt, sonst
  andere deutsche Stimme/Systemstandard. Keep/Duck/Mute verfügbar; Duck senkt
  nur innerhalb der tatsächlichen Voiceover-Zeitintervalle ab.
- UI: editierbarer JSON-Plan, Projekte, Audio-/Stimmenwahl, Library-Zugang,
  Ergebnisbuttons nutzen vorhandenes Finder-/Recent-Media-Verhalten.
  Brennanzeige ergänzt DVD-R/RW, DVD+R/RW, CD-R/RW, BD-R/RE; CD-/Blu-ray-
  Authoring ausdrücklich als hier noch nicht angebunden gekennzeichnet.
- Whisper fehlt lokal, Capability/UI deaktiviert, kein Download/Installation.
  Vorhandene Transkriptions-Engine und zeitmarkierte Segmente angebunden und
  gezielt gemockt getestet. Dubbing-Datenmodell/Providergrenze vorbereitet;
  kein Übersetzungsprovider und kein Dubbing-Render vorgetäuscht.
- 76 gezielte Tests PASS; UI-Bridge 0 findings, Node-Syntax PASS. Keine volle
  Suite, kein Computer Use, keine Dependencies/Commits/Push. Offen: realer
  LLM-Plan ohne Fallback nach Positionskorrektur, Whisper mit lokalem Modell,
  Dubbing-Ausführung, Musik-/Soundspuren, Übergänge außer harten Schnitten.

### 2026-09-08 — Gemeinsame Plattform-UI und Settings-Prüfung

- Funktionslose HTML-Fensterknöpfe entfernt. Beide create_window-Wege verwenden
  explizit native Rahmen/resizable; macOS erhält native linke Systemknöpfe,
  Windows behält native rechte. Kein Custom-Bridge-Fensterersatz erforderlich.
  Native Klicks nicht visuell geprüft (kein Computer Use).
- Hartes Windows-11-Label durch Backend-OS-Erkennung ersetzt: macOS-Version
  aus mac_ver, Windows mit tatsächlich gemeldeter Kernel-/Buildversion.
- Extras öffnet jetzt den Settings-Workflow auch von der Startseite aus.
  Datei öffnet vorhandenen Dialog, Hilfe beschreibt reale/experimentelle
  Funktionen. Alle sichtbaren onclick/onchange-Funktionsnamen aufgelöst.
- Settings: Audio/Voiceover und Temp/Preview editierbar, Pfadstatus für vier
  zentrale Benutzerziele, Config, Logs, DB/Recent, Thumbnails und Projekte.
  Output wird für Konvertierung, Rip, Untertitel und Director verwendet;
  Temp für DVD-Arbeit und nun auch Preview, Audio für Extraktion/Voiceover.
  Keine Datenmigration: vorhandene .config/.retrodisc-Datenpfade bleiben gültig.
  Verzeichnis-Preflight prüft absolute Pfade, Dateikonflikte und echte
  Schreibbarkeit. Nur Benutzerziele werden bei Start/Speichern erzeugt,
  niemals Toolpfade. Audio-Ziel fehlte bisher in ensure_directories.
  DVD-Temp wird bei Settings-Änderung an den bestehenden Service weitergegeben.
- Benutzerdefinierte Toolpfade werden beim Start nicht mehr durch PATH-Funde
  überschrieben; Toolstatus nutzt die tatsächlichen Laufzeitpfade. Windows-
  Beispielpfade und unbedingte Whisper-Offline-Behauptung aus UI entfernt.
- Reale Benutzerpfade rein lesend geprüft: derzeit fehlen Media-Zielordner,
  Config, Library und Projekte; Logs existieren. Keine Ordner außerhalb des
  Worktrees erzeugt. Details: build/platform-check/actual-paths.json.
- Lokales FFmpeg bietet scale_vt, transpose_vt und yadif_videotoolbox (Metal).
  4s-Test, 640x360 H.264/AAC: CPU 0.149s, VideoToolbox 0.255s,
  Hardwaredecode+scale_vt+VideoToolbox 0.444s. KEIN belastbarer Benchmark;
  CPU-CRF und Hardware-Bitrate sind nicht qualitätsgleich.
  CPU und bisheriger VT-Weg: ffprobe + vollständiges Dekodieren sauber.
  scale_vt-Output: Metadaten plausibel, aber Decoderfehler. Deshalb keine
  Aktivierung/Änderung der bewährten Encoder-/Fallback-Pipeline.
  Reproduktion/Messwerte: build/platform-check/performance.py, performance.json,
  decode.json. SHA-256 der geprüften Ausgaben:
  CPU b24f80bd83c76eaf1f79e2765ab65538a65f710ad58100a5bf18a75cb76e01ae
  VT ecbc585d9bd4fc3e3cb49780c207e299e62a8d6b624c64f3c6d61ed00665b25e
  scale_vt bc3108aa8daebb5245af8e952c371c551d528e9fdf0f2254b100f8c6d27937ea
- 82 relevante Regressionstests bestanden; 1 fachfremder Whisper-Runtime-Test
  wegen fehlendem faster_whisper ausgeschlossen (erster Lauf: 82 pass/1 fail).
  UI-Bridge 0 findings, Node-Syntax und diff --check sauber. Kein Commit/Push.
  Offen: native manuelle Mac-/Windows-Abnahme und separate Ursachenprüfung des
  experimentellen scale_vt-Ausgabefehlers. Keine Metal-Beschleunigung behauptet.

### 2026-09-08 — Director mit gültiger LLM-Planung, SRT und lokalem Dubbing

- JSON-Schema aus PlanProposal/Pydantic bleibt verpflichtend, anschließend
  Prüfung der echten Asset-IDs/Dauern und Ableitung monotoner Zielpositionen.
  Maximal Primärversuch + eine Reparatur, danach sichtbarer gespeicherter Fallback.
  Prompt-Kontext enthält maximal acht relevante Transkriptsegmente je Asset,
  je 600 Zeichen; vollständiges Transkript bleibt im Asset. Stichworttreffer
  begrenzen den vorgeschlagenen Quellschnitt auf das betreffende Segment.
- Drei bereits installierte Modelle real geprüft: llama3.2:3b gültiger Plan
  im ersten Versuch (6.360s), qwen2.5-coder:3b ebenfalls (22.721s), gemma3:4b
  Fallback nach zwei Versuchen (9.967s). Llama wird in der Director-UI bevorzugt
  vorgeschlagen, explizite Nutzerauswahl bleibt erhalten. Kein Modelldownload.
- UI zeigt Titel, Zieldauer, Story, Quellen, Start/Ende/Ziel, Voiceover und
  Fallback-Hinweis als Text neben editierbarem JSON. Speichern/Neuplanen und
  Rendern bleiben getrennt. Lokale Dubbing-Übersetzung mit anschließender Review.
- Whisper-Diagnose: requirements/setup deklarieren faster-whisper regulär;
  PyInstaller berücksichtigt Paket und vendor/whisper-base. In der verwendeten
  Dev-Python-Umgebung fehlen Paket und lokales Modell, kein Hidden-Import-Fix
  nötig. Kein Test auf optional umetikettiert, keine Installation außerhalb
  des Worktrees. Capability unterscheidet package_missing/model_missing/
  not_configured/available. Director verwendet nachgewiesenen lokalen Modellpfad;
  Faster-Whisper-Verzeichnisse werden local_files_only geladen. Reale ASR offen.
- Segmentdaten erhalten start/end/text/language. SRT nutzt bestehenden
  SubtitleGenerator: Originalsegmente werden auf Schnitte umgerechnet, bei
  Voiceover werden tatsächlich gesprochene Texte/Dauern verwendet. Sidecar-
  Pfad im Projekt und Abschlussereignis; Finder-Button ohne falsche Konvertierung.
- LocalOllamaTranslationProvider prüft lokalen Host, installiertes Modell,
  Schema und Segmentanzahl. Keine Cloud-/Fake-Übersetzung. Dubbing verwendet
  gemeinsamen Director-Renderer mit originalen Startzeiten und Keep/Duck/Mute.
  Sprachsegmente werden höchstens um Faktor 1.25 via atempo beschleunigt,
  sonst verständlicher Fehler. Passende Sprachstimme aus lokalen Fähigkeiten.
  Windows meldet TTS unavailable; kein Apple-Prozess auf Windows.
- Realer 8s-Lauf: Llama-Plan → zwei Videos → deutsche Stimme → Ducking → SRT →
  h264_videotoolbox → ffprobe → Recent Media → Projekt erneut laden PASS.
  Deutsch→Englisch, Ollama-Übersetzung, englische TTS, moderate Tempoanpassung,
  Audio-Mix und 8s-Output ebenfalls PASS. Quelle war das bekannte Skript der
  tatsächlich erzeugten TTS-Spur, ausdrücklich keine Whisper-Erkennung.
- 30s-Test mit vorhandener wiederholter lokaler Fixture, 1280x720, Audio:
  CPU H.264 1.397s / 21.48x Echtzeit / 981482 Bytes;
  VT H.264 1.322s / 22.69x / 2919100 Bytes;
  VT HEVC 1.563s / 19.20x / 3350790 Bytes.
  Alle ffprobe- und vollständigen Decoderprüfungen PASS. Stark synthetisches
  Material; CPU-CRF und Hardware-Bitrate nicht qualitätsgleich, keine allgemeine
  Beschleunigungsbehauptung. scale_vt bleibt deaktiviert.
- Reproduktion/Reports unter build/director-next: models.py/json, e2e.py,
  e2e-result.json, hashes.json. SHA-256 der geprüften MP4:
  Director 08e3fa9ffda517819033bebcb30b3d7d5183f7fe72521b8e53660c90b9cd666e
  Dubbing f2452320d5b3dbf0953b0ee4af584beb3a57fe20f8d09dc54ab99a32ee2e9b22
  CPU30 b2f0a305519fa4bbf1661fdad075da9e0fc5e43777c0d101508db0322dd34edf
  H26430 d3201faa437b84941d26c76d364e1e32a87559400867990be61eee448ceceb47
  HEVC30 63a5acdc71ad516d5a36e95763b2c23c9c27cb78723d93446ed9e0e5cae953ff
- 97 gezielte Regressionstests PASS, 1 fehlende Whisper-Runtime ausgeschlossen;
  danach 7 UI-Tests inklusive neuer Planansicht PASS. UI-Bridge 0 findings,
  Node-Syntax/diff --check sauber. Keine gesamte Suite, keine Commits/Push.
- Restpunkte: reguläre Whisper-Dev-Dependency + lokales Modell bereitstellen,
  echte ASR-End-to-End-Prüfung, Windows-TTS-Provider. Dubbing bleibt Prototyp;
  semantische Übersetzungsqualität muss vor Rendern vom Nutzer geprüft werden.

### 2026-09-09 — Klassischer Video-Restaurations-Prototyp

- Gemeinsame RestorationAnalysis/Options/Plan-Modelle und RestorationProvider-
  Grenze. Bestehende MediaLibrary, Converter, Encoderwahl/Fallback und Queue-
  Completion wiederverwendet; eigener Workflow „Video restaurieren“ im Menü.
- Analyse: echte ffprobe-Metadaten (Codec, Auflösung, DAR/SAR, Framerate,
  Pixelformat, Farbraum/Pegelbereich, Bitrate, Audio), IDÉT-Feldanalyse und
  signalstats über maximal acht Sekunden. Luma-/Chroma-Rauschproxy aus Differenz
  zu schwacher hqdn3d-Filterung; ausdrücklich auch Textur/Bewegung enthalten.
  Verwacklung, Unschärfe, Blockartefakte, Flicker und Audiostörungen bleiben
  unbestimmt statt erfundener Einstufung. Widersprüchliche Field Order bleibt
  unknown und erfordert Nutzerprüfung. Gesamtes Langmaterial nicht analysiert.
- bwdif/yadif send_field erhält bei 576i25 die 50 Bewegungsphasen. Danach
  getrenntes Luma/Chroma/Temporal-Denoise, sehr leichte Farbe, geringe Schärfung,
  optional Lanczos-Skalierung zuletzt. Natürlich/Verbessert/Stark mit Warnung
  vor Detailverlust. Kein KI-Upscale, keine Frame-Interpolation/scale_vt.
- DAR-bewusste Skalierung auf 720p/1080p mit Padding; Originalauflösung lässt
  SAR bestehen. Optional Audio highpass+afftdn, standardmäßig aus. Kein
  automatischer Weißabgleich oder aggressives Histogramm-Stretching.
- libvidstab-Zweipasspfad vorbereitet (smoothing=5, kein Autozoom), aber im
  vorhandenen FFmpeg fehlen die Filter: Checkbox deaktiviert, real ungeprüft.
  QTGMC/VapourSynth nicht verfügbar; weitere KI-/RF-Provider unsupported.
  Szenenparameter/optionale Szenenanalysen speicherbar, noch nicht ausführbar.
- UI: Analyse, Presets, einzeln schaltbare Filter, editierbares JSON, Projekt
  speichern/laden, Original-/Restauriert-Vorschau bis 6s über native Player,
  explizite Renderbestätigung. Ergebnis über vorhandenen Finder-Button und
  Recent-Media-Übergaben an Konvertieren/Brennen/Director/erneute Restaurierung.
- Projekte unter bestehender Library-Datenwurzel/restoration-projects speichern
  Analyse/Plan, Preview/Output, Filter, FFmpeg-Version und SHA-256 von Quelle
  und Derivat. Keine Originalüberschreibung; Namenskollisionen erhalten die
  bestehende Datei. FFV1-Archivmaster/RF-Capture sind nicht implementiert.
- Real: verrauschte 4s-SD-Fixtures in TFF und BFF korrekt erkannt (je 100
  eindeutige Fields); beide → H.264 VideoToolbox 1280x720/50p + Audio. Progressive
  50p bleibt 50p. ffprobe + vollständiges Dekodieren PASS. Cropdetect bestätigt
  4:3-Inhalt 960x720 bei x=160; Audio-/Video-Endzeitdifferenz jeweils 0.0s.
  Vorschau, Projektladen, Recent Media und unveränderte Quellchecksummen PASS.
  Zusätzlich 0.4s/25p ohne Audio auf CPU inkl. Vorschau PASS.
- Reproduktion: build/restoration-check/run.py und extra.py; result.json und
  extra-result.json. SHA-256 der geprüften finalen MP4:
  TFF cd7678743206527199590d6098ff63fea6670d9f1442f41e52814b4844a00736
  BFF 265d663e435e694832e8ed68e1331955ddbb4070ed54fff9d394afa3adb266f2
  Progressive d73af3878b708ac78dcff8bdcbc21a31c4e91d3bf4840b2dfcd0e13a88c689fd
- 63 gezielte Tests PASS (Restoration, Recent, VideoToolbox, Plattform, UI),
  native Playeraufrufe Mac/Windows gemockt; UI-Bridge 0 findings, Node-Syntax
  und diff --check sauber. Keine visuelle Qualitätsabnahme/echte VHS-Aufnahme,
  kein realer Windows- oder libvidstab-Test. Keine Dependencies/Commits/Push.

### 2026-09-09 — Restaurierung: Vorschau- und Quellschutz nachgeschärft

- Vorhandenen Prototyp beibehalten. FFprobe-Bildrate 0/0/N/A verwendet eine
  gültige r_frame_rate; ohne belastbare Angabe klarer Fehler statt Division
  durch null oder erfundener Bildrate. Analysemodell verlangt positive fps.
- Vorschau-Signatur bindet Quellstand, Preset, Filteroptionen und Szenenparameter.
  Nach Änderungen oder gelöschten Preview-Dateien wird eine neue Vorschau
  verlangt. UI startet finalen Render erst nach vorhandener Vorher/Nachher-
  Vorschau und Nutzerbestätigung. Alte Projekte ohne Signatur bleiben ladbar,
  benötigen für die bisherigen Vorschauen eine Neugenerierung.
- Quellgröße/mtime werden auch über Analyse und Verarbeitung hinweg verglichen;
  Änderungen führen zum Abbruch, eigene Derivate werden bereinigt.
- 69 relevante Tests PASS; UI-Bridge 0 findings, JS-Syntax/diff --check sauber.
  Vorhandener echter SD-Test erneut PASS: TFF/BFF 25i → 720p50, progressive
  50p unverändert; Audio, Decoderprüfung, Preview, Projektladen, Recent Media
  und originale Quellchecksummen bestätigt. Keine neue Provider-/Pipeline.
- Aktuelle result.json unter build/restoration-check; SHA-256 finaler MP4:
  TFF 2381472284119fe9e832f5d5b8a80228e0d3c1f82895cd38593238026628cbd8
  BFF acebd7846fa2ffdd38d2168abfed1d4f8cd0eadce556e02e6b850d93f4152820
  Progressive a3192015057bbc21bcb68e1efe0f9a1f3349b72a5eace3f563b089d8c5224677
- Keine Commits/Push. Restpunkte unverändert: reale Band-Qualitätsabnahme,
  Windows-Praxistest, libvidstab-Verfügbarkeit, szenenadaptive Ausführung,
  optionale KI-/Archivmaster-/RF-Provider.

### 2026-09-09 — Szenenadaptive Ausführung fertiggestellt + Smart-Edit-Kern (macOS-Beleg)

Fortsetzung des unterbrochenen Codex-Stands (szenenadaptive Restauration). Der
Renderer wendet Szenenparameter jetzt tatsächlich an; zusätzlich neu: Report
nach Missionsvorgabe, Batch, sowie ein deterministischer Smart-Edit/Short-Kern.
Umgebung: macOS 15.6 (Apple Silicon), Homebrew **ffmpeg 8.1.1**, Python 3.11
in `.venv-test` (nur pydantic/pytest/pytest-asyncio/pytest-mock/structlog/rich/
click/httpx — keine schweren ML-Pakete). Keine Commits/Push/Branches.

**Restauration (Missionen 1–5, 7, 23, 24, 26) — realer FFmpeg-Beleg, keine Mocks:**
Reproduzierbar über `scripts/restoration_acceptance.py` (erzeugt Testmedien,
fährt Analyse→Szenenanalyse→adaptiven Render→Report→Archiv, dekodiert jede
Ausgabe mit `-xerror`, prüft Dauer/Streams/SHA). Lauf `/tmp/retrodisc-accept`,
GESAMT PASS:
- `filters()` erzeugt pro Szene `hqdn3d`/`unsharp` mit `enable='gte(t,s)*lt(t,e)'`.
  30s-Video: 3 Szenen erkannt, 1 dunkle Szene → stärkeres Denoise
  `1.2:2.8:1.5:3.0` vs. helle `0.7:1.5:1.0:2.0`; 6 szenengesteuerte Filter aktiv.
  Ausgabe 1280x720/25p, 30.0s, Audio, vollständiges Decoding PASS. Quell-SHA
  625715ce… unverändert; Ausgabe-SHA 50fe5d19….
- TFF/BFF 576i → 720p: field_order tff/bff, Deinterlace an, Ausgabe dekodiert,
  Quell-SHA unverändert (6afe3e62…, 3d78d217…). Progressive SD nicht deinterlaced,
  720x576 erhalten.
- Report neu (`Restoration.build_report`, Mission 3): Sektionen source/analysis/
  processing/result/integrity; nur gemessene Fakten, keine erfundenen Scores.
- Archivmaster (Missionen 4/5): FFV1 + pcm_s24le, 30.0s, vollständiges Decoding,
  Manifest-SHA cfd12f27… == Datei-SHA, `-map_metadata -1`, Quelle unverändert.
- Performance (Mission 26, VideoToolbox): 30s adaptiver Render 4.99s; Archiv 2.56s;
  4s-Läufe ~1.0–1.2s. `scale_vt` bleibt aus.
- Batch (Mission 7, neu): `Restoration.batch()` + Launcher `restoration_batch`.
  Lauf über [TFF, kaputte Datei, progressive] → 2 done / 1 error, Fehler stoppt
  die Queue nicht, beide Ausgaben dekodieren; Originale nie überschrieben.

**Smart Edit / Short (Missionen 9–19, 22, 25) — neuer deterministischer Kern:**
`src/models/smart_edit.py` (SmartEditProject, CaptionStyle, ReframeSettings,
SilenceSettings, VoiceEnhanceSettings, TimeRange) + `SmartEditor` in
`src/services/smart_edit.py`; Launcher `smart_edit_short/_capabilities/_project`;
LLM-Wiederverwendung über `Director.select_time_ranges` + `Assistant.highlight_ranges`.
Reproduzierbar über `scripts/smart_edit_acceptance.py`, GESAMT PASS:
- 20s-Quelle mit echter Sprechpause 6–10s. Short-Lauf: Highlight-Fallback →
  Sprechpausen kürzen (silencedetect) → Center-Reframe 9:16 → Voice-Enhance →
  (Captions) → H.264/AAC. Ausgabe **1080x1920**, Audio, vollständiges Decoding,
  geschnittene Segmente [2.5–6.15, 9.85–17.5] (Pause getrimmt), Dauer 11.4s,
  Projekt-Reload PASS.
- **Ehrliche Grenze:** Homebrew-ffmpeg 8.1.1 ist **ohne libass** gebaut
  (`ffmpeg -buildconf` bestätigt), daher kein `subtitles`-Filter. Captions wurden
  kapazitätsgesteuert übersprungen (`captions_burned:false` + Notiz), **nicht
  gefälscht**. ASS-Erzeugung (`build_ass`) ist rein unit-getestet; der Burn-Pfad
  ist auf einem libass-fähigen Build (Windows-Vendor gyan.dev) noch praktisch
  zu verifizieren.
- Mission 15 (SubjectTracker) nur Architektur (`level:'unavailable'`); Reframe
  V1 = stabiler Center-Crop, keine vorgetäuschte Personenverfolgung.
- Mission 18 (Ducking): keep/duck/mute im Modell; echtes Ducking lebt weiterhin
  im Director. Im Ein-Quellen-Short ist `duck` mangels zweiter Spur wie `keep`.

**Tests/Gates:** `tests/test_restoration.py` 24 PASS (3 neu: build_report,
collect_sources, batch), `tests/test_smart_edit.py` 19 PASS (neu). Gesamtsuite
`pytest -q`: **470 passed, 17 skipped, 4 failed**. Die 4 Fehler sind
umgebungs-/plattformbedingt und **nicht** von dieser Arbeit verursacht:
`test_core_flows` (faster-whisper/`requests` nicht im Test-venv), 2×
`test_installer` (Windows-`%APPDATA%`-Pfade unter macOS), `test_drive_detection_ui`
(Node-Ausführung eines `app.html`-JS-Snippets in Codex' noch offener Disc-Copy-
Arbeit; `app.html` wurde hier nicht verändert). `verify_ui_bridge.py` PASS
(0 findings, 63 Bridge-Methoden), `node --check` OK, `git diff --check` sauber,
`compileall` sauber.

**Offen (echte Punkte):** Caption-Burn auf libass-Build; UI-Panels für Batch/
Short in `app.html`; LLM-Highlight-Lauf gegen laufendes Ollama; realer
Windows-/libvidstab-Test; optionale KI-/RF-Provider. Detaillierte Übergabe:
`HANDOFF_2026-09-09_SzenenAdaptiv_SmartEdit.md`.

### 2026-09-09 (Teil 2) — UI für Smart-Edit/Short + Batch/Archiv, Ollama-Realtest, Testklärung

Fortsetzung: die offenen Punkte aus Teil 1 abgearbeitet. Umgebung wie oben
(macOS, ffmpeg 8.1.1, `.venv-test`). Keine Commits/Push/Branches.

**UI in `src/ui/app.html` (Missionen 1–4, 6–8, 20, 21):**
- Neues Panel `tab-short`: Quelle wählen/Recent übernehmen, 15/30/60 s, 9:16/1:1/16:9,
  Highlights, Sprechpausen (Aus/Natürlich/Straff/Kompakt), Fülllaute, Untertitel
  (Aus/Normal/Modern), Sprache verbessern (Aus/Natürlich/Klar/Stark), Audio
  keep/duck/mute, Exportprofil, „Short erstellen", Fortschritt, Ergebnis mit
  Buttons Finder/Konvertieren/Brennen/KI-Regisseur. Nutzt ausschließlich die
  vorhandene Bridge (`smart_edit_short/_capabilities/_project`), keine zweite Logik.
- Restore-Panel erweitert: Archiv-Sektion („Archivkopie erstellen" → neuer Bridge
  `restoration_archive`, Ergebnis zeigt Archivmaster/Manifest/SHA256/Original
  unverändert) und Batch-Sektion (Dateien/Ordner, Liste mit Status, Presets
  Natürlich/Verbessert/Stark, Szenenadaptiv, `restoration_batch`).
- Caption-Capability sauber vor dem Rendern (Mission 4): `smart_edit_capabilities`
  meldet `captions` (libass). Fehlt libass, werden Normal/Modern deaktiviert +
  Hinweis; „Untertiteldatei (SRT) erstellen" bleibt über `generate_subtitles`.
  Kein Fehler erst beim Rendern. Tests für beide Zustände
  (`test_capabilities_enable_caption_burn_only_with_libass`).
- Startseite gruppiert (Mission 6): fünf Medien-Aktionen oben; sekundär gruppiert
  in Erstellen (KI-Regisseur, Short) / Retten (Restaurieren) / Werkzeuge. Neue
  Toolbar-Buttons Short + Restaurieren. Handoffs verdrahtet: Restoration→Short,
  Short→Konvertieren/Brennen/KI-Regisseur.
- Archivmaster wird NICHT in Recent Media beworben: der Job setzt bewusst keine
  `output_paths`; die UI erhält die Archivinfo separat über das `job_done`-Event
  (`_on_complete` reicht `archive`/`batch_summary` durch).
- UI-Zustände (Mission 7): null-`api()`-Guards, Job läuft/erfolg/fehlgeschlagen,
  Ollama offline, Caption-Burn nicht verfügbar, Ausgabe verschwunden
  (`useRecentMedia` prüft erneut). `node --check` sauber, `verify_ui_bridge`
  PASS (0 findings, 64 Bridge-Methoden).

**Ollama-Highlight-Realtest (Missionen 5, 11), `scripts/ollama_highlight_realtest.py`:**
- Lokales Ollama erreichbar, Modell `llama3.2:3b`. 40s-Asset + Transkript, Wunsch
  „interessanteste 15 s". LLM lieferte reale Segmente [10–16, 20–26, 30–37];
  `all_within_duration`=true, `no_invented_times`=true; echter Short 1080x1920,
  19.12s, vollständiges Decoding. Genau ein LLM-Versuch, dann Fallback.
- Offline (unerreichbarer Host): deterministischer Fallback [12.5–27.5], Short
  15.02s, vollständiges Decoding. GESAMT PASS.
- Beim Aufbau ein Fehler NUR im Testskript gefunden (2-Tupel statt (start,end,text)-
  Tripel an `Director.select_time_ranges`); Produktpfad nutzt Tripel und ist korrekt.

**Testklärung (Mission 9) — Herkunft und Einzelbewertung:**
Alle Zahlen stammen aus EINEM Lauf `.venv-test/bin/python -m pytest -q`. Vorher:
475 passed / 17 skipped / 4 failed. Nachher: **476 passed / 19 skipped / 1 failed**.
- `test_drive_detection_ui::…medium_confirmation…`: **behoben.** Ursache war eine
  Lücke im Node-Test-Harness (rief `refreshQueue`, das `finalOutputPaths` nutzt,
  ohne es im Stub bereitzustellen → ReferenceError vom eigenen `catch{}`
  verschluckt → `jlist.innerHTML` blieb undefined). Das echte UI-Verhalten war
  korrekt (nachgewiesen). Fix: `finalOutputPaths` extrahiert + `escHtml/escAttr/
  revealOutputButton`-Stubs ergänzt. Kein künstlicher Skip. → jetzt 5/5 PASS.
- `test_installer::…every_shortcut…` und `…start_menu_folder_recursively…`:
  **echt Windows-only.** `_removal_plan` nutzt `os.path.expandvars`, das `%APPDATA%`
  nur unter Windows auflöst; die 5 Geschwister-Parse-Tests laufen plattformüber-
  greifend, diese zwei nicht. Gleicher `skipif(sys.platform!='win32')` wie der
  bereits vorhandene Schwester-Ausführungstest (Zeile 186) ergänzt — Konsistenz,
  kein Green-Washing; auf Windows laufen sie weiter.
- `test_core_flows::…whisper…importable`: **fehlende optionale Runtime.** Der Test
  ist ein Packaging-Guard (`import requests`, `import faster_whisper`). Das schlanke
  macOS-Dev-venv installiert die schwere ML-Runtime bewusst nicht; im echten
  Windows-Build-venv importierbar. Bewusst NICHT geskippt (das würde den Zweck des
  Guards zerstören). Einziger verbleibender, umgebungsbedingter Fehler.

**Acceptance nach allen Änderungen (Mission 11):** `restoration_acceptance.py`
GESAMT PASS (30s adaptiv erneut 3 Szenen/1 dunkel, 4.95s), `smart_edit_acceptance.py`
GESAMT PASS (1080x1920, Audio, Decoding, kept 11.3s), Ollama-Realtest PASS. Alle
Ausgaben mit ffprobe + `-xerror`-Volldecode geprüft.

**Gates:** `verify_ui_bridge` PASS (0 findings), `node --check` OK, `compileall`
sauber, `git diff --check` sauber. Backend-Kern: `test_restoration` 24,
`test_smart_edit` 24 PASS.

**Offen:** Caption-Burn praktisch auf libass-fähigem (Windows-)ffmpeg; realer
Windows-/libvidstab-Test; optionale KI-/RF-Provider. Handoffs sind auf Bridge-/
UI-Ebene verdrahtet; ein echter Klick-Durchlauf braucht die laufende WebView.

### 2026-09-09 (Teil 3) — Produktionsreife: Whisper-ASR, Dubbing, Diagnose, Packaging

Umgebung wie zuvor (macOS, ffmpeg 8.1.1, `.venv-test`). Keine Commits/Push/Branches.
Ergebnis vorweg: `pytest -q` = **480 passed / 19 skipped / 0 failed**.

**Whisper-Runtime (Mission 1):** `faster-whisper` ist laut Architektur PFLICHT
(requirements.txt, setup.py install_requires, build.py RUNTIME_DEPS, Spec bündelt
faster_whisper+ctranslate2+tokenizers+huggingface_hub+av+numpy + vendor/whisper-base).
Die vorgesehene Dependency (`faster-whisper`+`requests`) NUR ins Dev-/Test-venv
installiert (keine alternative ASR). Packaging-Guard-Test grün.

**Echte ASR (Missionen 2/3), `scripts/whisper_asr_realtest.py` — GESAMT PASS:**
Kleinstes Modell `tiny` einmalig lokal (~4 Dateien, offline danach). Echte deutsche
Sprache via `say`. A) SubtitleGenerator: Sprache=de erkannt, 3 Segmente start/end/text,
SRT mit Timecodes, ASR 2.1s. B) Director.transcribe: Video→Audio-Extraktion→ASR→
Transcript→Projekt speichern/neu laden. C) Smart Edit mit ECHTEM ASR (keine
vorgegebenen Segmente): Short 1080x1920, 10s, Audio, Volldecode.

**Echtes Dubbing (Mission 4), `scripts/dubbing_realtest.py` — GESAMT PASS:**
DE-Video → Whisper (de) → Ollama-Übersetzung EN (`llama3.2:3b`) → `say`-TTS →
Ducking → EN-Video (Volldecode, Audio, generierte Sprachspur, SRT mit Inhalt).
Gegenprobe EN→DE akkurat. Echter Produkt-Schutz bestätigt: >25% TTS-Beschleunigung
wird verweigert (kurze Clips brauchen Zeitfenster-Headroom).

**App/JS-Smoke (Mission 5), `tests/test_ui_smoke.py`:** Node-Harness führt die
ausgelieferten Panel-Funktionen (loadShortUI/applyCaptionCapability/shortShowResult/
batchRenderList/batchOnDone/archiveShowResult) ohne JS-Runtime-Fehler aus; Caption-
Capability wirkt in beiden Zuständen korrekt auf die UI.

**Capability-Dashboard (Mission 12):** neuer Bridge `diagnostics()` + Diagnose-Panel
in den Einstellungen. Ehrliche Aggregation echter Detektion (FFmpeg/FFprobe/yt-dlp,
Ollama, Whisper, TTS, Hardware-Encoder, libass, libvidstab, QTGMC/Real-ESRGAN/…);
Status available/unavailable/optional/model_missing. Test `tests/test_diagnostics.py`.

**Cleanup/Security/Pfade (Missionen 7/10/21):** Alle Temp-Verzeichnisse nach den
Läufen leer (keine verwaisten Clips/WAV/AIFF/concat-Listen; TemporaryDirectory).
KEIN `shell=True` in src/scripts/launcher; alle Subprozesse als Argumentlisten über
`create_hidden_subprocess`/`subprocess.run`. Edge-Case-Pfad
`Te st (ä ö ü ß 🎬) 'quote' [v1].mp4` durch Restoration- UND Short-Render, beide
dekodieren (`scripts/edgecase_paths_realtest.py` PASS). Kein hardcodierter User-/OS-Pfad
in neuem Code.

**Output-Kollision (Mission 9):** Restoration/Short lehnen vorhandene Ziele ab
(FileExistsError, eindeutige uuid-Namen), Archiv nutzt `open('x')`/`-n`, Batch
eindeutige Namen. Regressionstest vorhanden.

**Packaging (Missionen 13-18):** `retrodisc_final.spec` um `collect_submodules("src")`
ergänzt — die vielen LAZY im Launcher importierten Module (restoration, director,
translation, voice, smart_edit + deren Modelle, utils) fehlten in `hiddenimports`
und hätten im Paket gecrasht. Verifiziert via identischem `pkgutil.walk_packages`:
alle 40 src-Submodule inkl. der zuvor fehlenden werden erfasst. PyInstaller ist auf
dem Mac nicht installiert und der Spec ist Windows-only (verlangt `vendor/ffmpeg.exe`,
sonst `sys.exit`); ein echter macOS-.app-Build ist hier NICHT möglich und wurde NICHT
vorgetäuscht. Neue Services erben die Tool-Auflösung über die gemeinsame FFmpeg-Instanz
(settings.tools), keine neue Shell-PATH-Annahme. Modelle liegen im vorgesehenen
Vendor-/User-Data-Pfad (nicht im beschreibbaren Bundle).

**Performance (Mission 19, VideoToolbox):** Restoration 30s adaptiv ~4.95s, Short
~1.4s, Dubbing (inkl. ASR+LLM+TTS) End-to-End im niedrigen Sekundenbereich; Whisper
tiny 2.1s. Große Dateien: FFmpeg-Streaming, Prüfsummen in 1-MB-Blöcken, Transkript-
kontext fürs LLM begrenzt — kein Vollladen in RAM.

**Tests (Mission 24):** EIN Lauf `.venv-test/bin/python -m pytest -q` →
**480 passed, 19 skipped, 0 failed**. Neu u.a. `test_ui_smoke` (2), `test_diagnostics` (1),
Caption-Capability (1). Gates: `verify_ui_bridge` PASS (0 findings, 65 Bridge-Methoden),
`node --check` OK, `compileall` sauber, `git diff --check` sauber. Keine künstlichen Skips.

**Offen (echte Restpunkte):** Caption-Burn praktisch auf libass-fähigem (Windows-)ffmpeg;
echter macOS/Windows-Paket-Build auf dem Build-Rechner; libvidstab (advanced),
optionale KI-/RF-Provider; Klick-Durchlauf in laufender WebView.

### 2026-09-09 — Echter macOS-Bundle-/WebView-Abnahmelauf

- Gemeinsamer Launcher als `RetroDisc.app` gebaut; separater macOS-Spec, Windows-Spec erhalten.
- Packaging-Fixes: eigenständiges yt-dlp ohne System-Python; multiprocessing.freeze_support gegen erneuten GUI-Start durch Whisper.
- Bundle-Tools mit minimalem PATH, echte offline deutsche ASR (3 Segmente), Modell-fehlt-Capability, Cocoa-WebView/JS-Bridge, Convert → Recent → Konvertieren/Brennen/Director PASS. Vollständiger Decode PASS.
- Verschobene App (Leerzeichenpfad) einschließlich ASR PASS. 121 Mach-O-Dateien ohne externe Homebrew-/Dev-Abhängigkeiten; Ad-hoc-Signatur gültig.
- Hauptprogramm SHA-256 `f7739c9b3e97ac03e2324302dc1ae7e2af4f7a9317ff92041b588fe8393553da`; vollständige Artefakt-Hashes/Belege in `build/macos-release`. Details/Reproduktion: `MACOS_RELEASE_READINESS.md`.
- Regression 483 passed / 19 skipped / 0 failed; abschließend 46 gezielte Tests PASS; Bridge/JS/compileall/diff-check PASS.
- Keine Distributionsfreigabe: Developer-ID/Notarisierung und Windows-Praxistest offen; Caption-Burn ohne libass nicht verfügbar. Keine Commits/Push.
- Gatekeeper separat real geprüft: `spctl --assess --type execute` → rejected (Exit 3); Ad-hoc-Signatur genügt nicht für Distributionsfreigabe.

### 2026-09-09 — Windows static package / final release matrix

- Windows-Spec behalten; ASR-Pflichtpakete schlagen bei fehlender Runtime/Collection jetzt früh fehl. Shared Services/Package-Check via collect_submodules geprüft. Windows-Vendor-EXEs hier nicht vorhanden: sämtliche Windows-FFmpeg-Capabilities/Caption-Ausführung NOT TESTED.
- LOCALAPPDATA-Umleitung für Windows-Settings korrigiert; Windows-TTS ehrlich unavailable ohne Apple-Providerlabel. Package-Check prüft frozen/UI/Shared Imports/Whisper-Runtime.
- Plattformneutraler Caption-Burn-Harness: echte Quelle/SRT, Burn-in, FFprobe, Volldecode, sichtbarer Textkontrast; macOS-Build ohne libass meldet CAPABILITY_UNAVAILABLE.
- Release-Staging ignoriert Artefakte; nachvollziehbare Build-/Signier-Anleitungen und Matrix unter release/reports/READINESS.md. Keine gültigen sichtbaren Apple-Signieridentitäten, keine Notarisierung/Umgehung.
- Finaler macOS-Staging-Build erneut Package-ASR/WebView/Handoffs/Decode PASS, 121 Mach-O-Dateien ohne externe Dev-/Homebrew-Bibliotheken, Ad-hoc-Signatur gültig. Hashbindung und Größenmessung in Release-Bericht.
- Neue release-Artefakte führten zunächst zur Sammlung upstream NumPy-Tests; pytest.ini ignoriert ausschließlich release/. Abschließend 487 passed / 19 skipped / 0 failed. Bridge/JS/compileall/diff-check PASS.
- LOCAL DEVELOPMENT YES; PUBLIC DISTRIBUTION NO (Developer-ID/Notarisierung, echter Windows-Build/Vendor-Caption-Test fehlen). Keine Commits/Push/neuer Branch.

### 2026-09-09 (Teil 4) — Timeline-Fortsetzung: Undo/Redo, Render, Transitions, Slideshow/Musik

Fortsetzung exakt an Codex' Timeline-Stand (edit() auf ProductionPlan, client-seitige
Timeline-UI). Umgebung wie zuvor. Keine Commits/Push/Branches. Ergebnis:
`pytest -q` = **497 passed / 19 skipped / 0 failed**.

- **Undo/Redo (Mission 1):** Server-seitige `TimelineHistory` (Snapshot-basiert,
  begrenzt, Redo-Zweig-Verwerfung, kein Event-Sourcing, keine Mediendatei berührt)
  in `src/services/timeline.py` + 5 Tests. Client-seitige Undo/Redo-Buttons von Codex
  waren nie deaktiviert → `timelineUpdateButtons()` ergänzt: Buttons disabled, wenn
  Stack leer; Aufruf in draw/apply/undo. Smoke-Test `test_ui_smoke` deckt beide Zustände.
- **Timeline-UI (Mission 2):** von Codex weitgehend fertig (Video/Audio/Voiceover/
  Caption/Music-Tracks, Trim/Split/Move/Delete, Transition/Zoom-Selects, auto-Refresh);
  nur Button-Gating-Lücke behoben.
- **Timeline-Render real (Mission 3), `scripts/timeline_render_realtest.py` PASS:**
  2 Videos → Trim/Split/Move/Delete + Undo/Redo (echt gefahren) → Director.render →
  1280x720, Dauer = Summe der Clips, Video+Audio, Volldecode.
- **Transitions (Mission 4/5):** im Renderer bereits umgesetzt (cut/fade/dip_black via
  fade-Filter, Zeilen 277-280). Acceptance im selben Skript: fade (8s) + dip_black,
  beide Volldecode PASS. (Echtes xfade-Crossfade nicht im Modell — offener Punkt.)
- **Bilder/Ken-Burns/Slideshow/Musik (Missionen 6-11), `scripts/slideshow_realtest.py`
  PASS:** 3 echte Bilder (png/jpg) + mp3-Musik → image→video (loop), zoompan
  (Ken Burns subtle), fade-Transition, Musik-Mix (afade/adelay/amix) → **H.264/AAC**,
  9.0s, Volldecode. Bild-Assets (kind='image'), image→video und Musik-Mix waren von
  Codex im Modell (`AudioPlacement`) + Renderer umgesetzt; hier erstmals real belegt.
- **Recent-Media-Fix (Missionen 6/22):** `recent_outputs()` klassifizierte Bilder als
  „disc"; jetzt `image`. `asset()` war bereits korrekt.
- **Audio/Originalton (Mission 12):** Renderer wendet `original_audio` keep/duck/mute +
  `original_volume` an (Slideshow mit mute belegt).

**Tests/Gates:** EIN Lauf → 497 passed / 19 skipped / 0 failed. Neu: `test_timeline`
(9, davon 5 Undo/Redo), `test_ui_smoke` Timeline-Button-Gating. Eine durch Codex'
parallele `app.html`-Änderung entstandene Regression behoben (`directorSummarizePlan`
rief `timelineDraw` unbedingt → im isolierten Escaping-Test undefiniert; jetzt
`typeof`-Guard). `verify_ui_bridge` PASS (0 findings), `node --check` OK, `compileall`
sauber, `git diff --check` sauber.

**Offen (echte Restpunkte):** xfade-Crossfade (Modell hat cut/fade/dip_black);
Waveform-Track (Mission 13), Director 2.0, Restoration-Pro-UI-Details, Drag&Drop,
als eigenständige spätere Blöcke; Windows-Praxistest/Vendor-libass-Caption.

**Git-Checkpoint (Mission 33) — GEPUSHT:** Checkpoint-Commit `ffbf63c` (Parent
`44af8d2`; reiner Quellcode, 69 Dateien, keine Binaries/Medien/Modelle/venv) per
Fast-Forward auf `origin/crossplatform-2026` gepusht (`44af8d2..ffbf63c`, kein Force,
keine Divergenz). Nach `gh auth login` (github.com/Mulchen1984, HTTPS, osxkeychain)
gelang der zuvor an fehlenden Credentials gescheiterte Push. Verifiziert:
`HEAD` == `origin/crossplatform-2026` == `ffbf63c`. Diese Doku-Aktualisierung folgt als
separater Commit.

### 2026-09-09 (Mission 35) — Echte gecachte Audio-Wellenform in der Timeline

Ausgangspunkt `9c55f58`, sauberer Baum. Umgebung wie zuvor (macOS, ffmpeg 8.1.1,
`.venv-test`). Pfad: Mediendatei → ffmpeg-PCM (mono, dauerabhängige Rate) →
Peak-Buckets → Disk-Cache (Datei+mtime+size) → Timeline-UI schneidet clientseitig
pro Clip. Keine zweite Timeline-Architektur; Codex' `edit()`/Undo-Redo unverändert.

**Backend** `src/services/waveform.py` (`Waveform`): echte Max-abs-Peaks aus dem PCM
(numpy, Fallback `array`); Rate = clamp(2_000_000/Dauer, 200..8000 Hz) begrenzt
Speicher (≤ ~4 MB), Analyse in `asyncio.to_thread` (blockiert die UI nicht).
Disk-Cache pro Datei+mtime+size+buckets; kein erneutes Analysieren derselben Datei.
`peaks()` liefert kompakt `{has_audio,duration,peaks[≤buckets],rate}`; kein Vollladen
nach JS. `slice_window()` schneidet das Clip-Fenster [start,end].

**Bridge/UI:** `timeline_waveform(asset_path)` (+Api-Proxy). Client lädt Peaks EINMAL
je Asset (`S.waveformCache`), schneidet clientseitig pro Clip → Trim/Split/Move/
Delete/Undo/Redo bleiben synchron ohne Reanalyse, kein Polling. SVG-Balken im
vorhandenen Timeline-Stil, Originalton (blau) und Voiceover (grün) per Legende
unterscheidbar; Clip ohne Audio zeigt „kein Audio"; Caption-Track unverändert.

**Cache-/Peak-Strategie:** buckets-Standard 1600 (Quelle) → UI-Slice je Clip; Peakzahl
hart durch `buckets` begrenzt; Rate dauerabhängig; JSON pro Quelle wenige KB.

**Reale Tests** (`tests/test_waveform.py`, echtes ffmpeg): Video mit Audio →
variierende Peaks; **Anti-Dummy-Test**: laute Hälfte > 2× leise Hälfte (schlägt bei
konstanten/Dummy-Peaks fehl); Video ohne Audio → sauberer No-Audio-Zustand, kein
Fehler; reine Audiodatei → Peaks; Cache-Wiederverwendung ohne Reanalyse (2. Aufruf
mit unbrauchbar gemachtem ffmpeg liefert Cache); Peakzahl ≤ buckets; Dateiname mit
Leerzeichen+Umlauten. UI-Smoke (`tests/test_ui_smoke.py`): `slicePeaks`/`waveformSvg`
— Trim = Teilfenster [2.5,5]→25 Peaks, Split = 50/50, No-Audio→leer, echte `<rect>`.

**Regressionen geprüft (unverändert PASS):** Timeline-Render (2 Videos, Trim/Split/
Move/Delete+Undo/Redo), Transitions fade/dip_black (real), Originalton keep/duck/mute
+ `original_volume`, Voiceover, Captions, Recent Media — 88 gezielte Tests + realer
`timeline_render_realtest.py` GESAMT PASS.

**Tests/Gates:** `pytest -q` = **505 passed / 19 skipped / 0 failed**. `verify_ui_bridge`
PASS (0 findings, 67 Bridge-Methoden), `node --check` OK, `compileall` sauber,
`git diff --check` sauber. Keine künstlichen Skips.

**Verbleibende Risiken:** Timeline hat (noch) keinen horizontalen Zoom-Regler — die
SVG-Wellenform skaliert mit der Clip-Zeilenbreite (`preserveAspectRatio=none`), Sync
bleibt proportional; ein späterer Zoom müsste nur die Zeilenbreite ändern. Peaks sind
absolute Full-Scale-Werte, die UI skaliert je Clip auf das eigene Maximum (Form gut
sichtbar, Lautheitsvergleich zwischen Clips nicht 1:1). Sehr lange Dateien werden mit
niedrigerer Rate analysiert (Overview-Genauigkeit, gewollt).

### 2026-09-09 — Optical-Media-Workbench: P0/P1-Kernmodule (Windows-only)

Ausgangspunkt `4d99c39`, sauberer Baum. Fokus: wenige vollständige, getestete
Komponenten statt vieler Stubs. Windows-only, keine DRM-/Kopierschutz-Umgehung,
keine Hardware-Behauptungen (alle Tests mit Mocks/synthetischen Strukturen).

**Neu (rein, ohne Hardware testbar):**
- `src/core/errors.py` — typisierte Fehler (Drive/Media/Probe/Read/Encode/Authoring/
  Burn/Verify/ExternalTool) mit stabilem `code`, Nutzertext + `detail` (für Logs).
- `src/services/booktype.py` — Medienklassifikation (DVD±R/RW/DL, BD, ROM),
  Bitsetting-Capability (Medium UND Backend, nie blind), Book-Type-Kommando,
  Result-Parsing, `BurnResult`, `describe_media()` (reichert `get_disc_info` an).
  **Verdrahtet**: Launcher `get_disc_info` liefert jetzt `media_type` +
  `book_type_options` je nach echter `dvd+rw-booktype`-Präsenz.
- `src/services/disc_copy.py` — explizite Copy-State-Machine mit den kritischen
  Garantien: Quelle nie Ziel, frische/eindeutige Zielerkennung, wieder-eingelegte
  Quelle abgelehnt, nicht-beschreibbar/nicht-leer/zu-klein abgelehnt, Cancel in
  jeder Phase, temporäres Abbild für Cleanup vermerkt, Fehler → definierter
  Terminalzustand.
- `src/services/fingerprint.py` — reihenfolgeunabhängiger, NFC-unicode-sicherer
  Disc-Fingerprint über normalisierte Struktur (nur kleine Strukturdateien gehasht).
- `src/services/main_movie.py` — lokale Hauptfilm-Heuristik mit Konfidenz + Gründen;
  konservativ bei Serien/gleich-langen Titeln und Unterlänge.

**Zielarchitektur-Mapping:** vorhandene `DiscTools` (create_iso/burn_iso/verify_iso/
get_disc_info) bleibt der reale FFmpeg-/growisofs-Pfad; die neuen Module ergänzen
BurnService-Optionen (Book Type), Copy-Statemachine, DiscFingerprint- und
MainMovie-Heuristik lose gekoppelt. Kein zweites Job-System: bestehende
`JobState`/`Pipeline` bleiben; die Copy-Machine ist die geführte Sequenz.

**Release-Readiness-Matrix (ehrlich):**

| Komponente | Implementiert | Auto-getestet | Hardware-getestet | Release-ready | Notiz |
|---|---|---|---|---|---|
| Typed errors | JA | JA | – | JA | reine Bibliothek |
| Book type / bitsetting (Logik) | JA | JA | NEIN | NEIN | echter Brenner nötig |
| Book type in get_disc_info | JA | JA (pure) | NEIN | NEIN | echte Disc/Brenner nötig |
| Disc-Copy-State-Machine | JA | JA | NEIN | NEIN | reale Zwei-Laufwerk-Kopie offen |
| Disc fingerprint | JA | JA | – | JA | strukturbasiert |
| Main-movie-Heuristik | JA | JA | NEIN | teilw. | echte Disc-Titel zum Feinschliff |
| DVD→ISO / burn_iso (Bestand) | JA | JA | NEIN | NEIN | physischer Test erforderlich |
| Waveform-Timeline | JA | JA | – | JA | siehe eigener Block |

**Tests/Gates:** `pytest -q` = **557 passed / 19 skipped / 0 failed** (+52 neu:
booktype 22, disc_copy 16, fingerprint 7, main_movie 7). `verify_ui_bridge` PASS
(0 findings), `node --check` OK, `compileall` sauber, `git diff --check` sauber.

**Offen/Blocked:** Physische Brenn-/Kopier-/Book-Type-Verifikation braucht echte
Laufwerke+Medien (Hardware-blockiert); Windows-Praxistest; DriveInspector-
Capability-Parsing, Verify-Ergebnismodell-Ausbau und Disc-Health als nächste Schritte.

### 2026-09-09 — Workbench Folgeschritte: Verify, Book-Type-Brennpfad, DriveInspector

Fortsetzung (Next-best-Tasks 3→2→1). Windows-only, keine DRM-Umgehung, keine
Hardware-Behauptungen. `pytest -q` = **593 passed / 19 skipped / 0 failed** (+36).

- **VerifyService** (`src/services/verify.py`): `VerifyResult` mit PASS/
  PASS_WITH_WARNINGS/FAIL/NOT_AVAILABLE + reine Prüfungen (Größe/Hash/Struktur/
  Book-Type) und ehrlicher Aggregation. `DiscTools.verify_iso_result()` verpackt
  das vorhandene `verify_iso` strukturiert (Hardware-Pfad unverändert). 10 Tests.
- **Book Type im Brennpfad** (`DiscTools.burn_iso_result()`): setzt DVD-ROM-Book-Type
  nur wenn Medienfamilie UND `dvd+rw-booktype`-Backend es können, brennt über das
  bestehende `burn_iso`, liest den tatsächlichen Book Type zurück und liefert einen
  `BurnResult` (Größe, Speed, Verify, Warnungen). Ehrliche Warnung statt Vortäuschen.
  5 Orchestrierungstests (gemockt, ohne Hardware).
- **DriveInspector** (`src/services/drive_inspector.py`): robuster, reiner
  Capability-Parser (Vendor/Model/Firmware, DVD±R/RW/DL, BD-R/RE/XL, Write-Speeds)
  aus `dvd+rw-mediainfo`/INQUIRY; tolerant gegen leer/Garbage/Unicode/Locale, nimmt
  nie eine Fähigkeit an. `DiscTools.inspect_drive()` + Bridge `inspect_drive` (+Proxy).
  10 Tests inkl. gemocktem Subprozess + fehlendem Werkzeug. **Nur Erkennen, keine
  Firmware-Änderung.**

Readiness-Matrix aktualisiert: Verify-Modell/Book-Type-Logik/DriveInspector-Parser =
implementiert + auto-getestet; realer Brenn-/Book-Type-/Drive-Report weiterhin
Hardware-blockiert (physischer Test erforderlich). Gates: `verify_ui_bridge` PASS
(0 findings), `node --check` OK, `compileall` sauber, `git diff --check` sauber.

### 2026-09-09 — Disc-Health-Datenmodell (Mission 14, vorbereitet)

`src/services/disc_health.py`: Read-Policy-Eskalation (Normal→Retry→ReducedSpeed→
MultipleRead→SectorCompare), `DiscHealthReport` + `DiscHealthAccumulator`, ehrlicher
`health_score` **nur aus realen Leseergebnissen** (clean 1.0 / retried 0.8 /
unstable 0.5 / failed 0), Status-Bänder; ohne Daten `NOT_AVAILABLE` statt 0 — keine
erfundenen Health-Werte, kein Kopierschutz-Bypass (nur legitim lesbare Daten).
Datenmodell/Schnittstelle vorbereitet; noch nicht von einem realen resilienten
Lese-Backend gefüttert (Hardware). 6 Unit-Tests. `pytest -q` = 603 passed / 19
skipped / 0 failed; compileall + diff-check sauber.

### 2026-09-09 — Speicherplatz-Prüfung vor großen Operationen (Mission 31)

`src/services/disk_space.py`: `evaluate`/`check_path`/`ensure_space` (freier Platz
vs. benötigt + Sicherheitsreserve = max(512 MB, 5 %)), Schätzer `directory_size`,
`iso_estimate` (Payload + ~2 % Overhead), `transcode_estimate`. Neuer `StorageError`
(`src/core/errors.py`). **Verdrahtet**: `DiscTools.create_iso` bricht jetzt VOR dem
`mkisofs`-Start ab, wenn der Zielordner nicht genug Platz hat (Test beweist, dass der
externe Prozess dann nicht startet). 8 Unit-Tests (evaluate/Reserve/Schätzer/
gemocktes `disk_usage`/Früh-Abbruch). `pytest -q` = 611 passed / 19 skipped / 0
failed; compileall + diff-check sauber.

### 2026-09-09 — TempManager (Mission 30, produktionsreif)

`src/services/temp_manager.py`: konfigurierbarer Temp-Root (Default unter
`tempfile.gettempdir()/RetroDisc`), eindeutige Job-Verzeichnisse (`retrodisc-job-<id>`,
Job-ID sanitisiert → kein Pfad-Ausbruch/Wurzeltreffer), `allocate` (Artefakt im
Job-Dir, kein Ausbruch), `ensure_space()` (nutzt `disk_space`, keine Parallelstruktur),
`cleanup(job)`, `cleanup_stale(max_age)` (Absturz-Recovery), Context-Manager
`session(required_bytes=…, keep_on_error=…)` (optionaler Speicher-Precheck vor dem
Anlegen; räumt bei Erfolg auf; bei Fehler standardmäßig auch – kein Leak großer Images
– oder Diagnoseartefakte behalten). **Löschungen hart auf eigene Job-Dirs innerhalb
des Roots begrenzt** (nichts außerhalb wird je entfernt), Windows-Dateisperren via
begrenztem Retry toleriert, strukturiertes Logging, saubere Exceptions. Als
eigenständiger Service bereitgestellt (keine Wiring in aktuell von Codex bearbeitete
Dateien, um Konflikte zu vermeiden). 12 Unit-Tests.

### 2026-09-09 — Editor V1 auf bestehender Director-Timeline

- Dokumentation/Commits abgeglichen; Claudes Disc/Waveform-Arbeit erhalten. Bestehende Scene/ProductionProject erweitert: strukturierte Übergänge mit validierter Audio-/Video-Überlappung, Tempo/Freeze, Clip-Audio/Lock/Sichtbarkeit, Text/Overlay/PIP, Look-/Transform-Parameter. Alte Transitionstrings bleiben kompatibel.
- FFmpeg bleibt Renderer; finale Hardware-/CPU-Kodierung über bestehenden Converter. Keine Dependencies/Modelle installiert. UI-Edits/Undo serialisiert, Styles/Overlay-Controls/Suggestions angebunden.
- 17 reale synthetische Renderprüfungen mit FFprobe, Dauer/Audio, Volldecode, Recent Media und Quell-SHA-Schutz PASS; aktiver Cancel mit Cleanup PASS. Artefakt-Hashes: build/editor-acceptance/result.json.
- Text-Capability ehrlich unavailable (lokales FFmpeg ohne drawtext). Positive Text-/Font- und kombinierte Titel-Acceptance nicht behauptet. Kein visueller Qualitätsnachweis und kein realer Windows-Test.
- 597 passed / 19 skipped / 0 failed; UI-Bridge 0 findings, JS/compileall/diff-check PASS. Details und echte Restpunkte (Projekt-/Export-Settings, Preview, weitere Audio-/Overlay-Controls) in EDITOR_V1_STATUS.md.
- Keine Commits/Push/neuer Branch durch Codex.

### 2026-09-09 — VerifyService: echter VIDEO_TS/BDMV-Strukturvergleich

`src/services/verify.py` erweitert: `scan_tree` (Datei→Größe/Hash über den
vorhandenen `fingerprint`-Walker, keine Parallelstruktur), `detect_disc_kind`
(VIDEO_TS→dvd / BDMV→bd), `layout_checks` (Pflichtdateien: DVD `VIDEO_TS/VIDEO_TS.IFO`;
BD `BDMV/index.bdmv`+`MovieObject.bdmv`; empfohlene als Warnung), `compare_trees`
(fehlend=Fehler, zusätzlich=Warnung, Größenabweichung=Fehler, optional Hash-Vergleich)
und `verify_disc_structure(reference, target, kind='auto', compare_hash=…)` →
strukturierter `VerifyResult` (PASS/PASS_WITH_WARNINGS/FAIL/NOT_AVAILABLE) mit
verständlichen Ursachen für UI/Logs statt bloßem Boolean. 6 neue Tests mit gültigen
und absichtlich beschädigten VIDEO_TS/BDMV-Strukturen (fehlende Pflichtdatei,
Größenabweichung, Extra-Datei=Warnung, Hash-Mismatch bei gleicher Größe). Keine
Bridge-Verdrahtung, da `retrodisc_launcher.py` aktuell fremd-uncommitted ist
(Konfliktvermeidung). `pytest -q` grün.

### 2026-09-09 — MetadataService + lokaler Metadata-Cache (Mission 23)

`src/services/metadata.py` (neu, offline-first): `Metadata`-Datenmodell (Titel/
Originaltitel/Jahr/Laufzeit/Beschreibung/Genres/Regie/Cast/Altersfreigabe/Cover/
Backdrop/Provider/Provider-ID/Sprache/Disc-Typ/Edition/Confidence), `MetadataQuery`,
`MetadataProvider`-Protocol (austauschbar/priorisierbar für TMDb/OMDb/… später),
`MetadataCache` (fingerprint-keyed JSON, **atomare Writes**, korrupte Dateien werden
ignoriert statt Absturz, `schema_version`+Migrationshaken, TTL/Refresh, **manuelle
Overrides getrennt von Auto-Daten – gewinnen beim Merge und überleben Auto-Refresh**),
`MetadataService.lookup` (Cache-Hit → **kein Provider-Aufruf**; offline/kein Provider →
nur lokaler Cache; Providerfehler blockiert nichts → Fallback), `score_candidate`
(Titel/Jahr/Laufzeit, mehrere Kandidaten nach Confidence). Fingerprint als
Primärschlüssel; vorhandener `fingerprint`-Service wiederverwendet, keine doppelte
Cache/HTTP/Fingerprint-Infra. 15 Unit-Tests (R/W, unbekannt, korrupt, Schema/Migration,
manueller Override, TTL, atomarer Write, Confidence, Cache-Hit-ohne-Provider,
Providerfehler, offline, mehrere Kandidaten, Priorität). `pytest -q` = 644 passed /
19 skipped / 0 failed; compileall + diff-check sauber. Keine Bridge/UI-Verdrahtung
(Launcher/UI fremd-uncommitted → Konfliktvermeidung).

### 2026-09-09 — LibraryService / lokaler Medienkatalog

`src/services/library_catalog.py` (neu): `LibraryItem`-Datenmodell (Fingerprint,
Titel, Jahr, source_type, original_disc_type, iso_path, rip_path, cover,
content_hash, created, last_verified, notes, metadata) und `LibraryService` auf
**SQLite mit `PRAGMA user_version`-Schema-Versionierung + Migrationshaken** (keine
flache JSON-Liste; eigene catalog.db, rührt die bestehende scanned-media library.db
nicht an). Fingerprint = Primärschlüssel → natürliche Dedupe (Upsert bewahrt
Anlegedatum und manuelle Notizen), `content_hash`-Gruppen als zusätzliche
Dubletten-Erkennung (`find_duplicates`), `attach_metadata` verknüpft
MetadataService-Daten, `mark_verified`, robustes Verhalten bei kaputtem
metadata_json. Vorbereitet für spätere Player-/Library-UI. 9 Unit-Tests
(Roundtrip, Dedupe/Upsert, Migration von altem DB-Stand, Duplikate,
Metadata-Verknüpfung, JSON-Korruption). `pytest -q` = 653 passed / 19 skipped /
0 failed; compileall + diff-check sauber.

### 2026-09-09 — Kritischer Audit Metadata/Library + Härtung

Selbstaudit der beiden Vorpakete gegen die Anforderungen; gefundene echte Lücken behoben:
- **Atomare Writes gehärtet:** `MetadataCache._atomic_write` mit `flush()+os.fsync()`
  vor dem Rename und `try/finally`-Temp-Cleanup → kein verwaister Temp-Rest, Ziel
  bleibt bei Abbruch intakt.
- **Migration forward-safe:** neuer als unterstützter Cache (version > current) wird
  NICHT herabgestuft/überschrieben; echte v0→v1-Aufwärtsmigration.
- **Provider-Timeout:** `MetadataService` umschließt jeden Provider mit
  `asyncio.wait_for`; Hänger/Exception werden isoliert, der nächste Provider läuft
  weiter.
- **Matching:** `disc_label` fließt ein (Fallback wenn kein Titel); deterministischer
  Tie-Break (Confidence → exaktes Jahr → Titel).
- **Library:** `PRAGMA busy_timeout=5000` (konkurrierende Zugriffe), korrupte/ungültige
  DB → klarer `LibraryError` statt roher SQLite-Fehler, Upsert überschreibt vorhandene
  nicht-leere (auch manuelle) Felder NICHT mit Leerwerten, Context-Manager (`with`)
  schließt die Verbindung sauber.
- **Neue Tests:** +17 (Multi-Provider-Failover, Provider-Timeout, disc_label-Match,
  Tie-Break, Stale-Refresh, manueller Override über `service.lookup`, Forward-Compat-
  Migration, atomarer Write-Fehler; Library: Upsert-Felderhalt, busy_timeout, Rollback,
  korrupte DB, Context-Manager/close) plus **3 Integrationstests** über die echte Kette
  DiscFingerprint→MetadataService→MetadataCache→LibraryService (inkl. Offline-Pfad und
  Fingerprint-Dedupe derselben Disc).
- `pytest -q` = 670 passed / 19 skipped / 0 failed; compileall + diff-check sauber.

### 2026-09-09 — Transcoding-Backend-Schicht (neues Subpackage src/services/transcode)

Zusammenhängende, UI-freie Transcoding-Grundlage; alle FFmpeg-/ffprobe-Aufrufe über
einen injizierbaren Runner → komplett ohne echtes FFmpeg testbar. Codex-WIP nicht
berührt.
- **capabilities.py**: CapabilityStatus-Enum, EncoderCapability, echte Probe-Encodes
  (lavfi, wenige Frames), HardwareAccelerationService (CPU/NVENC/QSV/AMF, AV1),
  umgebungs-signierter CapabilityCache (ffmpeg-Version+Plattform+Host) mit TTL,
  korrupt-sicher.
- **profiles.py**: 7 deklarative TranscodingProfiles (strukturierte Felder, keine
  Command-Strings). **selection.py**: EncoderSelectionEngine (Hardware nach Vendor-
  Priorität → CPU → Fallback-Codecs; HDR/10-bit vermeidet ungeeignetes H.264;
  transparente reasons/warnings; force/prefer/allow-hardware).
- **probe.py**: MediaProbeService (robustes ffprobe-JSON, tolerant/korrupt-sicher).
- **command.py**: FFmpegCommandBuilder → Argumentliste (kein Shell-String);
  encoder-spezifische Ratecontrol/Preset-Abbildung, Downscale-only, Deinterlace,
  Mapping, Container.
- **progress.py**: FFmpegProgressParser (-progress pipe:1 → frame/fps/out_time/speed,
  Prozent+ETA), toleriert unvollständige Zeilen.
- **job.py**: TranscodingJob-Statemachine + run_transcode (Streaming-Progress,
  Cancel/Timeout, graceful terminate→kill).
- **verify.py**: verify_transcode (Existenz/Größe/ffprobe-lesbar/Videostream/Codec/
  Dauer → VerifyResult; traut Exit-Code 0 nicht blind). **errors.py**:
  FFmpegErrorClass + kompakte Klassifikation (UNKNOWN-Fallback). **service.py**:
  TranscodeService orchestriert Probe→Caps→Profile→Selection→Command→Job→Verify.
- **Audit-Fund + Fix**: `run_transcode` las stderr erst am Ende → volllaufende
  stderr-Pipe hätte lange Encodes blockieren können (Deadlock). Jetzt gleichzeitiges,
  begrenztes stderr-Draining (16 KB Tail für Fehlerklassifikation). Kein Import-Zyklus,
  kein globaler Zustand, keine Shell-Strings.
- Tests: 66 neue (Capabilities/Selection/Probe/Command/Progress/Job/Verify/Integration),
  inkl. **echtem FFmpeg-Integrationstest** (skippt ohne FFmpeg, kein CI-Gate).
  `pytest -q` = 736 passed / 19 skipped / 0 failed; compileall + diff-check sauber.

### 2026-09-10 — Pipeline-Handoff abgeschlossen, CPU-Workflow real geprüft

- Übernommen: uncommittierte `pipeline/events.py`, `resources.py`, `scheduler.py`
  und `test_pipeline_scheduler.py`; Claudes persistente Queue/Analyse/Recommendation
  sowie Transcode-/Metadata-/Library-Services weiterverwendet. Editor-WIP bleibt separat.
- Reproduziert und behoben: Cancel vor Task-Start verlor Ressourcen/Status;
  Scheduler-Abbruch ließ Child-Tasks laufen; Parent-Retry ließ ungestartete
  Dependency-Nachfolger dauerhaft FAILED. Fehlerfortpflanzung funktioniert jetzt
  auch gegen die Prioritätsreihenfolge; fehlende Dependencies werden benannt.
- Queue-Claim und Retry bedingte atomare SQLite-Updates; Metadata-Merge unter
  Schreiblock; Rollback/Busy/Connection-Cleanup und explizites Startup-Recovery
  getestet. Recovery setzt PREPARING/RUNNING/VERIFYING auf INTERRUPTED, startet
  nichts automatisch und behandelt vorhandene Teil-Ausgaben nie als Erfolg.
- Task-Cancel terminiert nun auch den echten FFmpeg-Kindprozess. Verifikation
  lehnt stark verkürzte/zeitlich unbekannte Ausgaben und fehlendes erwartetes Audio
  ab. `event_type=`-Fix real mit werfendem Listener und weiterlaufendem Workflow belegt.
- `pipeline/workflow.py`: schmaler File-Adapter Analyse → Recommendation → Queue →
  Scheduler → CPU-Transcode → Verify + vollständiges Decode → Library + Provenance/
  Events. Bestehende Services, keine zweite Engine/DB. Exklusives Publish über
  Hardlink im gleichen Dateisystem schützt existierende Ziele; Dateisysteme ohne
  Hardlink-Unterstützung schlagen sicher fehl. Pro Job eigener Staging-Pfad,
  Cleanup bei Fehler/Cancel. Ressourcen gelten innerhalb des gemeinsamen
  ResourceManager/Event-Loops, nicht als systemweite Mehrprozess-Sperren.
- Real auf macOS: synthetische Quelle H.264/AAC, 160×120, 2.000 s; Output CPU
  `libx264`, H.264/AAC, 2.020 s, 68 735 Bytes. Queue/Library erneut geöffnet,
  Progress/Events/Library-Provenance geprüft, vollständiges Decoding, Quelle
  unverändert. Artefakte (ignoriert): `build/pipeline-acceptance/report.json`.
  Quelle SHA-256 `70aa9ac36b84d6184a177bdaec0cc04e9c323faf459c421cb81748ccf3e8d23d`;
  Ausgabe SHA-256 `ade0e3b4f34fcb38ec2d620b9bba28cebe02757b66594b5b2642d4bed297cea6`.
- Gesamtdiff-Review: zusätzliche Musikdauer-Regression im älteren Editor-WIP
  (Speed/Freeze/Overlap) minimal korrigiert und separat getestet; nicht Bestandteil
  dieses Pipeline-Commits. Vorhandene Editor-Restpunkte bleiben bestehen.
- Gates des gemeinsamen Worktrees: **804 passed / 19 skipped / 0 failed**;
  `build/pipeline-regression.log`. Bridge PASS/0 Findings, Node-Syntax PASS,
  compileall PASS, git diff --check PASS. Reale CPU-/Cancel-Tests zusätzlich zu
  simulierten Ressourcen-/Failure-Tests. Keine physische Disc oder Windows-GPU getestet.
- Offen: reale Windows-/NVENC-/QSV-/AMF-/Laufwerksabnahme. Der neue persistente
  Backend-Workflow ist noch nicht in die GUI-Queue eingebunden (kein UI-Umbau
  in diesem Auftrag). Recovery wird explizit durch den Queue-Eigentümer vor dem
  Start aufgerufen; keine automatische Wiederaufnahme/Entfernung fremder Dateien.

### 2026-09-11 — Echte Blu-ray-Funktionalität (BDMV-Authoring, ISO, Brennen, Capability-Gating)

Vorherige UI-Blöcke zeigten Blu-ray-Zielmedien nur an und deaktivierten sie
pauschal ("BDMV-Authoring nicht implementiert"). Dieser Block macht die
Unterstützung real, statt sie nur sichtbar zu machen.

- Bestandsaufnahme: Blu-ray-Lesen/-Rippen war bereits real (`disc_analyzer.py`/
  `bluray_mpls.py`, `ripper.py`); BDMV-*Authoring* fehlte komplett (nur
  `dvdauthor`/VIDEO_TS vorhanden, kein Blu-ray-Muxing-Werkzeug installiert oder
  vendorbar).
- Neu: `src/services/bluray_authoring.py` (MPLS-/CLPI-/index.bdmv-/
  MovieObject.bdmv-Writer; MPLS byte-exakt zum bereits produktiven Leser,
  echter Round-Trip getestet) + `src/services/bluray_workflow.py`
  (`BlurayWorkflow` analog `DVDWorkflow`) + `FFmpeg.to_bluray_stream`
  (BDAV-M2TS via `-mpegts_m2ts_mode`, feste PIDs 0x1011/0x1100 - real gegen
  FFmpeg verifiziert: Sync-Byte 0x47 an Offset 4 jedes 192-Byte-Pakets, PIDs
  per ffprobe bestätigt). Ende-zu-Ende real geprüft: echter FFmpeg-Encode →
  `author_bdmv()` → von RetroDiscs eigenem `DiscAnalyzer` korrekt zurückgelesen.
- Realer Fund + Fix: `mkisofs -allow-limited-size` wird von der hier
  installierten mkisofs-Variante nicht erkannt, UND der naheliegende Fallback
  (`-udf -iso-level 3`) verwirft Dateien >4 GiB dabei stillschweigend
  (Exit-Code 0, aber ein kaputt-kleines Image) - `DiscTools.create_iso` jetzt
  mit Flag-Fallback plus einer Größenprüfung nach der Erstellung gehärtet.
- Neue Bridge-Methoden: `create_bluray`, `burn_existing_iso`,
  `check_target_medium` (Capability-Gating bereits vor dem Einreihen, nicht
  nur in der UI); `list_target_media` meldet jetzt `authoring_available`.
- `copy_disc`-Fix: eine kopierte Blu-ray-Quelle bekam bisher fälschlich
  `disc_type=DVD` beim Brennen (Book-Type-Fehlklassifikation) - jetzt real
  über `BDMV`-Erkennung korrekt durchgereicht.
- Tests: 927 → 989 passed (+62), 19 skipped, derselbe 1 vorbestehende
  unabhängige Fehler unverändert. `compileall`/`verify_ui_bridge`/
  `node --check` PASS.
- Screenshots (`artifacts/blu-ray-visibility-review/`): Startseite, Rippen mit
  sichtbarer DVD-/Blu-ray-Erkennung, Brennen mit Zielmedienauswahl (einmal
  DVD-only-, einmal BDXL-fähiges Laufwerk), Bibliothek als sekundäres Werkzeug.
- Offen: kein physisches Laufwerk in dieser Umgebung (Burn-Pfad softwareseitig
  vollständig getestet, nicht hardwareverifiziert); das produktive
  Windows-`mkisofs.exe` (aus dem DVDStyler-Bundle) selbst nicht getestet;
  `index.bdmv`/`MovieObject.bdmv` sind strukturell wohlgeformt, aber das
  MovieObject trägt bewusst keine HDMV-Navigationsbefehle (kein
  Referenz-Decoder zum Gegenprüfen vorhanden).

### 2026-09-12 — DVD-/Blu-ray-Vorschau-Player (mpv per JSON-IPC)

- Engine-Wahl: mpv per JSON-IPC-Socket (`--input-ipc-server`), gesteuert als
  Subprozess wie FFmpeg/dvdauthor/growisofs. `python-mpv` (ctypes-Bindings)
  real getestet und verworfen: stürzt beim Instanziieren reproduzierbar ab,
  obwohl das mpv-Binary selbst fehlerfrei läuft. HTML5 `<video>` verworfen
  (kein zuverlässiger MPEG-2-/VOB-/DTS-/Mehrspur-Support in
  WKWebView/WebView2).
- Neu: `src/services/player.py` (`PlayerService`, `_MpvIpcClient`),
  `player_source.py` (Titel-Index → Datei-/Segmentliste, wiederverwendet
  `dvd_ifo.parse_tt_srpt`/`bluray_mpls.parse_mpls` - keine parallele
  Disc-Analyse; mehrsegmentige Titel laufen über mpvs `edl://`-Protokoll als
  eine zusammenhängende Zeitleiste), `iso_mount.py` (`hdiutil`/
  `Mount-DiskImage`, garantiertes Unmount), `drm_capabilities.py`
  (CSS/AACS/BD+ ehrlich als nicht unterstützt ausgewiesen).
- Drei real gefundene und behobene Bugs: (1) ein dauerhafter
  Hintergrund-Reader-Task verlor unter echtem IPC-Verkehr selten eine
  Antwort (Race) → jetzt strikt sequenziell/lock-geschützt gelesen; (2)
  ein Titelwechsel auf derselben mpv-Instanz sah noch das
  `file-loaded`-Ereignis der vorherigen Quelle → `clear_events()` jetzt vor
  jedem `loadfile`; (3) ein ISO blieb dauerhaft gemountet, wenn die
  Titelauflösung NACH erfolgreichem Mount fehlschlug → jetzt in jedem
  Fehlerpfad garantiert ausgehängt (Regressionstest ergänzt).
- UI: neuer Tab „Vorschau" + „Vorschau"-Button je Titel im Rippen-Tab (nutzt
  das bereits geladene `get_disc_content`-Ergebnis, keine erneute
  Titelerkennung im Player).
- Real getestet (echtes MPEG-2/AC-3- bzw. H.264/AC-3-Material, keine
  Fake-Bytes): normale Videodatei; DVD-Titel mit einem und mit mehreren
  VOB-Segmenten; Blu-ray-Titel mit einem und mit mehreren M2TS-Clips (via
  `bluray_authoring`); DVD-/Blu-ray-ISO (Mount → Wiedergabe → Unmount);
  Titel-/Kapitel-/Audio-/Untertitelwechsel; Main-Movie-Flow (öffnet den von
  `DiscAnalyzer` real identifizierten Titel); Stop/Cleanup; ungültige Quelle;
  nicht unterstützter Codec; fehlendes Backend.
- Tests: 1019 → 1037 passed (+18), 19 skipped, derselbe 1 vorbestehende
  unabhängige Fehler unverändert. `compileall`/`verify_ui_bridge`/
  `node --check` PASS.
- Screenshots (`artifacts/player-preview-review/`): Ruhezustand, laufende
  Wiedergabe, Titel-/Kapitelwahl, Audio-/Untertitelwahl - alle gegen echte
  mpv-Wiedergabe über einen lokalen Test-HTTP-Shim (computer-use rendert in
  dieser Sandbox kein natives Fenster, dieselbe bereits dokumentierte
  Einschränkung wie in früheren Blöcken).
- Offen: keine DVD-/Blu-ray-Menüs (HDMV/BD-J, bewusst eine spätere Funktion);
  kein CSS/AACS/BD+; mpv ist für Windows-Produktionsbuilds noch nicht über
  `prepare_vendor.py` vendort; der Windows-Named-Pipe-IPC-Zweig ist nach
  mpv-Dokumentation implementiert, aber in dieser macOS-Umgebung nicht
  laufzeitgeprüft.
- Kombinierter Stand des gemeinsamen Worktrees nach Merge mit paralleler
  Editor-/Timeline-/Queue-Arbeit: **1037 passed / 19 skipped / 1 vorbestehender
  unabhängiger Fehler** (`test_every_queueing_bridge_method_returns_a_usable_job`,
  scheitert an `convert_file`, nicht an Disc-/Player-Funktionalität).
