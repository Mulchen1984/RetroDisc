# RetroDisc — Daten- und Ablaufmodell

Der Modulaufbau steht in **`CLAUDE.md`** unter „Aufbau" und wird hier nicht
wiederholt. Dieses Dokument beschreibt die beiden Dinge, an denen bisher die
meisten Fehler entstanden sind und die man dem Code nicht an einer einzigen
Stelle ansieht: **wo Dateien liegen** und **wie ein Auftrag durchläuft**.

Stand: 2026-09-06

---

## 1. Wo Dateien liegen

Es gibt genau zwei Wurzeln. Alles andere leitet sich ab.

### Medienordner — was der Nutzer sieht

Einstellbar, Vorgabe `%USERPROFILE%\RetroDisc`. Der Nutzer wählt ihn einmal
in den Einstellungen; die Unterordner entstehen automatisch.

```
<media_root>                     directories.media_root
 ├── Downloads                   directories.download_dir   (je Auftrag ein Unterordner)
 ├── Videos                      directories.output_dir     (fertige Ergebnisse)
 ├── Temp                        directories.temp_dir       (DVD-Zwischendateien)
 ├── Logs                        directories.log_dir        (retrodisc_YYYY-MM-DD.log)
 ├── library.db                  directories.library_db
 └── jobs.sqlite3                Jobhistorie
```

### Anwendungsdaten — was der Nutzer nicht sieht

`%LOCALAPPDATA%\RetroDisc`: `settings.json`, `tools/` (nachgeladene
Werkzeuge), `complete.wav`.

### Die Regeln

1. **Jede Komponente bezieht ihre Pfade aus `AppSettings`.** Kein Modul legt
   seinen Ort selbst fest. Wer das doch tat, war ein Befund — die
   Mediathek schrieb lange nach `~/.retrodisc`.
2. **`_apply_runtime_settings` zieht alles nach.** Wer eine neue Komponente
   mit einem Pfad anlegt, trägt sie dort ein. Sonst arbeitet sie nach einer
   Einstellungsänderung weiter auf dem alten Ort.
3. **`MEDIA_SUBFOLDERS` ist die eine Tabelle.** `DirectorySettings.derived()`
   und `ensure_directories()` lesen beide daraus. Ein neuer Unterordner wird
   dort eingetragen, nirgends sonst.
4. **`set_media_root()` ist der einzige Weg, der Einzelordner ersetzt.**
   Normales Speichern lässt bewusst abweichend gesetzte Ordner in Ruhe.

### Ausgabedateien: reservieren, nicht prüfen

`src/core/output.py` ist die einzige Stelle, die Zielnamen vergibt.

- `claim_unique_target(pfad)` reserviert **atomar** (`O_CREAT | O_EXCL`) und
  weicht einem belegten Namen mit `" (1)"`, `" (2)"` … aus.
- `claim_target_group(pfade, stamm)` hält zusammengehörende Dateien — Video
  und Untertitel — unter demselben Zähler zusammen.
- `timestamped(pfad)` für Namen, die sonst bei jedem Lauf gleich hießen, etwa
  ein Rip, dessen Name nur aus dem Laufwerksbuchstaben besteht.

**Warum atomar und nicht `exists()`:** Zwei parallele Veröffentlichungen sehen
sonst denselben freien Namen, und die zweite überschreibt die erste
klanglos. Das exklusive Öffnen ist ein einziger Syscall und schließt das
Fenster.

**Reserviert wird zur Ausführungszeit, nicht beim Einreihen.** Ein Auftrag,
der in der Warteschlange abgebrochen wird, soll keine leere Datei
hinterlassen. `RetroDiscBridge._with_reserved_output` kapselt das: reservieren,
Handler laufen lassen, bei Fehlschlag den Namen wieder freigeben.

**Wer reserviert, muss überschreiben dürfen.** Am reservierten Namen liegt die
eigene leere Datei; die Existenzprüfung in `FFmpeg.convert` wäre dort ein
Fehlalarm. Deshalb `overwrite=True` auf reservierten Zielen — und nur dort.

**Bewusste Ausnahme:** `convert_file` reserviert nicht. Dort steuert der
Nutzer das Überschreiben über eine Checkbox, und die Fehlermeldung nennt die
Lösung. Das ist gewolltes Verhalten.

---

## 2. Wie ein Auftrag durchläuft

### Die Kette

```
UI (app.html)
  → RetroDiscApi          schlanker Proxy, den PyWebView bekommt
  → RetroDiscBridge       baut den Job, kennt die Einstellungen
  → Pipeline.submit       Warteschlange, Handler pro Job
  → Handler               die eigentliche Arbeit
  → Job-Ereignisse        zurück an die UI über evaluate_js
```

`scripts/verify_ui_bridge.py` prüft diese Kette auf fehlende Proxys, fehlende
Bridge-Ziele und Arity-Fehler. **Jede neue Bridge-Methode braucht ihren
Proxy in `RetroDiscApi`**, sonst ist der Knopf in der Oberfläche tot.

### Der Handler gehört zum Job, nicht zum Typ

`Pipeline._job_handlers` bildet Job-Id auf Handler ab. Ein reines
Typ-Register würde den Handler eines noch wartenden Jobs beim nächsten Submit
desselben Typs ersetzen.

### Wo ein Zustand sichtbar wird — drei Orte, gleiche Wahrheit

| Ort | Zweck | Quelle |
|-----|-------|--------|
| Jobzeile in der Oberfläche | laufender Blick | `get_queue()` alle 2 s + Ereignisse |
| `jobs.sqlite3` | überlebt den Neustart | `Pipeline.history.save()` |
| `retrodisc_YYYY-MM-DD.log` | Supportfall ohne laufende App | `structlog` + stdlib |

Ein Schritt, der nur an einem dieser Orte auftaucht, ist ein Befund. Die
Downloadstrecke schreibt deshalb in `stage()` alle drei gleichzeitig.

### Die Schritte der Downloadstrecke

`src/services/download_workflow.WORKFLOW_STAGES` ist die verbindliche Liste:

```
Quelle erkannt → Download gestartet → Download abgeschlossen
  → Verarbeitung gestartet → Konvertierung läuft → Datei erstellt → Fertig
```

`stage(name, progress=None)` heißt „nur beschriften": beim Konvertieren
liefert FFmpeg den Fortschritt selbst, ein fester Wert ließe den Balken
zurückspringen.

### Ein fertiger Job muss seinen Pfad melden

`_on_complete` sendet `output`. Die Oberfläche zeigt daraus Dateinamen,
vollständigen Pfad und die beiden Knöpfe. **Ein Ergebnis ohne sichtbaren Pfad
ist unfertig** — das war der Ausgangsbefund des gesamten Umbaus.

---

## 3. Media AI Pipeline

`src/services/media_ai/` ist additiv: es **steuert** die vorhandenen
Bausteine, statt sie zu ersetzen. `Downloader`, `FFmpeg`, `Pipeline` und
`SubtitleGenerator` sind unverändert.

| Baustein | Aufgabe | steuert |
|---|---|---|
| `MediaDownloader` | Titel ermitteln, Mappe anlegen, laden | `core.downloader.Downloader` |
| `MediaSplitter` | Audio- und Videospur trennen | `core.ffmpeg.FFmpeg.convert` |
| `AudioProcessor` | Transkription, Sprachausgabe | Backend-Protokoll |
| `VideoProcessor` | Frame-Extraktion, Bildanalyse | `ffmpeg`, Backend-Protokoll |
| `MediaWorkspace` | die Mappe je Titel, feste Dateinamen | — |
| `MediaJob` | Zustand des Imports in `metadata.json` | — |

### Die Arbeitsmappe

Eine Mappe je Titel unter `directories.download_dir`, mit festen Namen:
`original.<ext>`, `video.<ext>`, `audio.wav`, `transcript.txt`,
`metadata.json`, `frames/`.

**Bewusst kein eigener `Media/`-Zweig.** Ein zweiter Downloadbaum neben dem
eingestellten wäre genau der Fehler, den die Ordnerkonsolidierung beseitigt
hat: Dateien, die der Nutzer dort sucht, wo sie nicht liegen.

`metadata.json` ist der Zustand, nicht Beiwerk. Es überlebt den Neustart und
sagt der Oberfläche, welcher Schritt noch angeboten wird. Geschrieben wird es
atomar (Temp-Datei plus `os.replace`), wie `AppSettings.save`.

### Die Schritte des Imports

`workflow.MEDIA_AI_STAGES` ist die verbindliche Liste; ein Test prüft
Vollständigkeit und Reihenfolge:

```
Quelle wird gelesen → Arbeitsmappe angelegt → Download läuft
  → Download abgeschlossen → Videospur wird getrennt
  → Audiospur wird extrahiert → Fertig
```

Jeder Schritt landet gleichzeitig an drei Orten — Jobzeile, `metadata.json`,
Logfile. Die Fortschrittsabschnitte: Probe 0–3 %, Download 5–60 %, Video
62–80 %, Audio 80–98 %, Abschluss 100 %. `_PhaseProgress` rechnet den
Werkzeugfortschritt in seinen Abschnitt um und lässt Abbruch und
Prozessbesitz beim echten Job.

### Reihenfolge beim Import

Erst den Titel ermitteln, **dann** die Mappe anlegen, dann hineinladen. Nur so
heißt der Ordner nach dem Medium statt nach einer Job-Id, und
`original.<ext>` trägt die Endung, die yt-dlp wirklich geliefert hat.

`create_workspace` legt mit `mkdir` ohne `exist_ok` an — atomar, und ein
zweiter Import desselben Titels bekommt `" (1)"`. Nach dem Download ist der
Ablauf **fehlertolerant an den Rändern**: schlägt das Trennen einer Spur fehl,
bleibt der Import erfolgreich und der Grund steht in `metadata.json` unter
`errors`. Eine reine Tonquelle hat keine Videospur — das ist eine Eigenschaft
der Quelle, kein Fehlschlag.

### Formatvorgaben, die die Pipeline zusichert

- **Audio:** `pcm_s16le`, 16 kHz, mono. Genau das erwartet Whisper intern, und
  gängige Voice-Cloning-Modelle nehmen es als Eingabe. Späteres Umrechnen
  entfällt.
- **Video:** `-c:v copy`, `-an`. Kein Grund neu zu kodieren; das erhält die
  Qualität und ist um Größenordnungen schneller.

### KI-Schnittstellen: vorbereitet, nicht integriert

Dreiteiliges Muster je Fähigkeit: ein `Protocol`, ein Vorgabe-Backend, und ein
Prozessor, der nur das Protokoll kennt. Backends kommen über den Konstruktor —
**keine Modellimporte auf Modulebene**, sonst wächst die gepackte EXE um
Abhängigkeiten, die niemand benutzt. Aus demselben Grund steht auch der
Whisper-Import in der Methode, nicht im Kopf der Datei.

Für die Transkription ist das Vorgabe-Backend der bereits vorhandene
`SubtitleGenerator`. Für Sprachausgabe und Bildanalyse wirft der Platzhalter
einen Satz, der sagt, wo ein Backend angeschlossen wird — statt
`AttributeError` oder stiller Untätigkeit.

---

## 4. Zwei Fallen, die schon zugeschlagen haben

### Der windowed Build hat keine Standardströme

`retrodisc_final.spec` baut mit `console=False`. Dort ist `sys.stdout` `None`.

- Wer nur nach stdout protokolliert, protokolliert **nichts**. Genau so
  verschwand die gesamte structlog-Ausgabe der Medienpipeline auf
  `os.devnull`, während im Logfile nur die Launcher-Zeilen standen.
- `configure_structlog(stream, logfile=...)` schreibt deshalb immer auch in
  die Datei.

### cp1252 kann Dateinamen aus dem Netz nicht darstellen

Windows liefert Standardströme mit der ANSI-Codepage. Ein YouTube-Titel mit
Emoji oder CJK löst beim **bloßen Loggen** einen `UnicodeEncodeError` aus.
Liegt so ein Logaufruf in einem `try`, dessen `except` den Job scheitern
lässt, wird aus fertiger Arbeit ein Fehler — am 2026-09-05 genau so passiert.

- `src/utils/logging_setup.py` stellt alle Ströme auf UTF-8 mit
  `errors="replace"`.
- Erfolgsmeldungen stehen **außerhalb** des `try`, das den Job scheitern
  lassen kann.
- Diese Fehlerklasse findet **kein** Source-Gate: pytest, Smoke und
  `verify_core` laufen alle auf einem UTF-8-fähigen Kanal, die gebaute
  Anwendung nicht.
