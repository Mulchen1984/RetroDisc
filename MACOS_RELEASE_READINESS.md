# macOS Release-Abnahme — 2026-09-09

Status: lokaler Entwicklungsbuild abgenommen; noch keine Distributionsfreigabe.

## Artefakt und Reproduktion

- App: `build/macos-release/dist/RetroDisc.app` (Apple Silicon).
- Hauptprogramm SHA-256: `f7739c9b3e97ac03e2324302dc1ae7e2af4f7a9317ff92041b588fe8393553da`.
- Vollständige Datei-Hashes und Mach-O-Prüfung: `build/macos-release/bundle-audit.json`.
- Build aus dem ausdrücklich angeforderten bestehenden, uncommitteten Worktree.
- Build: `.venv-test/bin/python -m PyInstaller retrodisc_macos.spec --distpath build/macos-release/dist --workpath build/macos-release/work --noconfirm`.
- Build-Abhängigkeiten: vorhandene Projektpakete PyInstaller, pywebview und yt-dlp in `.venv-test` ergänzt. Keine neue Medien-/ML-Architektur.
- Modelle bleiben extern; keine Modelle ins Bundle kopiert.

## Tatsächliche Abnahme

| Prüfung | Ergebnis |
|---|---|
| macOS .app / Cocoa-WebView | PASS: Splash, Haupt-UI, injizierte JS-API, sauberes Ende |
| Plattform / Encoder-UI | macOS 26.6.2, native Controls, Auto/VideoToolbox/CPU |
| Bundle-Tools ohne Entwickler-PATH | FFmpeg, FFprobe, eigenständiges yt-dlp erfolgreich |
| First Run mit isolierten Nutzerdaten | Datenbank/Zielverzeichnisse erstellt, Recent zunächst leer, kein Tool-Download nötig |
| Whisper ohne Modell | korrekt `model_missing`, Runtime vorhanden |
| Whisper mit externem Tiny-Modell | offline echte deutsche Sprache, drei SRT-Segmente |
| Convert aus echter JS-Bridge | MP4 mit Unicode-/Leerzeichenpfad, erfolgreicher vollständiger Decode |
| Recent → Konvertieren/Brennen/Director | tatsächlicher Output über produktive UI-Funktion übernommen |
| App verschoben, Pfad mit Leerzeichen | Package-Prüfung und echte ASR erneut PASS |
| Mach-O-Abhängigkeiten | 121 Dateien geprüft; keine absoluten Homebrew-/Dev-Abhängigkeiten |
| codesign verify deep strict | PASS, nur Ad-hoc-Signatur |
| Gatekeeper (`spctl --assess`) | rejected (Exit 3); keine Distributionsfreigabe |
| Caption-Burn | nicht verfügbar: gebündeltes FFmpeg ohne subtitles/libass; UI-Capability/SRT-Fallback geprüft |

Belege: `package.json`, `package.srt`, `webview.json`, `webview.log`,
`relocated.json`, `relocated.srt`, `bundle-audit.json` unter `build/macos-release`.
Testdaten/Nutzerprofile im Worktree; vorhandenes ASR-Testmodell und Sprachaudio nur gelesen.
Keine Computer-Use-Prüfung; WebView-Abnahme über echte `evaluate_js`/Bridge-Aufrufe.

## Änderungen dieses Blocks

- `retrodisc_macos.spec`: macOS-Bundle für gemeinsamen Launcher, native Tool-Bibliotheken, Cocoa und ASR-Runtime.
- `scripts/bundled_ytdlp.py`: nativer gebündelter yt-dlp-Einstieg ohne System-Python.
- `retrodisc_launcher.py`: Bundle-yt-dlp priorisieren; `freeze_support()` verhindert erneuten GUI-Start durch Whisper-Unterprozesse; explizite Package-/WebView-Prüfmodi.
- `src/utils/package_check.py`: reproduzierbare Bundle-ASR-/WebView-/Handoff-Abnahme, ausschließlich explizit gestartet.
- `scripts/audit_macos_bundle.py`: Signatur, Abhängigkeiten und Datei-Hashes prüfen.
- `tests/test_macos_package.py`: Bundle-Priorität, plattformgetrennter Spec, multiprocessing-Startschutz.

## Regression

- 483 passed, 19 skipped, 0 failed (vollständiger Lauf, `regression.log`).
- Nach abschließender Erweiterung des Prüfmodus: 46 relevante Tests PASS.
- UI-Bridge PASS, 0 findings; JavaScript-Syntax PASS; compileall PASS; git diff --check PASS.
- Windows-Spec unverändert durch diesen Block; Windows-Plattformregression grün, kein realer Windows-Build hier.

## Verbleibend / Grenzen

- Developer-ID-Signierung, Notarisierung und Gatekeeper-Abnahme für Verteilung fehlen.
- Realer Windows-Paket-/Hardwaretest bleibt extern.
- Caption-Burn benötigt ein separat geprüftes libass-fähiges FFmpeg; keine Verfügbarkeit vorgetäuscht.
- Keine manuelle visuelle/Bedienungsabnahme aller Menüs oder tatsächlicher Brennhardware.
- Externes Whisper-Modell muss vom Benutzer konfiguriert/bereitgestellt werden; neue Nutzer erhalten korrekt Modell-fehlt-Status.
- Der erwähnte frühere „finaler Build- und UI-Abnahmelauf“-Prompt lag nicht vor; geprüft wurden die zehn explizit genannten Punkte.
- Keine Commits, kein Push, kein neuer Branch.
