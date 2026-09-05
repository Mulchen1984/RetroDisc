# PLATFORM_PARITY.md — Cross-Platform-Handoff-Stand

Stand: 2026-09-05. Dieses Dokument beschreibt, was beim Wechsel auf macOS
**uebernommen** werden kann und was dort neu beschafft oder verifiziert werden
muss. Es ersetzt nicht `RELEASE_AUDIT_STATUS.md` — dort steht die Beleglage,
hier die Plattformzuordnung.

## Grundregel des Handoffs

Unter Windows geloeste Produktlogik wird auf macOS **nicht neu implementiert**.
Der Acceptance-Harness (`src/acceptance.py` + `scripts/run_acceptance.py`)
bleibt die gemeinsame fachliche Wahrheit. Es gibt **keine zweite macOS-
Testlogik**: dieselben Faelle laufen dort gegen dasselbe Produkt, nur mit
macOS-Vendor-Binaries und einem macOS-Bauweg.

## Statuslegende

| Status | Bedeutung |
| --- | --- |
| **shared** | Plattformneutraler Code. Laeuft unveraendert, sobald die Werkzeuge vorhanden sind. |
| **win-verified** | Unter Windows real belegt (Gates + Acceptance). |
| **mac-verified** | Auf macOS real belegt. **Derzeit nirgends vergeben** — auf einem Mac ist noch nichts gelaufen. |
| **mac-pending** | Kein Codeaufwand erwartet, aber auf macOS noch zu verifizieren. |
| **platform-specific** | Erfordert eine macOS-spezifische Anpassung oder Beschaffung. |

Es gibt aktuell **keinen einzigen** `mac-verified`-Eintrag. Das ist kein
Versehen, sondern der ehrliche Stand: dieser Baseline-Commit ist der
Ausgangspunkt fuer die macOS-Verifikation, nicht ihr Ergebnis.

Wichtig: **win-verified** heisst nicht „auf macOS kaputt". Es heisst, dass fuer
macOS kein Beleg existiert. Jede Aussage in diesem Dokument ist bewusst so
formuliert, dass sie nicht mehr behauptet, als belegt ist.

---

## 1. Gemeinsamer Core

Der Core ist bereits auf Portierbarkeit angelegt: die Plattformunterschiede
stecken in **geschuetzten Zweigen** (`if os.name == "nt": ... else: ...`), nicht
in parallelen Implementierungen.

| Modul | Status | Anmerkung |
| --- | --- | --- |
| `src/core/ffmpeg.py` | shared | Reiner FFmpeg-Treiber. Kein Plattformcode. |
| `src/core/downloader.py` | shared | Private Arbeitsverzeichnisse, Gruppen-Publikation, Kollisionszaehler — alles plattformneutral. |
| `src/core/pipeline.py` | shared | Jobverwaltung, Zustaende, Abbruch. |
| `src/models/`, `src/config/presets.py` | shared | Datenmodelle und Presets. |
| `src/services/converter.py`, `smart_edit.py`, `library.py`, `search.py`, `watch_folder.py`, `assistant.py` | shared | Kein Plattformcode. |
| `src/services/upscaler.py` | shared | Nutzt `tempfile.mkdtemp`; FFmpeg-Lanczos-Fallback ist plattformneutral. |
| `src/utils/logging_setup.py` | shared | Loest ein Windows-Problem, ist aber plattformneutral geschrieben (`None`-Stroeme, `reconfigure`, `buffer`-Fallback). |
| `src/utils/subprocesses.py` | shared, mit Adapter | `CREATE_NO_WINDOW` und der Prozessbaum-Abbruch sind auf `os.name == "nt"` begrenzt; der POSIX-Zweig existiert bereits. |
| `src/config/settings.py` | shared, mit Adapter | `default_device` ist `"D:"` unter Windows, sonst `/dev/sr0`. Auf macOS ist das **nicht** korrekt — siehe Abschnitt 4. |
| `src/core/disc.py` | shared, mit Adapter | Laufwerkserkennung und Medienpruefung haben einen Windows-Zweig (`_windows_volume_info`, Laufwerksbuchstaben). macOS braucht ein Gegenstueck. |
| `src/services/dvd_workflow.py` | shared, mit Adapter | Nur die Geraetepfad-Behandlung ist Windows-spezifisch. |
| `src/services/subtitle.py` | shared | Sucht das Modell unter `_MEIPASS/vendor/whisper-base` bzw. im Repo — beides plattformneutral. |
| `src/ui/app.html` | shared | Die gesamte Oberflaeche samt Inline-JavaScript. |

## 2. Einstiegspunkte und Bauweg

| Datei | Status | Anmerkung |
| --- | --- | --- |
| `retrodisc_launcher.py` | win-verified | **Produktiver Einstieg der gepackten EXE.** Enthaelt `RetroDiscBridge`/`RetroDiscApi` und den Acceptance-Hook. Der Code ist ueberwiegend plattformneutral; die Windows-Bezuege sind `_MEIPASS`, die DVD-Werkzeugaufloesung und die Konsolen-Encoding-Absicherung. Auf macOS als Einstieg wiederverwendbar, aber dort nicht verifiziert. |
| `build.py`, `retrodisc_final.spec` | platform-specific | Baut ausschliesslich fuer Windows (Onefile-EXE, Installer). macOS braucht einen eigenen Bauweg (App-Bundle statt EXE). |
| `installer/` | platform-specific | Windows-Installer und Uninstaller. Auf macOS ohne Entsprechung (dort DMG). |
| `prepare_vendor.py` | platform-specific | Laedt **Windows**-Binaries. Der Whisper-Teil ist plattformneutral und wird wiederverwendet — siehe `prepare_vendor_macos.py`. |
| `BUILD_MACOS.sh`, `create_dmg.py`, `assets/retrodisc.icns` | platform-specific | Altbestand aus der Zeit vor der Windows-only-Entscheidung. **An keinem Gate belegt.** Als Ausgangspunkt brauchbar, aber vor Gebrauch zu pruefen, nicht blind zu vertrauen. |
| `retrodisc_portable.py`, `src/ui/desktop.py`, `retrodisc.py` | shared, unbelegt | Enthalten bereits Darwin/Linux-Zweige, sind aber **nicht** der produktive Einstieg und an keinem Gate belegt. |

## 3. Funktionsoberflaeche (42 Bridge-Methoden)

Gruppiert nach fachlichem Bereich. Die Spalte „macOS" nennt den erwarteten
Aufwand, nicht ein Messergebnis.

| Bereich | Methoden | Windows | macOS |
| --- | --- | --- | --- |
| Konvertierung | `convert_file`, `convert_batch`, `get_presets`, `probe_file`, `get_mediainfo` | win-verified (Acceptance-Fall `conversion`) | mac-pending — nur FFmpeg noetig |
| Download | `download_url`, `search_media` | win-verified (Acceptance-Fall `unicode_download`) | mac-pending — nur yt-dlp noetig |
| Untertitel / Whisper | `generate_subtitles` | win-verified im Smoke; **als Acceptance-Fall noch offen** | mac-pending — Modell ist plattformneutral |
| Videobearbeitung | `trim_video`, `merge_videos`, `upscale_video`, `interpolate_video`, `create_highlights`, `preview_trim` | win-verified im Smoke | mac-pending — nur FFmpeg noetig |
| Jobs / Queue | `get_queue`, `cancel_job`, `clear_completed` | win-verified in Source-Tests; **Cancel als Acceptance-Fall noch offen** | mac-pending |
| Einstellungen | `get_settings`, `save_settings`, `check_tools`, `get_tool_status` | win-verified (Acceptance-Fall `settings`) | platform-specific - `default_device` (siehe 4) |
| Bibliothek | `get_library`, `scan_library`, `search_library`, `get_library_stats` | win-verified in Source-Tests | mac-pending |
| Watch Folder | `set_watch_folder`, `get_watch_folders` | win-verified in Source-Tests | mac-pending |
| **Disc / Optisch** | `detect_burners`, `get_disc_info`, `create_dvd`, `rip_disc` | win-verified ohne Rohling (virtuelles ISO) | **platform-specific** — Laufwerkserkennung, Geraetepfade und DVD-Werkzeuge sind alle Windows-spezifisch |
| UI / Dialoge | `open_file_dialog`, `open_folder_dialog`, `open_folder_for_batch`, `open_output_folder`, `open_tool_dialog`, `resize_compact`, `resize_work`, `splash_complete`, `shutdown` | win-verified | mac-pending — pywebview-Verhalten auf WebKit weicht ab |
| Sonstiges | `play_sound`, `run_assistant` | win-verified | mac-pending |

## 4. Konkret bekannte macOS-Anpassungen

Diese Punkte sind **aus dem Code abgeleitet**, nicht auf einem Mac gemessen:

1. **`src/config/settings.py:15`** — `default_device` liefert `"D:"` unter Windows und sonst `/dev/sr0`. `/dev/sr0` ist Linux, **nicht** macOS. Auf macOS waere es typischerweise `/dev/disk*` bzw. der Zugriff ueber `drutil`. Das ist die klarste, konkret benennbare Anpassung.
2. **`src/core/disc.py`** — `_windows_volume_info`, `GetVolumeInformationW` und die Laufwerksbuchstaben-Logik brauchen ein macOS-Gegenstueck (`diskutil`/`drutil`).
3. **`src/services/dvd_workflow.py:213`** — Geraetepfad-Behandlung mit Laufwerksbuchstaben.
4. **pywebview** — auf macOS ueber WebKit statt WebView2. Braucht `pyobjc-core` und `pyobjc-framework-Cocoa`/`WebKit`. Fensterverhalten, Dialoge und der Splash-Uebergang sind dort neu zu verifizieren.
5. **Bauweg** — App-Bundle und DMG statt Onefile-EXE und Installer; Signierung ueber Apple-Notarisierung statt Authenticode.
6. **`src/utils/subprocesses.py`** — der POSIX-Zweig existiert, ist aber nie an einem Gate gelaufen.

## 5. Vendor-Ressourcen

### Plattformneutral — direkt uebernehmen

| Ressource | Groesse | Warum neutral |
| --- | --- | --- |
| `vendor/whisper-base/` (`model.bin`, `tokenizer.json`, `vocabulary.txt`, `config.json`) | ~148 MB | CTranslate2-Modellgewichte. Reine Daten, kein Maschinencode. Gepinnt auf `Systran/faster-whisper-base`, Revision `ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66`, jede Datei per SHA-256 geprueft. `prepare_vendor.prepare_whisper()` funktioniert unveraendert auf macOS. |
| `tests/fixtures/test_video.mp4`, `tests/fixtures/spoken_de.wav` | klein | Medien-Testressourcen, **in Git versioniert** und damit beim Auschecken sofort da. |

### Muss auf macOS neu beschafft werden

| Ressource | Windows-Quelle heute | macOS-Beschaffung |
| --- | --- | --- |
| FFmpeg / FFprobe | BtbN-Autobuild `N-126342-gf88b741dbf`, Tag `autobuild-2026-08-31-13-27`, ZIP per SHA-256 gepinnt | macOS-Build noetig (z. B. evermeet.cx oder Homebrew `ffmpeg`). **Neuer Pin mit eigener SHA-256 erforderlich.** |
| yt-dlp | `yt-dlp.exe` 2026.08.19, SHA-256 `66674953…` | `yt-dlp_macos` derselben Version. **Neuer Pin erforderlich.** Der Versionspin selbst ist plattformneutral und muss gleich bleiben — ein aelterer Pin bricht den Download still (`HTTP 403`). |
| DVD-Werkzeuge (`dvdauthor`, `mkisofs`, `growisofs`, `dvd+rw-mediainfo`) | Aus dem **DVDStyler-Windows-Installer** 3.2.1 extrahiert | Auf macOS nicht aus DVDStyler zu holen. Herkunft: Homebrew `dvdauthor`, `cdrtools` (liefert `mkisofs`), `dvd+rw-tools`. **Anderer Beschaffungsweg, andere Pins.** |
| `vendor/dvdstyler/`, `vendor/dvdstyler-download/` | Windows-Installer und Extraktionsordner | Auf macOS ohne Entsprechung. |

Keine dieser Vendor-Dateien liegt in Git — `vendor/` ist ignoriert. Auf dem Mac
wird der Baum neu erzeugt, nicht kopiert.

## 6. Was nicht in Git liegt (und nicht hineingehoert)

Real geprueft am 2026-09-05: **0** getrackte `.exe`, `.dll`, `.zip`, `.iso`,
`.so`, `.dylib`, `.pyd` und keine Pfade unter `vendor/`, `dist/`, `Output/`,
`build/` oder `.venv/`. Das Repository umfasst 119 versionierte Dateien.

Ignoriert: `vendor/`, `dist/`, `Output/`, `build/`, `.venv/`, `RetroDisc_Data/`,
`.claude/settings.local.json`, Caches und IDE-Metadaten.

## 7. Ablauf auf dem Mac

1. Genau diesen Commit auschecken (Tag `v1.0.0-crossplatform-baseline`).
2. Python 3.11 bereitstellen, `pip install -r requirements.txt`, dazu
   `pywebview`, `pyobjc-core`, `pyobjc-framework-Cocoa`.
3. `python prepare_vendor_macos.py` — holt den plattformneutralen
   Whisper-Baum ueber den bestehenden, gepinnten Pfad und meldet praezise,
   welche macOS-Binaries noch fehlen.
4. `python -m pytest -q` — die plattformneutralen Tests muessen laufen.
   Windows-spezifische Tests (Installer, Codesign, Subprocess-Sichtbarkeit)
   sind dort als uebersprungen oder als bekannte Luecke zu erwarten und
   **nicht** umzuschreiben, bevor der Grund verstanden ist.
5. `python scripts/run_acceptance.py --source-only` — **derselbe** Harness,
   dieselben Faelle. Kein macOS-Sonderweg.

## 8. Offene Punkte, bewusst nicht erledigt

- **Acceptance-Faelle Cancel, Collision und Whisper** sind spezifiziert, aber
  noch nicht implementiert. Sie waren freigegeben und wurden zugunsten dieses
  Handoffs zurueckgestellt; es existiert kein angefangener Code dafuer.
- **Code-Signatur** — die Windows-Artefakte sind unsigniert. Auf macOS tritt
  an ihre Stelle die Apple-Notarisierung. Separat als Distributionsthema.
- **Physischer Brenn- und Rueckleseteset** — mangels Rohling auf keiner
  Plattform gefahren. Separat als Hardware-Acceptance.
- **macOS-Bauweg** — bewusst nicht angefasst („noch kein grosser macOS-Umbau").

---

## 9. Ein Repository als einzige Source of Truth

Windows und macOS arbeiten auf **demselben** Repository. Es gibt keinen
zweiten Quellstand und keine Fork-Struktur.

| Feld | Wert |
| --- | --- |
| Repository | `C:\Users\marco\Documents\Claude Code\RetroDisc` (lokal) |
| Remote | **noch nicht eingerichtet** — siehe unten |
| Branch | `main` |
| Baseline-Tag | `crossplatform-baseline-2026-09-05` |

### Branch-Strategie

- **`main`** ist der gemeinsame, stabile Produktstand. Beide Plattformen
  ziehen von hier und liefern hierhin zurueck.
- **Plattform-Branches nur temporaer** und nur fuer eine konkrete Aenderung,
  etwa `macos/disc-adapter`. Danach zurueck nach `main` und loeschen.
- **Keine dauerhafte Trennung** zwischen Windows- und macOS-Zweig. Sobald
  zwei Staende laenger nebeneinander leben, entsteht genau die Doppelarbeit,
  die dieser Handoff verhindern soll.
- Plattformunterschiede gehoeren in **Adapter innerhalb gemeinsamer Dateien**
  (`if os.name == "nt": ... else: ...`), nicht in plattformeigene Kopien
  derselben Logik.

### Offener Punkt: das Remote fehlt

Zum Zeitpunkt dieses Commits ist **kein Git-Remote konfiguriert**
(`git remote -v` ist leer) und das GitHub-CLI (`gh`) ist auf dem
Windows-Rechner nicht installiert. Der Baseline-Stand liegt daher lokal
eingefroren und getaggt vor, ist aber **nicht gepusht**.

Bevor der Mac ziehen kann, muss einmalig entschieden und eingerichtet werden:

1. Wo das gemeinsame Remote liegt (GitHub, GitLab, oder ein Bare-Repo auf
   einem Netzlaufwerk / iCloud-unabhaengigen Pfad).
2. Ob es **privat** ist. Das Repository enthaelt keine Geheimnisse, aber es
   ist unveroeffentlichte Arbeit; privat ist die Vorgabe.
3. Danach:

   ```
   git remote add origin <URL>
   git push -u origin main
   git push origin crossplatform-baseline-2026-09-05
   ```

Erst danach gilt Schritt 7 dieses Dokuments.
