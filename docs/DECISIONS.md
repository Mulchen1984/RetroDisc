# RetroDisc — Architekturentscheidungen

Kurze Einträge, chronologisch, mit Datum. Jeder Eintrag beantwortet drei
Fragen: **Was** wurde entschieden, **warum**, und **was wäre die Folge**, wenn
jemand die Entscheidung später umdreht.

Eine Entscheidung wird hier nicht gelöscht, sondern durch eine neue ersetzt
und als *überholt* markiert. Das Journal (`RELEASE_AUDIT_STATUS.md`) belegt
die Messungen, dieses Dokument die Absicht.

---

## ADR-001 — Kein zweiter Media-Downloadbaum

**Datum:** 2026-09-06 · **Status:** aktiv

**Entscheidung.** Die Arbeitsmappen der Media AI Pipeline liegen unter dem
bereits konfigurierten `directories.download_dir`
(`<media_root>/Downloads/<Titel>/`). Der ursprünglich angefragte
Zwischenknoten `Media/` entfällt.

**Warum.** Der Ursprungsbefund dieser gesamten Arbeit war, dass Dateien für
den Nutzer verschwinden, weil es mehrere Ausgabebäume gab: `output_dir` unter
`~/Videos`, `download_dir` unter `~/Downloads`, dazu Temp mitten in der
Ausgabe und eine Mediathek unter `~/.retrodisc`. Der Knopf „Output öffnen"
führte nach einem Download in den falschen Ordner. Ein weiterer paralleler
Baum hätte genau diesen Fehler reproduziert — diesmal für die neue Funktion.

**Folge einer Umkehr.** „Ordner öffnen" und die Mappenliste müssten zwei
Wurzeln kennen; `media_ai_list` und die Pfadprüfung in der Bridge
(`_media_ai_workspace`) bekämen einen zweiten erlaubten Bereich. Der Nutzer
hätte wieder zwei Orte, an denen seine Dateien liegen können.

**Umgesetzt in.** `src/services/media_ai/workspace.py` (Modulkopf),
`retrodisc_launcher.RetroDiscBridge._media_ai_workspace`.

---

## ADR-002 — `MediaJob` ist Zustand der Mappe, keine zweite Queue

**Datum:** 2026-09-06 · **Status:** aktiv

**Entscheidung.** `MediaJob` beschreibt, was in einer Arbeitsmappe steht —
Herkunft, gelaufene Schritte, vorhandene Artefakte, Fehler — und wird in
`metadata.json` gehalten. Die *Ausführung* bleibt vollständig bei
`src/core/pipeline.Pipeline`; die Media-AI-Aufträge gehen als gewöhnliche
`Job`-Objekte durch `_submit_job`.

**Warum.** Eine zweite Warteschlange hätte alles doppelt gebraucht, was schon
existiert und funktioniert: Fortschrittsmeldungen an die Oberfläche, Abbruch
inklusive Prozessbaum, die dauerhafte Jobhistorie, die Ergebnisanzeige mit
Pfad und den beiden Knöpfen. Doppelte Mechanik driftet auseinander — der eine
Weg bekommt eine Korrektur, der andere nicht.

Was `metadata.json` dagegen wirklich beiträgt, kann die Pipeline nicht: es
überlebt den Neustart *pro Medium* und beantwortet die Frage „was fehlt an
diesem Import noch", die eine Jobhistorie nicht beantwortet.

**Folge einer Umkehr.** Fortschritt, Abbruch, Historie und Ergebnisanzeige
müssten für Media AI neu gebaut werden. Der Test
`test_media_ai_bridge.py::test_the_work_goes_through_the_existing_pipeline`
schlägt an, sobald ein Auftrag an `_submit_job` vorbeigeht.

**Umgesetzt in.** `src/services/media_ai/workspace.py` (`MediaJob`),
alle `media_ai_*`-Methoden der Bridge.

---

## ADR-003 — Whisper über die bestehende Schnittstelle, nicht neu gebaut

**Datum:** 2026-09-06 · **Status:** aktiv

**Entscheidung.** Die Transkription läuft über ein `TranscriptionBackend`-
Protokoll. Das Vorgabe-Backend `WhisperTranscription` ist ein dünner Adapter
über den bereits vorhandenen `src/services/subtitle.SubtitleGenerator`. Der
Import steht **in der Methode**, nicht im Kopf der Datei.

**Warum.** Whisper liegt seit Langem im Repository, ist an
`scripts/release_smoke.py` belegt (deutsche Faster-Whisper-SRT) und im
Vendor-Bundle als `whisper-base/` enthalten. Eine zweite Anbindung hätte
dieselbe Fähigkeit ein zweites Mal gepflegt.

Der Import in der Methode ist kein Stilfrage: `faster-whisper` zieht
Torch-Abhängigkeiten nach. Auf Modulebene bezahlt jeder Start diesen Aufwand —
auch der Nutzer, der nur herunterlädt und schneidet. Die gepackte EXE liegt
bereits bei rund 500 MB.

**Folge einer Umkehr.** Zwei Whisper-Anbindungen mit getrennten Modellpfaden
und Sprachoptionen. Zwei Tests halten die Entscheidung fest:
`test_the_default_transcription_backend_is_the_existing_whisper_service` und
`test_the_whisper_import_stays_out_of_module_scope`.

**Umgesetzt in.** `src/services/media_ai/processors.py`.

---

## ADR-004 — KI-Backends werden injiziert, nicht importiert

**Datum:** 2026-09-06 · **Status:** aktiv

**Entscheidung.** Je Fähigkeit ein `Protocol`, ein Vorgabe-Backend und ein
Prozessor, der nur das Protokoll kennt. Ein Backend kommt über den
Konstruktor. Wo noch keines existiert (Voice-Cloning, Vision), wirft der
Platzhalter `BackendNotConfigured` mit einem Satz, der nennt, wo ein Backend
angeschlossen wird.

**Warum.** Ohne diese Trennung landet jede Modellwahl in der Bridge und in der
Oberfläche. Ein Platzhalter, der still nichts tut oder `AttributeError` wirft,
ist für den Nutzer nicht von einem Defekt zu unterscheiden.

**Folge einer Umkehr.** Der Anschluss eines Modells würde Bridge und
Oberfläche anfassen statt nur den Konstruktoraufruf.

---

## ADR-005 — Zielnamen werden reserviert, nicht geprüft

**Datum:** 2026-09-06 · **Status:** aktiv (Nachtrag zur Umsetzung von P1-3)

**Entscheidung.** `src/core/output.py` ist die einzige Stelle, die Zielnamen
vergibt. Reserviert wird atomar (`O_CREAT | O_EXCL`), nicht über `exists()`
gefolgt von Schreiben. Reserviert wird zur **Ausführungszeit**, nicht beim
Einreihen.

**Warum.** `exists()`-dann-schreiben ist eine Wettlaufbedingung: zwei
Veröffentlichungen sehen denselben freien Namen, die zweite überschreibt die
erste klanglos. Der Downloader machte das immer richtig; alle anderen Wege
nicht — `Disc_D_Rip.mkv` traf die zweite Disc wie die erste, und ein zweites
DVD-Projekt mit dem Vorgabetitel löschte das Abbild des ersten.

Zur Ausführungszeit, weil ein in der Warteschlange abgebrochener Auftrag sonst
eine leere Datei hinterlässt.

**Folge.** Wer reserviert, muss überschreiben dürfen — am reservierten Namen
liegt die eigene leere Datei. Deshalb `overwrite=True` auf reservierten
Zielen, und **nur** dort. Ausnahme mit Absicht: `convert_file` reserviert
nicht; dort steuert der Nutzer das Überschreiben über eine Checkbox.

---

## ADR-006 — Ein Richtlinienblock ist kein Testfehlschlag

**Datum:** 2026-09-06 · **Status:** aktiv

**Entscheidung.** `tests/test_download_workflow.py` überspringt seinen
Echtlauf, wenn ein vendortes Werkzeug mit **WinError 4551**
(Anwendungssteuerungsrichtlinie) nicht startet. Der Grund steht im Skip-Text.
Jeder andere Fehlschlag — fehlendes Werkzeug, Absturz, falscher Exitcode —
bleibt ein Fehlschlag.

**Warum.** `vendor/ffmpeg.exe` ist unsigniert (SHA-256 `6834A793…`,
145 852 928 Bytes) und wird von Smart App Control blockiert; auch der direkte
Aufruf scheitert. Der Test brach damit ab, **bevor** RetroDisc-Code lief. Eine
dauerhaft rote Suite verdeckt die nächste echte Regression: niemand
unterscheidet dann noch „1 failed" von „2 failed".

**Was ausdrücklich nicht entschieden wurde.** Die Richtlinie wird nicht
umgangen, nicht abgeschaltet und nicht verändert. Der Block bleibt als
**Releaseblocker B1** in `docs/RELEASE_STATUS.md` sichtbar, und ein grüner
Lauf darf nicht als Beleg für die echte Medienstrecke gelesen werden.

**Folge einer Umkehr.** Ohne den Guard ist die Suite dauerhaft rot; mit einem
*weiter gefassten* Guard (etwa jedem `OSError`) würde ein echter Defekt
stillschweigend übersprungen.
