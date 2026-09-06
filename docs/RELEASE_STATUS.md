# RetroDisc — Freigabereife

Ein Blick auf die Frage: **kann das ausgeliefert werden?**

Kurze Antwort: nein — aber deutlich näher als heute früh. B1 ist am 06.09.
entfallen, damit laufen alle Gates wieder. Es fehlt der **Build aus dem
eingefrorenen Stand**; die vorhandenen Artefakte sind vom 05.09.

Stand: 2026-09-06 · Branch `release-signing` · letzter Commit `ca99a05` · gepusht

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

Zwei verhindern die Freigabe, beide **nicht durch Code lösbar**. B1 und B4
sind am 06.09. entfallen und bleiben als Nachweis stehen.

### ~~B1 — Vendor-Binaries blockiert~~ — **entfallen am 2026-09-06**

Die Richtlinie blockiert die Binaries nicht mehr; sie wurde dabei **nicht
umgangen und nicht verändert**. Belegt:

```
vendorfmpeg.exe  ->  ffmpeg version N-126342-gf88b741dbf-20260831
vendor\yt-dlp.exe  ->  2026.08.19
```

Alle Gates, die echte Medienarbeit fahren, laufen wieder:
`.hermes/verify_core.py` **0**, `scripts/release_smoke.py` **0**,
`scripts/run_acceptance.py` **PASS** (source 6/6, packaged 7/7) — inklusive
eines echten YouTube-Downloads mit koreanischem Titel, also des
cp1252-Falls.

**Nicht als dauerhaft annehmen.** Smart App Control entscheidet **je Datei**.
Dass diese Hashes jetzt starten, sagt nichts über andere — insbesondere nicht
über eine **neu gebaute** `dist\RetroDisc.exe`, die einen neuen Hash bekommt.
Ein erneuter Block beim nächsten Build ist möglich und wäre kein Rückschritt
im Code.

### B5 — Kein Build aus dem eingefrorenen Stand

Mit B1 ist der Bauweg wieder offen, aber noch nicht gefahren. Solange das
nicht geschehen ist, gilt für den ausgelieferten Zustand nur, was am
Quellstand belegt ist. Das betrifft D3/R3 (Logging im windowed Build), F12
(Media AI am Artefakt) und R1 (die Artefakte selbst).

Nächster Schritt: `python build.py --clean --sign`, danach
`scripts/verify_release_artifacts.py --require-signed` und ein Runtime-Gate.

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

Dasselbe gilt für die **packaged**-Ebene von `run_acceptance.py`: sie meldet
7/7, fährt dabei aber genau diese alte EXE. Der Nachweis gilt für den Stand
vom 05.09., nicht für die Arbeit danach.

### R2 — Ein grüner Testlauf belegt die Medienstrecke nicht

`test_download_workflow.py` überspringt seinen Echtlauf bei WinError 4551
statt fehlzuschlagen (ADR-006). Das macht die Suite ehrlich, lässt aber echte
Defekte durch, solange der Skip greift.

**Das ist keine Theorie mehr.** Am 06.09., als die Richtlinie den Block
aufhob, lief der Test zum ersten Mal — und fiel sofort über eine Regression,
die seit `2132e36` im Repository lag: der Test führte eine eigene Kopie der
Schrittnamen, die beim Umbenennen nicht mitgezogen wurde. Der Block hatte das
verdeckt, und der Fehler ist mit dem Freeze in die gepushte Historie gewandert.
Behoben in `ca99a05`; die Kopie ist durch `WORKFLOW_STAGES` ersetzt.

**Lehre:** Ein Skip ist eine Schuld, kein Ergebnis. Wer freigibt, muss auf die
Skips sehen, nicht nur auf die Farbe — und ein Skip, der lange steht, gehört
in einer Umgebung nachgeholt, in der er nicht greift.

### R3 — Das Release-Logging ist nur am Quellstand belegt

Der ganze Punkt von P1-4 ist der windowed Build, in dem `sys.stdout` `None`
ist. Genau dort ist es nicht nachgemessen. Mit B1 ist das jetzt **prüfbar**
und nur noch nicht geprüft: es braucht einen Build (B5) und danach einen Lauf
der gepackten EXE, dessen Logfile Zeilen aus `src.core.pipeline` enthält.

### ~~R4 — Der eingefrorene Stand liegt nur auf einem Rechner~~ — **geschlossen am 2026-09-06**

Am 05.09. hat eine fremde Sitzung den Branch gewechselt; am 06.09. lag
uncommittete Fremdarbeit im Baum (Jobhistorie, Download-Workflow). Beides ging
gut aus, war aber Zufall.

Der Branch `release-signing` ist nach `origin` gepusht
(`949fccc..5b6f1de`, Fast-Forward). Der Stand liegt damit nicht mehr nur auf
diesem Rechner.

Vor dem Push geprüft: keine uncommitteten Änderungen; Historie durchgesehen;
Mustersuche nach Zugangsdaten in allen hinzugefügten Zeilen ohne Treffer;
**null** neue Personenbezüge (`CLAUDE.md` enthielt schon vor dem Push acht
Pfade mit dem Benutzernamen); `dist/`, `Output/`, `build/`, `vendor/`,
`.venv/`, `RetroDisc_Data/` und `__pycache__/` sind über `.gitignore`
ausgeschlossen und mit **0** Dateien getrackt.

**Was offen bleibt:** die Sichtbarkeit des Repositorys konnte nicht geprüft
werden — `gh` ist auf diesem Rechner nicht angemeldet. Ist
`Mulchen1984/RetroDisc` öffentlich, dann sind die Pfade mit dem Benutzernamen
in `CLAUDE.md` öffentlich; das war schon vor diesem Push so und ist keine neue
Preisgabe, aber eine bewusste Entscheidung wert.

### R5 — Die EXE liegt bei rund 500 MB

Vor dem Anschluss eines Voice- oder Vision-Modells (MA-6, MA-7) ist zu
klären, wie das Modell ausgeliefert wird. Ein Bündeln würde die Artefaktgröße
weiter treiben; ein Nachladen widerspricht dem lokalen Betrieb.

---

## Commit-Plan zu B4 — ausgeführt

Acht Commits, jeder fachlich für sich prüfbar, dazu ein neunter, der den
Freeze dokumentiert. Reihenfolge ist Absicht: die Reservierung liegt
zuunterst, weil alles Weitere sie benutzt.

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

1. **B5 — bauen.** `python build.py --clean --sign` aus dem eingefrorenen
   Stand, dann `verify_release_artifacts.py --require-signed` und ein
   Runtime-Gate. Das schließt R1 und R3 und belegt D3 und F12. Der mit
   Abstand größte Einzelschritt, jetzt wo B1 weg ist.
2. **P2-8** — das Artefakt-Gate soll melden, wenn die Artefakte älter sind als
   die jüngste Quelldatei; genau diese Falle hat heute zugeschlagen.
3. **P2-3** — die letzten Werkzeug-Rohtexte aus der Oberfläche.
