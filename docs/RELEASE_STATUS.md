# RetroDisc — Freigabereife

Ein Blick auf die Frage: **kann das ausgeliefert werden?**

Kurze Antwort: nein, und zwar aus drei Gründen, von denen **keiner** im Code
liegt. Der Quellstand ist so weit und seit dem 06.09. eingefroren; belegt ist
er am Artefakt nicht.

Stand: 2026-09-06 · Branch `release-signing` · letzter Commit `24c87ca`

---

## FERTIG

Belegt durch Test oder Messung. Die Nachweise stehen in
`docs/REQUIREMENTS.md`, die Messungen im Journal.

**Output Management**
- Dateiname, vollständiger Pfad, „Ordner öffnen", „Datei öffnen" je Auftrag
- „Output öffnen" folgt dem tatsächlichen Job-Ausgabeordner, nicht mehr einem
  festen Pfad — der Downloadfall ist eigens getestet
- Keine stillen Überschreibungen: eine Reservierungsstelle
  (`src/core/output.py`), atomar über `O_CREAT | O_EXCL`, angewandt auf Rip,
  ISO, DVD-ISO, sechs Werkzeugausgaben und die Media-AI-Ausgaben

**Nachvollziehbarkeit**
- Sieben benannte Schritte der Downloadstrecke, gleichzeitig in Jobzeile,
  Jobhistorie und Logfile
- Jobhistorie überlebt den Neustart (`jobs.sqlite3`)
- Eine Logdatei je Tag unter `Logs/`, aus der Anwendung erreichbar
- Keine erfundenen Versions- oder Pfadangaben mehr; was nicht gemessen werden
  kann, heißt „unbekannt"

**Konfiguration**
- Eine zentrale Konfiguration; die letzten beiden Umgehungen (Mediathek,
  `dvd_workflow.temp_dir`) sind beseitigt
- Medienordner einmal wählen, Struktur Downloads/Videos/Temp/Logs entsteht
- Windows-Pfade: Unicode, reservierte Gerätenamen, lange Titel

**Media AI Pipeline**
- Import über yt-dlp in eine Mappe je Titel mit fester Struktur
- Audio als WAV/PCM/16 kHz/mono, Video ohne Neukodierung
- Schnittstellen für Transkription, Voice-Cloning und Bildanalyse; Whisper
  über den vorhandenen `SubtitleGenerator` angeschlossen
- Oberflächenbereich mit Mappenliste und Zustandsabzeichen

---

## IN ARBEIT

| Ticket | Punkt | Warum es zählt |
|--------|-------|----------------|
| P2-3 | Fehlermeldungen bei Konvertieren und Rippen enthalten noch Werkzeug-Rohtext | Media AI übersetzt bereits; die älteren Pfade nicht |
| P2-5 | Verwaiste Temp-Verzeichnisse nach hartem Abbruch | füllt unbemerkt den Medienordner |
| P2-6 | Erststart-Dialog (`first_run` wird nirgends gelesen) | der erste Eindruck entscheidet, ob der Nutzer seinen Ordner kennt |
| P2-7 | `verify_home_layout.py` ist unter Last unzuverlässig | ein Gate, das zufällig fehlschlägt, taugt nicht als Freigabekriterium |
| MA-8 | Transkript nur im Ordner sichtbar, nicht in der Oberfläche | |
| MA-9 | Playlists werden per `--no-playlist` stillschweigend auf das erste Video reduziert | die Oberfläche sagt es nicht |
| P3-4 | Ergebnis als Quelldatei übernehmen | Kette Rippen → Schneiden → Brennen zwingt über den Explorer |

---

## BLOCKIERT

Diese drei verhindern die Freigabe. **Keiner davon ist durch Code lösbar.**
B4 ist am 06.09. entfallen und bleibt unten als Nachweis stehen.

### B1 — Vendor-Binaries von der Anwendungssteuerungsrichtlinie blockiert

`vendor/ffmpeg.exe` (145 852 928 Bytes, SHA-256 `6834A793…`) ist **NotSigned**
und wird von Smart App Control blockiert. Auch der direkte Aufruf scheitert:

```
Eine Anwendungssteuerungsrichtlinie hat diese Datei blockiert   (WinError 4551)
```

**Folge.** `.hermes/verify_core.py`, `scripts/release_smoke.py` und der
Bauweg sind auf diesem Host nicht lauffähig. Die echte Medienstrecke — yt-dlp
und ffmpeg — ist seit dem 05.09. nicht mehr gefahren worden. Geprüft ist die
Ablauf-, Pfad- und Aufruflogik; **nicht** das Ergebnis der Werkzeuge.

**Nicht umgehen.** Die Richtlinie wird nicht abgeschaltet und nicht verändert;
ein Abschalten ist unter Windows nur durch eine Neuinstallation reversibel.
Der Weg nach vorn ist ein Host, auf dem die Binaries laufen, oder signierte
Vendor-Binaries.

### B2 — Keine öffentlich vertrauenswürdige Code-Signatur

Signiert wurde mit `CN=RetroDisc Development`. Auf diesem Rechner meldet
`Get-AuthenticodeSignature` `Valid`, weil die ausstellende Wurzel hier
vertraut wird — auf jedem anderen System liest dieselbe Datei als
`UntrustedRoot`. Beschaffungsfrage, keine Codefrage.

### B3 — Physischer Brenn- und Rücklesetest fehlt

Kein Rohling vorhanden. Die physischen Disc-Pfade gelten als **nicht
hardwareverifiziert** und sind so zu kennzeichnen.

### ~~B4 — Arbeitsbaum nicht eingefroren~~ — **erledigt am 2026-09-06**

Der Plan wurde in acht Commits umgesetzt; der Arbeitsbaum ist sauber. Damit
ist die Voraussetzung aus `CLAUDE.md` erfüllt, nur aus einem eingefrorenen
Commit zu bauen.

| # | Hash | Inhalt |
|---|------|--------|
| 1 | `d33c414` | Reserve every output name in one place |
| 2 | `b412d3e` | Keep job state across restarts |
| 3 | `2132e36` | Show every step of the download pipeline |
| 4 | `bff5002` | Derive every media folder from one media root |
| 5 | `bce715a` | Write pipeline logs from the windowed build |
| 6 | `62e37ec` | Add the media AI pipeline as a separate service layer |
| 7 | `76977f1` | Surface results, real environment data and media AI in the UI |
| 8 | `24c87ca` | Document architecture, decisions, requirements and release status |

44 Dateien, 6523 Einfügungen, 162 Löschungen gegenüber `949fccc`.

Der Branch liegt **8 Commits vor `origin/release-signing`**. Es wurde nicht
gepusht.

**Einschränkung, die zum Schnitt gehört:** die Commits 1–6 sind fachlich
abgegrenzt, aber nicht einzeln grün. Die Tests der unteren Schichten greifen
teilweise auf `retrodisc_launcher.RetroDiscBridge` zu, das erst mit Commit 7
kommt — die Bridge ist eine einzelne große Datei und lässt sich nicht sinnvoll
aufteilen. Grün ist der Stand ab `76977f1`; ein `git bisect` über diesen
Bereich braucht deshalb `HEAD` als Referenz.

---

## RISIKEN

Dinge, die heute nicht wehtun und beim Release wehtun würden.

### R1 — Die vorhandenen Artefakte sind veraltet, das Artefakt-Gate ist trotzdem grün

`scripts/verify_release_artifacts.py` meldet **PASS, 0 Befunde**. Es prüft
aber die Dateien, die im Baum liegen:

| Artefakt | Datum | SHA-256 |
|---|---|---|
| `dist\RetroDisc.exe` | 05.09.2026 22:08 | `DA9AC5A2…` |
| `Output\RetroDisc_1.0.0_Portable.zip` | 05.09.2026 22:08 | `02BDDBA3…` |
| `Output\RetroDisc_Setup_1.0.0.exe` | 05.09.2026 22:09 | `E3EC838E…` |

Die neueste Quelldatei stammt vom **06.09.2026 13:03**. Diese Artefakte
enthalten **nichts** aus den vier Arbeitsdurchläufen — kein Output Management,
kein Release-Logging, keine Media AI Pipeline.

**Das Risiko ist die Fehldeutung**, nicht das Gate: „Artefakt-Gate grün" darf
nicht als „Release ist fertig" gelesen werden. Nach dem nächsten Build sind
diese drei Hashes ungültig.

### R2 — Ein grüner Testlauf belegt die Medienstrecke nicht

Seit heute überspringt `test_download_workflow.py` seinen Echtlauf bei
WinError 4551 statt fehlzuschlagen (ADR-006). Das macht die Suite ehrlich —
eine dauerhaft rote Suite verdeckt die nächste echte Regression —, aber die
Zahl „588 passed" bedeutet jetzt weniger als vorher. Der Skip-Text nennt den
Grund, und `-rs` macht ihn im Lauf sichtbar. **Wer freigibt, muss auf die
Skips sehen, nicht nur auf die Farbe.**

### R3 — Das Release-Logging ist nur am Quellstand belegt

Der ganze Punkt von P1-4 ist der windowed Build, in dem `sys.stdout` `None`
ist. Genau dort ist es nicht nachgemessen, weil nicht gebaut werden kann (B1).
Der Nachweis ist ein Lauf der gepackten EXE, dessen Logfile Zeilen aus
`src.core.pipeline` enthält.

### R4 — Zwei Sitzungen im selben Arbeitsbaum

Am 05.09. hat eine fremde Sitzung den Branch gewechselt; am 06.09. lag
uncommittete Fremdarbeit im Baum (Jobhistorie, Download-Workflow). Beides ging
gut aus. Mit dem Einfrieren (B4) ist das Datenverlustrisiko deutlich kleiner,
aber nicht null: der Branch ist **nicht gepusht**, alles liegt weiterhin nur
auf diesem Rechner.

### R5 — Die EXE liegt bei rund 500 MB

Vor dem Anschluss eines Voice- oder Vision-Modells (MA-6, MA-7) ist zu
klären, wie das Modell ausgeliefert wird. Ein Bündeln würde die Artefaktgröße
weiter treiben; ein Nachladen widerspricht dem lokalen Betrieb.

---

## Commit-Plan zu B4

Sieben Commits, jeder für sich prüfbar. Reihenfolge ist Absicht: die
Reservierung liegt zuunterst, weil alles Weitere sie benutzt.

```
1  src/core/output.py  src/core/downloader.py  src/core/ffmpeg.py
   tests/test_output_reservation.py  tests/test_download_publish.py
   → "Reserve every output name in one place"

2  src/services/job_history.py  src/core/pipeline.py  src/models/media.py
   → "Keep job state across restarts"

3  src/services/download_workflow.py  src/services/converter.py
   tests/test_pipeline_visibility.py  tests/test_download_workflow.py
   → "Show every step of the download pipeline"

4  src/config/settings.py  src/services/dvd_workflow.py  src/services/ripper.py
   tests/test_media_root_and_logs.py  tests/test_core_flows.py
   → "Derive every media folder from one media root"

5  src/utils/logging_setup.py  tests/test_release_logging.py
   → "Write pipeline logs from the windowed build"

6  src/services/media_ai/  tests/test_media_ai_*.py
   → "Add the media AI pipeline as a separate service layer"

7  retrodisc_launcher.py  src/ui/app.html  src/__init__.py  src/acceptance.py
   tests/test_job_output_access.py  tests/test_convert_tab_config.py
   tests/test_environment_and_support.py  tests/test_media_ai_bridge.py
   tests/test_acceptance_harness.py  tests/test_disc_copy_flow.py
   tests/test_drive_detection_ui.py
   → "Surface results, real environment data and media AI in the UI"

8  docs/  RELEASE_AUDIT_STATUS.md
   → "Document architecture, decisions, requirements and release status"
```

**Ausgeführt am 2026-09-06.** Die Hashes stehen oben unter B4.

---

## Was als Nächstes den größten Unterschied macht

1. **B1 auflösen** — einen Host, auf dem die Vendor-Binaries laufen. Erst
   danach lassen sich B6, D3, F12 und R3 überhaupt belegen. Das ist jetzt der
   einzige Punkt, der weitere Arbeit am Code blockiert.
2. **P2-3** — die letzten Werkzeug-Rohtexte aus der Oberfläche.
3. **P2-8** — das Artefakt-Gate soll melden, wenn die Artefakte älter sind als
   die jüngste Quelldatei (siehe R1).
