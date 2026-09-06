# RetroDisc — Anforderungen und ihr Nachweis

Was das Produkt können muss, und **woran belegt ist**, dass es das kann. Eine
Anforderung ohne Nachweis gilt als offen, auch wenn der Code aussieht, als
wäre sie erfüllt.

Verwandte Dokumente: `CLAUDE.md` (Arbeitsweise, verbindlich),
`docs/ARCHITECTURE.md` (Aufbau), `docs/DECISIONS.md` (Warum),
`docs/TODO.md` (Backlog), `docs/RELEASE_STATUS.md` (Freigabereife),
`RELEASE_AUDIT_STATUS.md` (Messungen).

Stand: 2026-09-06

---

## Produktrahmen

| | |
|---|---|
| Plattform | Windows-only. macOS ist Ziel **nach** dem Windows-Abschluss. |
| Auslieferung | Portable ZIP und Installer, beide signiert. Kein sichtbares Konsolenfenster. |
| Betrieb | Vollständig lokal. Keine Cloud-Abhängigkeit für Kernfunktionen. |
| Nutzer | Windows-Endanwender ohne Kommandozeilenkenntnisse. |

---

## A — Grundprinzipien

Diese fünf stehen über den Einzelanforderungen. Ein Verstoß ist immer ein
Releaseblocker, unabhängig von seiner Größe.

| ID | Anforderung | Nachweis |
|----|-------------|----------|
| A1 | Keine Datei verschwindet für den Nutzer unsichtbar | `test_job_output_access.py` |
| A2 | Jeder Verarbeitungsschritt ist nachvollziehbar | `test_pipeline_visibility.py` |
| A3 | Jede Ausgabe hat einen eindeutigen Pfad | `test_output_reservation.py` |
| A4 | Keine stillen Überschreibungen | `test_output_reservation.py`, `test_media_ai_workspace.py` |
| A5 | Jede Änderung ist getestet | 623 Fälle, Gates in `CLAUDE.md` |

---

## B — Kernfunktionen

| ID | Anforderung | Status | Nachweis |
|----|-------------|--------|----------|
| B1 | Medien konvertieren (Presets, Batch) | erfüllt | `test_core_flows.py` |
| B2 | Download von YouTube und ÖR-Mediatheken | erfüllt | `test_download_publish.py` |
| B3 | DVD-Authoring und ISO-Erstellung | erfüllt | `test_disc_flows.py` |
| B4 | Disc rippen (ungeschützte Medien) | erfüllt | `test_ripper_iso_types.py` |
| B5 | Disc kopieren über Abbild | erfüllt | `test_disc_copy_flow.py` |
| B6 | Brennen auf Rohling | **nicht hardwareverifiziert** | kein Rohling — Blocker B3 |
| B7 | Untertitel per Whisper | erfüllt (Quellstand) | `release_smoke.py` — derzeit blockiert |
| B8 | Videoschnitt: Trim, Merge, Highlights | erfüllt | `test_core_flows.py` |
| B9 | Upscaling und Interpolation | erfüllt (Quellstand) | `release_smoke.py` — derzeit blockiert |
| B10 | Mediathek mit Suche | erfüllt | `test_library_search.py` |

---

## C — Output Management (P1)

| ID | Anforderung | Status | Nachweis |
|----|-------------|--------|----------|
| C1 | Dateiname des Ergebnisses sichtbar | erfüllt | `test_job_output_access.py` |
| C2 | Vollständiger Pfad sichtbar | erfüllt | dito |
| C3 | „Ordner öffnen" je Auftrag | erfüllt | dito |
| C4 | „Datei öffnen" je Auftrag | erfüllt | dito |
| C5 | Immer der tatsächliche Job-Ausgabeordner | erfüllt | `test_open_output_folder_follows_a_download_out_of_the_output_tree` |
| C6 | Keine Überschreibung bei gleichem Namen | erfüllt | `test_output_reservation.py` (24 Fälle) |
| C7 | Ergebnis als Quelldatei weiterverwenden | **offen** | Ticket P3-4 |

---

## D — Nachvollziehbarkeit (P1)

| ID | Anforderung | Status | Nachweis |
|----|-------------|--------|----------|
| D1 | Sieben Schritte der Downloadstrecke sichtbar | erfüllt | `test_pipeline_visibility.py` |
| D2 | Jobstatus überlebt einen Neustart | erfüllt | `job_history.py`, `test_download_workflow.py` |
| D3 | Gepackte EXE schreibt Pipeline-Logs | **Quellstand belegt, Artefakt offen** | `test_release_logging.py`; Blocker B1 |
| D4 | Eine Logdatei je Tag unter `Logs/` | erfüllt | `test_media_root_and_logs.py` |
| D5 | Logordner aus der Anwendung erreichbar | erfüllt | `test_environment_and_support.py` |
| D6 | Keine erfundenen Versions- oder Pfadangaben | erfüllt | dito |
| D7 | Fehlerursache bleibt am Job sichtbar | erfüllt | `renderJobs`, `job_record` |
| D8 | Fehlermeldungen ohne Werkzeug-Rohtext | **teilweise** | Media AI ja; Konverter/Rip offen → P2-3 |

---

## E — Konfiguration und Ablage (P2)

| ID | Anforderung | Status | Nachweis |
|----|-------------|--------|----------|
| E1 | Eine zentrale Konfiguration, keine Umgehung | erfüllt | `test_core_flows.py`, `test_media_root_and_logs.py` |
| E2 | Medienordner einmal wählen | erfüllt | `test_media_root_and_logs.py` |
| E3 | Struktur Downloads/Videos/Temp/Logs | erfüllt | dito |
| E4 | Externe Werkzeuge über Konfiguration | erfüllt | `ToolPaths`, Einstellungen |
| E5 | Windows-Pfade sauber (Unicode, reservierte Namen, lange Titel) | erfüllt | `test_media_ai_workspace.py` |
| E6 | Erststart führt durch die Einrichtung | **offen** | Ticket P2-6 |
| E7 | Verwaiste Temp-Verzeichnisse aufräumen | **offen** | Ticket P2-5 |

---

## F — Media AI Pipeline (P2)

| ID | Anforderung | Status | Nachweis |
|----|-------------|--------|----------|
| F1 | Import über yt-dlp in eine Mappe je Titel | erfüllt | `test_media_ai_pipeline.py` |
| F2 | Feste Struktur je Mappe | erfüllt | `test_media_ai_workspace.py` |
| F3 | Audio als WAV/PCM/16 kHz/mono | erfüllt | `test_audio_is_extracted_as_pcm_16k_mono` |
| F4 | Video ohne Neukodierung | erfüllt | `test_video_is_copied_not_reencoded` |
| F5 | Transkriptionsschnittstelle | erfüllt | `test_media_ai_pipeline.py`; ADR-003 |
| F6 | Voice-Cloning-Schnittstelle vorbereitet | erfüllt (Schnittstelle) | Backend offen → MA-6 |
| F7 | Frame-Extraktion | erfüllt | `VideoProcessor.extract_frames` |
| F8 | Vision-Schnittstelle vorbereitet | erfüllt (Schnittstelle) | Backend offen → MA-7 |
| F9 | Oberflächenbereich „Media AI" | erfüllt | `test_media_ai_bridge.py` |
| F10 | Transkript in der Oberfläche sichtbar | **offen** | Ticket MA-8 |
| F11 | Playlist-Verhalten benannt | **offen** | Ticket MA-9 |
| F12 | Echtlauf der Medienstrecke belegt | **blockiert** | Blocker B1 |

---

## G — Auslieferung

| ID | Anforderung | Status | Nachweis |
|----|-------------|--------|----------|
| G1 | Kein Konsolenfenster beim Start | erfüllt | Runtime-Gate im Journal |
| G2 | RetroDisc-Icon in Titelbalken und Taskleiste | erfüllt | `verify_app_icon.py` |
| G3 | Fünf Startaktionen bei 100/125/150 % sichtbar | erfüllt | `verify_home_layout.py` — Gate unzuverlässig → P2-7 |
| G4 | WebView-History verlässt die App nicht | erfüllt | `test_webview_navigation.py` |
| G5 | Artefakte signiert | **Development-Zertifikat** | Blocker B2 |
| G6 | Build aus eingefrorenem Commit | **offen** | Blocker B4 |
| G7 | Eine Versionsquelle | erfüllt | `test_environment_and_support.py` |

---

## Erhebungsregel

Ein Eintrag wird nur dann auf *erfüllt* gesetzt, wenn ein Test oder eine
Messung ihn belegt. Aussagen über gebaute Artefakte gelten ausschließlich für
den SHA-256, an dem sie gemessen wurden. Ein Nachweis, der auf einem
blockierten Werkzeug beruht, gilt als **nicht erbracht** — auch dann, wenn
die Suite grün ist.
