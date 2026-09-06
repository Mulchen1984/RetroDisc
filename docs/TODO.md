# RetroDisc — Backlog

Dieses Dokument ist das **Backlog** des Projekts: was offen ist, in welcher
Reihenfolge, und warum. Es ergänzt die beiden vorhandenen Dokumente, ersetzt
sie nicht:

- **`CLAUDE.md`** — wie in diesem Repository gearbeitet wird (Runtime, Gates,
  Bauweg, Produktvorgaben). Verbindlich.
- **`RELEASE_AUDIT_STATUS.md`** — das Journal: was wann gemessen wurde, mit
  Belegen. Chronologisch, wird hinten angehängt, nie umgeschrieben.
- **`docs/TODO.md`** (dieses Dokument) — der Blick nach vorn. Wird
  umgeschrieben, sobald sich der Stand ändert.
- **`docs/REQUIREMENTS.md`** — Anforderungen und ihr Nachweis.
- **`docs/ARCHITECTURE.md`** — Pfad- und Ablaufmodell.
- **`docs/DECISIONS.md`** — Architekturentscheidungen mit Begründung.
- **`docs/RELEASE_STATUS.md`** — Freigabereife, Blocker, Risiken.

Ein Ticket verschwindet hier erst, wenn es **belegt** erledigt ist. Der Beleg
steht im Journal, nicht hier.

Stand: 2026-09-06 (nach Durchlauf 8; gepusht, B1 entfallen)

---

## Releaseblocker

Diese drei verhindern ein Release unabhängig vom Code.

| # | Blocker | Art | Zuständig |
|---|---------|-----|-----------|
| ~~B1~~ | ~~Vendor-Binaries von Smart App Control blockiert~~ — **entfallen 06.09.** Alle Gates laufen wieder; SAC entscheidet je Datei, ein neuer Build kann erneut blockiert werden. | Umgebung | — |
| **B5** | **Kein Build aus dem eingefrorenen Stand.** Der Bauweg ist wieder offen, aber nicht gefahren. Bis dahin gilt nur, was am Quellstand belegt ist. | Build | offen |
| B2 | **Keine öffentlich vertrauenswürdige Code-Signatur.** Das lokale Development-Zertifikat belegt die Pipeline, nicht die Weitergabefähigkeit. | Beschaffung | — |
| B3 | **Physischer Brenn- und Rücklesetest fehlt.** Kein Rohling vorhanden. | Hardware | — |

**~~B4 — Arbeitsbaum nicht eingefroren~~ — erledigt am 2026-09-06.** In acht
Commits umgesetzt (`d33c414` … `24c87ca`), Arbeitsbaum sauber. Hashes und
die Einschränkung zum Schnitt stehen in `docs/RELEASE_STATUS.md`.

---

## P1 — muss vor Release fertig sein

| ID | Aufgabe | Status |
|----|---------|--------|
| P1-1 | Ausgabedatei in der Oberfläche: Dateiname, vollständiger Pfad, „Ordner öffnen", „Datei öffnen" | **erledigt** — `tests/test_job_output_access.py` |
| P1-2 | „Output öffnen" folgt dem tatsächlichen Job-Ausgabeordner | **erledigt** — `_latest_output_dir()` |
| P1-3 | Keine stillen Überschreibungen (Rip, ISO, DVD-ISO, Werkzeugausgaben, Download-MP4) | **erledigt** — `src/core/output.py`, `tests/test_output_reservation.py` |
| P1-4 | Release-Logging: die gepackte EXE schreibt echte Pipeline-Logs | **am Quellstand erledigt** — Nachweis am Artefakt fehlt (B1) |
| P1-5 | Keine Platzhalterpfade im Konvertieren-Tab | **erledigt** — `tests/test_convert_tab_config.py` |
| P1-6 | Pipeline-Status: alle sieben Schritte sichtbar | **erledigt** — `WORKFLOW_STAGES`, `tests/test_pipeline_visibility.py` |
| P1-7 | Job-Historie überlebt einen Neustart | **erledigt** — `src/services/job_history.py` |
| P1-8 | Statusleiste und Werkzeugleiste zeigten erfundene Angaben | **erledigt** — `get_environment()`, `tests/test_environment_and_support.py` |
| P1-9 | Zugriff auf das Protokoll aus der Anwendung | **erledigt** — `open_log_folder()` |

## Media AI Pipeline

| ID | Aufgabe | Status |
|----|---------|--------|
| MA-1 | Import über yt-dlp in eine Arbeitsmappe je Titel | **erledigt** — `src/services/media_ai/` |
| MA-2 | Audiospur als WAV/PCM/16 kHz/mono | **erledigt** — `MediaSplitter.extract_audio` |
| MA-3 | Videospur ohne Neukodierung (`-c:v copy`) | **erledigt** — `MediaSplitter.extract_video` |
| MA-4 | Schnittstellen für Transkription, Voice-Cloning, Bildanalyse | **erledigt** — Protokolle + Vorgabe-Backends |
| MA-5 | Oberflächenbereich „Media AI" | **erledigt** — `#tab-mediaai` |
| **MA-6** | **Voice-Cloning-Backend anschließen** (XTTS/OpenVoice/QwenTTS). Die Schnittstelle steht, ein Modell fehlt. Vor der Integration klären: Modellgröße gegen EXE-Größe (die EXE liegt bereits bei ~500 MB). | offen (P3) |
| **MA-7** | **Vision-Backend anschließen.** Wie MA-6; `VideoProcessor(vision=...)`. | offen (P3) |
| **MA-8** | **Transkript-Anzeige in der Oberfläche.** `transcript.txt` wird erzeugt, aber nur im Ordner sichtbar. | offen (P2) |
| **MA-9** | **Playlists.** `--no-playlist` ist gesetzt; ein Playlist-Link importiert nur das erste Video. Bewusste Entscheidung, aber die Oberfläche sagt es nicht. | offen (P2) |

## P2 — sinnvoll

| ID | Aufgabe | Status |
|----|---------|--------|
| P2-1 | Zentrale Konfiguration: keine Komponente umgeht die Settings | **erledigt** — Bibliothek und `dvd_workflow.temp_dir` nachgezogen |
| P2-2 | Medienordner einmal wählen, Struktur darunter | **erledigt** — `DirectorySettings.derived()` |
| **P2-3** | **Bessere Fehlermeldungen.** Fehlgeschlagene Jobs zeigen bis zu 1200 Zeichen FFmpeg-/yt-dlp-Rohausgabe. Für Endanwender unlesbar. Kurzfassung in Klartext, Rohtext aufklappbar und im Log. | **offen** |
| P2-4 | Rip-Bereich hat kein „Neu suchen" | **erledigt** — Knopf ergänzt, Zähltest in `test_disc_copy_flow.py` durch eine Eigenschaftsprüfung ersetzt |
| **P2-5** | **Verwaiste Temp-Verzeichnisse.** Nach einem harten Abbruch bleiben `.retrodisc-*`, `retrodisc_rip_*`, `dvd_*`, `_temp_highlights_*` liegen. Beim Start aufräumen, nur diese Muster, nur älter als 24 h. | **offen** |
| **P2-8** | **Artefakte im Baum sind veraltet, das Artefakt-Gate ist trotzdem grün.** `verify_release_artifacts.py` prüft `dist/` und `Output/` vom 05.09., die nichts aus den Durchläufen 1–4 enthalten. Das Gate sollte melden, wenn die Artefakte älter sind als die jüngste Quelldatei. | **offen** |
| **P2-7** | **`verify_home_layout.py` ist unter Last unzuverlässig.** Mehrfachläufe ergaben PASS/FAIL/PASS/FAIL bei unverändertem Markup; im Leerlauf 10/10 PASS. `settle()` wartet nur zwei `requestAnimationFrame` ab, ohne Fonts-ready oder Layout-Stabilität. Ein Gate, das zufällig fehlschlägt, ist als Freigabekriterium unbrauchbar. | **offen** |
| **P2-6** | **Erststart-Dialog.** `settings.first_run` existiert in `src/config/settings.py` und wird nirgends gelesen. Einmal Medienordner bestätigen, Werkzeugstatus zeigen, Flag setzen. | **offen** |

## P3 — später

| ID | Aufgabe | Status |
|----|---------|--------|
| P3-1 | Versionsnummer widersprüchlich | **erledigt** — `src/__init__.py` ist die eine Quelle, Launcher und Oberfläche lesen von dort |
| **P3-2** | Log-Rotation. Seit P1-4 gibt es eine Datei pro Tag; alte Dateien werden nie aufgeräumt. | offen |
| **P3-3** | `pipeline._completed` wächst unbegrenzt; `get_queue()` liest `_queue`/`_running` ohne den Lock der Pipeline aus einem Fremdthread. | offen |
| **P3-4** | Ergebnis als Quelldatei übernehmen — die Kette Rippen → Schneiden → Brennen zwingt heute über den Explorer. | offen |
| **P3-5** | macOS-Reste (`BUILD_MACOS.sh`, `create_dmg.py`, `assets/retrodisc.icns`) sind an keinem Gate belegt. Entfernen oder wiederbeleben, sobald Windows steht. | offen |

---

## Arbeitsregeln für dieses Backlog

- Ein Punkt wandert erst nach **erledigt**, wenn ein Test oder eine Messung
  ihn belegt. Der Beleg gehört ins Journal.
- Aussagen über gebaute Artefakte gelten nur für den SHA-256, an dem sie
  gemessen wurden.
- Neue Befunde werden hier eingetragen, nicht nur im Journal beschrieben:
  das Journal ist chronologisch und beantwortet nicht die Frage „was ist
  jetzt offen".
