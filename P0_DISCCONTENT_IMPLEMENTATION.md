# P0 Block 1: DiscContent-Grundlage (2026-09-11)

Separater Auftrag, Teil des priorisierten LV-Nacharbeitungsplans (siehe
Soll/Ist-Abgleich in der Konversation). Ziel ausschließlich: das zentrale
Datenmodell für Disc-Inhalte, seine Anbindung an die vorhandene
Disc-Analyse, die Verknüpfung mit der vorhandenen Main-Movie-Erkennung,
Tests und eine Bridge-Methode. Ausdrücklich NICHT Teil dieses Blocks:
Blu-ray-Zielgrößen, Book-Type-UI, Preview Player, Smart Space Optimizer,
Quality Bar, Wizard/Expert Mode, größere UI-Überarbeitung, On-the-fly
Disc Copy. `src/ui/app.html` wurde nicht angefasst.

**Korrekturdurchlauf (2026-09-11, zweiter Teil dieses Blocks):** Die erste
Fassung dieses Dokuments und der zugehörige Code hatten einen fachlichen
Fehler, der in einer fachlichen Prüfung aufgedeckt wurde: `DiscAnalyzer`
setzte einen DVD-Titel mit einer Gruppe von `VTS_XX_Y.VOB`-Dateien gleich
und einen Blu-ray-Titel mit einer einzelnen `*.m2ts`-Datei. Beides ist
fachlich falsch - ein `VTS_XX_Y.VOB` ist kein eigenständiger DVD-Titel, und
eine `*.m2ts`-Datei ist kein eigenständiger Blu-ray-Titel. Dieser Abschnitt
und der komplette Analyseweg wurden entsprechend korrigiert (siehe
"Korrektur: echte logische Titel statt Dateien" weiter unten). Alle
folgenden Abschnitte beschreiben den korrigierten Stand.

## Ausgangszustand

Der vorangegangene LV-Soll/Ist-Abgleich hatte belegt:

- Kein `DiscContent`-Modell, keine Title-/Chapter-Dataclass irgendwo im Code.
- `get_disc_info()` (`src/core/disc.py`) liefert nur einen flachen
  Disc-Ebene-Dict (`present/readable/type/label/tracks/capacity_bytes/...`),
  auf keiner Plattform Titel-/Kapitel-/Spur-Daten.
- `src/services/main_movie.py::detect_main_movie()` ist fertig implementiert
  und getestet, hatte aber **null Aufrufer** im gesamten Repository.
- `src/services/ripper.py` (`DiscRipper._dvd_title_files`/`_bluray_streams`)
  enthält eine eigene, viel simplere, bereits produktiv genutzte
  Main-Movie-Heuristik ("größter VOB-Titelsatz nach Byte-Summe" bzw.
  "größte .m2ts-Datei"), komplett unabhängig von `main_movie.py`.

## Architekturentscheidung

1. **Neue, purpose-built Dataclasses statt Wiederverwendung der
   Datei-Stream-Modelle.** `src/models/media.py` (`AudioStream`,
   `VideoStream`, `SubtitleStream`) beschreibt Streams einer bereits
   vorliegenden Mediendatei nach dem ffprobe-Schema einer Datei. Sie haben
   keine Felder für Disc-spezifische Eigenschaften (`forced` bei
   Untertiteln, `is_main_movie` bei Titeln, Kapitel pro Titel). Ein
   Disc-Titel ist semantisch keine "Media File" - deshalb ein eigenes Modul
   `src/models/disc_content.py` mit eigenen Klassen, wie im Auftrag
   ausdrücklich verlangt ("Generische Datei-Streams dürfen nicht einfach
   als vollständiges Disc-Modell ausgegeben werden").
2. **Echte logische Titel statt Dateien** (siehe Korrekturabschnitt): DVD-
   Titel kommen aus der Titeltabelle in `VIDEO_TS.IFO`, Blu-ray-Titel aus
   den Playlist-Dateien in `BDMV/PLAYLIST/`. Dateien (`*.VOB`, `*.m2ts`)
   sind höchstens die Bausteine, die ein Titel referenziert - nie der Titel
   selbst.
3. **Innen getrennt, außen vereinheitlicht.** `DiscAnalyzer.analyze()`
   liefert für DVD und Blu-ray dieselbe `DiscContent`-Form; die
   Fallunterscheidung (VIDEO_TS/IFO vs. BDMV/MPLS) ist intern und dem
   Aufrufer nicht sichtbar.
4. **Fehlende Detailtiefe wird als `None` markiert, nicht simuliert.**
   Wo eine zuverlässige Zuordnung nicht möglich ist (siehe unten), bleibt
   das betroffene Feld `None` statt geschätzt oder gleichmäßig verteilt zu
   werden.

## Korrektur: echte logische Titel statt Dateien

### Das Problem (erste Fassung dieses Blocks)

- DVD: `VTS_*_[1-9].VOB`-Dateien wurden nach Titelsatz-Nummer gruppiert und
  **jede Gruppe wurde ein `DiscTitle`**. Das ignoriert, dass die Zuordnung
  Titel → Titelsatz allein aus der Titeltabelle in `VIDEO_TS.IFO` kommt -
  ein Titelsatz kann theoretisch mehrere Titel enthalten, und die reine
  Dateisystem-Gruppierung kann das nicht unterscheiden.
- Blu-ray: **jede `.m2ts`-Datei in `BDMV/STREAM/` wurde ein `DiscTitle`**.
  Das ist fachlich falsch: echte Blu-ray-Titel werden durch Playlists
  (`BDMV/PLAYLIST/*.mpls`) definiert, die eine geordnete Liste von Clips mit
  Ein-/Aussprungzeiten referenzieren. Ein Titel kann mehrere Clips
  umfassen, und derselbe Clip kann von mehreren Playlists referenziert
  werden (z. B. Hauptfilm-Playlist und eine kurze Vorschau-Playlist auf
  denselben physischen Clip). Die alte Logik hätte in diesem Fall entweder
  Titel verloren oder falsch gezählt.

### Die Korrektur

1. **DVD: Parser für den Title Search Pointer Table (TT_SRPT)**, neu in
   `src/services/dvd_ifo.py` (`parse_tt_srpt()`). Liest ausschließlich die
   Tabelle aus `VIDEO_TS.IFO`, die die echten logischen Titel auflistet:
   pro Titel Titelsatz-Nummer, VTS-interne Titelnummer, echte
   Kapitelanzahl (`nr_of_ptts` - "Parts of Title") und Winkelanzahl. Layout
   nach der öffentlich dokumentierten DVD-Video-IFO-Struktur (u. a.
   kompatibel zu libdvdreads `ifo_types.h`: `vmgi_mat_t`/`tt_srpt_t`/
   `title_info_t`). Der Tabellenzeiger liegt bei Byte-Offset `0xC4` in
   `VIDEO_TS.IFO` (Sektorzeiger, big-endian, ×2048 = Byte-Offset); danach
   ein 8-Byte-Kopf (`nr_of_srpts`, reserved, `last_byte`) gefolgt von
   12-Byte-Einträgen pro Titel.
2. **Blu-ray: Parser für Playlist-Dateien (MPLS)**, neu in
   `src/services/bluray_mpls.py` (`parse_mpls()`). Liest `PlayList()`
   (referenzierte Clips in Wiedergabereihenfolge, Gesamtlaufzeit aus der
   Summe der Ein-/Aussprungzeiten je `PlayItem`) und `PlayListMark()`
   (echte Kapitelmarken vom Typ `ENTRY_MARK`, umgerechnet auf die
   Playlist-Gesamtzeitachse). Layout nach der öffentlich dokumentierten
   BD-ROM-BDMV-Struktur (u. a. kompatibel zu libblurays `mpls_parse.c`).
3. **`DiscAnalyzer` nutzt beide Parser als alleinige Titel-Quelle.** Die
   alte Dateisystem-Gruppierung (`_dvd_titlesets`/`_bluray_streams`) wurde
   vollständig entfernt, nicht nur ergänzt.

### Wichtige Konsequenz: DVD ohne `VIDEO_TS.IFO` liefert jetzt einen Fehler

Vorher fiel die Analyse bei fehlender/fehlerhafter `VIDEO_TS.IFO`
stillschweigend auf die Dateigruppierung zurück. Das widerspricht dem
Grundsatz "keine erfundenen Daten": ohne die Titeltabelle ist nicht einmal
die Titel**anzahl** einer DVD verlässlich bekannt. `DiscAnalyzer._dvd_titles()`
wirft deshalb jetzt `DiscContentError`, wenn `VIDEO_TS.IFO` fehlt oder nicht
als gültige VMGI-Struktur geparst werden kann - eine ehrliche
Fehlermeldung statt einer stillschweigend falschen Titelliste.

Für Blu-ray ist die Lage etwas anders: eine BD-Struktur ist inhärent
mehrteilig (kein einzelnes "Master-Index"-File wie bei DVD), daher gilt ein
fehlender `BDMV/PLAYLIST`-Ordner als "keine Titel gefunden" (leere Liste),
nicht als harter Fehler.

### Was für gemeinsam genutzte Titelsätze/Clips gilt

- **DVD:** Teilen sich mehrere TT_SRPT-Titel denselben Titelsatz (VTS), ist
  ohne Zell-/PGC-Parsing (`VTS_PGCITI` in `VTS_XX_0.IFO`) nicht bekannt,
  welcher VOB-Abschnitt zu welchem Titel gehört. `duration_seconds` und
  `size_bytes` bleiben in diesem Fall bewusst `None` statt anteilig
  geschätzt zu werden. Die echte Kapitelanzahl (`nr_of_ptts`) ist davon
  unabhängig weiterhin bekannt und wird gesetzt.
- **Blu-ray:** Referenzieren mehrere Playlists denselben Clip, wird jeder
  Playlist unabhängig ihre eigene Laufzeit (aus den eigenen In-/Aussprung-
  zeiten) und - als dokumentierte Näherung - die volle Dateigröße des
  referenzierten Clips zugerechnet (keine Aufteilung nach dem tatsächlich
  genutzten Byte-Bereich, da das eine Byte-Offset-Zuordnung erfordern würde,
  die hier nicht implementiert ist). Beide Playlists bleiben als
  eigenständige, gültige Titel erhalten - keiner wird verworfen oder
  fälschlich zusammengeführt.

## Neue Modelle (`src/models/disc_content.py`)

- `DiscContentError` - Exception für nicht analysierbare Discs.
- `DiscChapter(index, start_seconds=None, duration_seconds=None)` -
  `start_seconds`/`duration_seconds` sind `None`, wenn nur die Existenz/
  Anzahl der Kapitel bekannt ist, ihre Zeitposition aber nicht.
- `DiscVideoInfo(codec, width, height, fps)`
- `DiscAudioTrack(index, codec, language, channels, bitrate, default)`
- `DiscSubtitleTrack(index, language, format, forced, default)`
- `DiscTitle(index, name, duration_seconds=None, size_bytes=None, chapters,
  video, audio_tracks, subtitle_tracks, is_main_movie, main_movie_confidence)` -
  `duration_seconds`/`size_bytes` sind `None`, wenn sie ohne verlässliche
  Struktur-Zuordnung nicht eindeutig ermittelt werden können.
- `DiscContent(disc_type, label, device, capacity_bytes, available_bytes,
  titles)` mit `main_movie`-Property (erster Titel mit `is_main_movie=True`)

Alle Klassen haben `to_dict()` für eine JSON-sichere, verschachtelte
Serialisierung. `disc_type` nutzt weiterhin das vorhandene `DiscType`-Enum
aus `src/models/media.py` (DVD/BLURAY/CD) - eine reine Enum-Wiederverwendung,
kein Übergriff auf die Datei-Stream-Modelle.

## Neue Parser-Module

- **`src/services/dvd_ifo.py`** - `IfoParseError`, `DvdTitleEntry`,
  `parse_tt_srpt(data: bytes) -> list[DvdTitleEntry]`. Reine Byte-Parsing-
  Funktion, keine Abhängigkeit zu `DiscAnalyzer` oder den Disc-Modellen -
  eigenständig testbar und wiederverwendbar (die geforderte "saubere
  Parser-/Provider-Abstraktion").
- **`src/services/bluray_mpls.py`** - `MplsParseError`, `MplsPlaylist`,
  `parse_mpls(data: bytes) -> MplsPlaylist`. Ebenfalls eigenständig, ohne
  Abhängigkeit zu den Disc-Modellen.

## Neuer Service (`src/services/disc_analyzer.py`)

`class DiscAnalyzer(disc_tools: DiscTools, probe: MediaProbeService)`

- `analyze(device) -> DiscContent` (async): Einstiegspunkt.
- `_dvd_titles(video_ts)` / `_dvd_title_from_entry(entry, video_ts, shared_vts)`:
  TT_SRPT-Einträge → echte `DiscTitle`-Objekte, VOB-Dateien werden nur noch
  zur Laufzeit-/Größen-/Stream-Ermittlung eines bereits durch die IFO
  bestätigten Titels herangezogen.
- `_bluray_titles(bdmv)` / `_bluray_title_from_playlist(index, playlist, stream_dir)`:
  MPLS-Playlists → echte `DiscTitle`-Objekte, `.m2ts`-Dateien werden nur
  noch zur Größen-/Stream-Ermittlung eines bereits durch die Playlist
  bestätigten Titels herangezogen.
- `_apply_main_movie()`: Brücke zu `main_movie.detect_main_movie()`
  (unverändert), jetzt aber mit echten Titeln als Eingabe statt einzelner
  Dateien.

## Datenfluss

```
UI (später)
   -> RetroDiscApi.get_disc_content(device)
   -> RetroDiscBridge.get_disc_content(device)
        -> self._async(self.disc_analyzer.analyze(device)).result(timeout=60)
             -> DiscTools.get_disc_info(device)              # Disc-Ebene, unveraendert
             DVD:
             -> VIDEO_TS.IFO lesen -> parse_tt_srpt()         # echte Titel/Kapitelanzahl
             -> je Titel: zugehoerige VTS_XX_*.VOB (Groesse/Laufzeit/Streams via ffprobe)
             Blu-ray:
             -> BDMV/PLAYLIST/*.mpls lesen -> parse_mpls() je Datei  # echte Titel/Clips/Kapitel
             -> je Playlist: referenzierte BDMV/STREAM/*.m2ts (Groesse/Streams via ffprobe)
             -> main_movie.detect_main_movie(titel_liste)      # unveraendert, jetzt auf echten Titeln
        -> DiscContent.to_dict()
   -> json.dumps(...)  bzw.  json.dumps({"error": ...})
```

## Analyseweg DVD

1. `get_disc_info()` liefert `present/label/capacity_bytes/...` (unverändert).
2. Ist `VIDEO_TS/VIDEO_TS.IFO` vorhanden und lesbar: `parse_tt_srpt()`
   liefert die echte Titelliste (Titelsatz, Titelnummer, Kapitelanzahl,
   Winkelanzahl). Fehlt die Datei oder ist sie nicht als gültige VMGI-
   Struktur erkennbar, wird `DiscContentError` geworfen (siehe oben).
3. Pro Titel: gehört der Titelsatz eindeutig zu genau diesem einen Titel,
   werden Größe (Summe der VOB-Dateigrößen) und Laufzeit (Summe der
   ffprobe-Laufzeiten aller VOBs im Titelsatz) zugerechnet; Video-/Audio-/
   Untertitel-Layout wird vom ersten VOB mit erkennbaren Streams
   übernommen. Teilen sich mehrere Titel einen Titelsatz, bleiben Größe und
   Laufzeit `None` (siehe oben).
4. Kapitel: `nr_of_ptts` echte Kapitel-Objekte, jeweils mit `start_seconds=
   None`/`duration_seconds=None` (Zeitposition ohne VTS_PGCITI-Parsing
   nicht bekannt - siehe "Bekannte Einschränkungen").

## Analyseweg Blu-ray

1. `get_disc_info()` wie bei DVD.
2. Ist `BDMV/PLAYLIST/` vorhanden: jede lesbare `*.mpls`-Datei wird über
   `parse_mpls()` zu einer `MplsPlaylist` (referenzierte Clip-IDs in
   Wiedergabereihenfolge, Gesamtlaufzeit, echte Kapitel-Zeitstempel aus
   `ENTRY_MARK`-Einträgen) und daraus zu einem `DiscTitle`. Nicht lesbare
   Playlist-Dateien werden übersprungen (protokolliert), nicht die ganze
   Disc zum Fehler gemacht. Fehlt der `PLAYLIST`-Ordner ganz, ist das
   Ergebnis eine leere Titelliste (kein Fehler).
3. Pro Titel: Größe = Summe der Dateigrößen der (einmalig gezählten)
   referenzierten Clips; Video-/Audio-/Untertitel-Layout kommt aus einem
   ffprobe-Aufruf auf den ersten referenzierten Clip mit erkennbaren
   Streams.
4. Kapitel: echte `ENTRY_MARK`-Zeitstempel aus `PlayListMark()`, umgerechnet
   auf die Playlist-Gesamtzeitachse. Keine Marken vorhanden → leere
   Kapitelliste, kein Platzhalter.

Ist weder `VIDEO_TS/` noch `BDMV/` vorhanden, aber ein Medium `present`,
gilt die Disc als Audio-/Datenträger: `disc_type=CD`, `titles=[]` - kein
Fehler, sondern ein gültiges, leeres Ergebnis (unverändert gegenüber der
ersten Fassung).

## Main-Movie-Verknüpfung

`DiscAnalyzer._apply_main_movie()` baut aus den ermittelten (jetzt echten)
Titeln `[{"index", "duration", "chapters", "size"}, ...]` und ruft die
**unveränderte** `detect_main_movie()` aus `main_movie.py` auf. Da die
Heuristik `None`-Werte für `duration`/`size` bereits wie `0` behandelt
(`_num()`: `float(value or 0)`), werden Titel mit unbekannter Laufzeit/
Größe (geteilter DVD-Titelsatz) automatisch benachteiligt statt fälschlich
bevorzugt - keine Änderung an `main_movie.py` nötig. Bei Blu-ray wird nicht
mehr der größte einzelne `.m2ts`-Stream verglichen, sondern die längste/
größte **Playlist** (siehe Regressionstests 3 und 4). Der zurückgegebene
Kandidat wird per Index auf `DiscTitle.is_main_movie=True` gesetzt, dessen
Konfidenz zusätzlich in `main_movie_confidence` gespiegelt.

## Bridge

Unverändert gegenüber der ersten Fassung: `RetroDiscBridge.get_disc_content(device)`,
Proxy `RetroDiscApi.get_disc_content`, `self.disc_analyzer`-Konstruktion in
`__init__`. Keine Änderungen in diesem Korrekturdurchlauf nötig, da sich nur
die interne Titel-Ermittlung in `DiscAnalyzer`, nicht die Schnittstelle,
geändert hat. Weiterhin keine UI-Anbindung.

## Tests

### Parser-Unit-Tests (neu)

- **`tests/test_dvd_ifo.py`** (7 Tests): ein Titel/ein Titelsatz, mehrere
  Titel über verschiedene Titelsätze, mehrere Titel im selben Titelsatz
  (unterschieden durch `vts_title_number`), null Titel, falsches Magic-
  Signatur, abgeschnittene Datei, TT_SRPT-Zeiger außerhalb der Datei.
- **`tests/test_bluray_mpls.py`** (8 Tests): einzelner Clip, mehrere Clips
  in Wiedergabereihenfolge (inkl. `IN_time != 0`), derselbe Clip zweimal in
  einer Playlist, `ENTRY_MARK`-Zeitstempel über mehrere Clips hinweg korrekt
  auf die Playlist-Gesamtzeitachse umgerechnet, Nicht-`ENTRY_MARK`-Marken
  werden ignoriert, keine Marken-Sektion → leere Kapitelliste, falsches
  Magic, unbekannte Version.

### Modell-/Analyzer-/Bridge-Tests (`tests/test_disc_content.py`, 25 Tests)

Reine Modell-Tests (leere Struktur, ein/mehrere Titel, Kapitel, mehrere
Audio-/Untertitelspuren, Main-Movie-Markierung, JSON-Serialisierung) sind
gegenüber der ersten Fassung inhaltlich unverändert (sie konstruieren
Dataclasses direkt und sind von der Titel-Ermittlung unabhängig).

Die Analyzer-Tests wurden vollständig durch IFO-/MPLS-basierte Fixtures
ersetzt bzw. um die geforderten Regressionstests ergänzt:

| Geforderter Regressionstest | Test(s) |
|---|---|
| 1. Blu-ray-Playlist mit einem M2TS-Clip | `test_analyze_bluray_regression_1_playlist_with_one_clip` |
| 2. Blu-ray-Playlist mit mehreren M2TS-Clips | `test_analyze_bluray_regression_2_playlist_with_multiple_clips` |
| 3. mehrere Blu-ray-Playlists | `test_analyze_bluray_regression_3_multiple_playlists` |
| 4. derselbe M2TS-Clip von mehreren Playlists referenziert | `test_analyze_bluray_regression_4_same_clip_referenced_by_multiple_playlists` |
| 5. DVD mit mehreren VOB-Dateien = ein logischer Titel | `test_analyze_dvd_regression_5_multiple_vobs_form_one_logical_title` |
| 6. unbekannte Kapitelinfo wird nicht erfunden | `test_analyze_bluray_regression_6_no_marks_means_no_fabricated_chapters` (Blu-ray, leere Liste) und `test_analyze_dvd_regression_5_...` (DVD, `start_seconds is None` trotz bekannter Kapitelanzahl) |

Zusätzlich (nicht explizit gefordert, aber zur Absicherung der Korrektur
notwendig): `test_analyze_dvd_multiple_titles_across_different_vts`,
`test_analyze_dvd_titles_sharing_one_vts_have_unknown_duration_and_size`,
`test_analyze_dvd_without_video_ts_ifo_raises_instead_of_guessing`,
`test_analyze_bluray_playlist_marks_become_real_chapters`,
`test_analyze_bluray_without_playlist_folder_returns_no_titles`.

Alle Bridge-Tests (`test_bridge_get_disc_content_*`) sind unverändert -
sie monkeypatchen `disc_analyzer.analyze` direkt mit einem fertigen
`DiscContent`-Objekt und prüfen damit ausschließlich die Bridge-Schicht,
unabhängig von der internen Titel-Ermittlung.

## Tests vorher / nachher

- Vor diesem Korrekturdurchlauf (erste Fassung von P0 Block 1):
  821 passed, 19 skipped, 1 failed (bekannt, unabhängig, siehe
  `STABILITY_QUEUE_INIT.md`).
- Nach der Korrektur: **844 passed**, 19 skipped, **1 failed** (derselbe,
  unveränderte, bereits dokumentierte Fehler). +23 Tests netto (25 in
  `test_disc_content.py`, davon einige neu gegenüber vorher entfernten
  Alt-Tests, plus 7 in `test_dvd_ifo.py`, plus 8 in `test_bluray_mpls.py`).
- Zusätzliche Gates: `compileall` (grün), `scripts/verify_ui_bridge.py`
  (PASS, 0 Findings - unverändert, da Bridge-Schnittstelle nicht angefasst),
  `git diff --check` (grün).

## Bekannte Einschränkungen

- **DVD-Kapitel: Anzahl echt, Zeitposition unbekannt.** `nr_of_ptts` aus
  TT_SRPT ist eine echte, direkt aus der IFO gelesene Kapitelanzahl.
  Einzelne Kapitel-Startzeiten liegen in der VTS-eigenen `VTS_PGCITI`-
  Zell-Tabelle (`VTS_XX_0.IFO`), die hier NICHT geparst wird - das wäre ein
  eigenständiger, deutlich größerer Arbeitsschritt. `start_seconds`/
  `duration_seconds` bleiben deshalb bewusst `None`, statt gleichmäßig über
  die Titellänge verteilt zu werden.
- **DVD-Titel, die sich einen Titelsatz teilen, haben unbekannte Laufzeit/
  Größe.** Ohne Zell-Parsing ist nicht bekannt, welcher VOB-Abschnitt zu
  welchem Titel gehört (siehe oben). In der Praxis (Einzelfilm-DVDs, der
  RetroDisc-Zielfall) ist dieser Fall selten - die meisten Discs haben genau
  einen Titel pro Titelsatz.
- **Sprachkennzeichnung bei DVD-Spuren meist `None`.** DVD-Sprachinfo pro
  Audio-/Untertitelspur liegt in der `VTSI_MAT`-Attributtabelle in der IFO,
  nicht im rohen VOB-Elementarstrom; ffprobe kann sie auf VOB-Ebene in der
  Regel nicht liefern.
- **Blu-ray: STN_table nicht geparst.** Die Playlist-eigene Stream-Nummern-
  Tabelle (die u. a. echte Sprachcodes für Audio-/Untertitelspuren einer
  Playlist enthält) wird nicht gelesen. Audio-/Untertitel-Sprache kommt
  stattdessen aus ffprobe auf den referenzierten `.m2ts`-Clip - dort
  häufiger vorhanden als bei DVD, aber nicht garantiert.
- **Blu-ray: geteilte Clips bekommen die volle Dateigröße je referenzierender
  Playlist**, nicht anteilig nach tatsächlich genutztem Byte-Bereich (siehe
  Korrekturabschnitt oben) - eine dokumentierte Näherung, kein exakter Wert.
- **`DiscRipper` (Rip-Feature) nutzt weiterhin seine eigene, einfachere
  Main-Movie-Heuristik** ("größter Titelsatz/Stream nach Byte-Summe") und
  wurde in diesem Block bewusst nicht auf `DiscAnalyzer`/`DiscContent`
  umgestellt - das war nicht Teil des Auftrags und hätte das bestehende,
  funktionierende Rip-Verhalten verändern können.
- **Getestet nur mit handgebauten, strukturkonformen Byte-Fixtures**, nicht
  mit einer echten eingelegten DVD/Blu-ray oder einem echten Disc-Abbild
  (kein optisches Laufwerk in dieser Umgebung verfügbar). Die IFO-/MPLS-
  Byte-Layouts sind nach öffentlich dokumentierten, weit verbreiteten
  Strukturen implementiert (siehe Modul-Docstrings für konkrete
  Referenzen), aber in dieser Umgebung NICHT gegen echte Hardware oder ein
  echtes Disc-Abbild verifizierbar - wie bei allen bisherigen Disc-
  Fähigkeiten dieses Projekts bleibt der physische Hardwarepfad ungetestet,
  bis echte Medien verfügbar sind.
- **Keine UI-Anbindung.** `get_disc_content` ist über die Bridge erreichbar,
  aber von keiner Stelle in `app.html` aufgerufen - wie beauftragt.

## Nicht verändert

`src/ui/app.html`, `src/services/ripper.py`, `src/core/disc.py`,
`src/services/dvd_workflow.py`, `src/services/main_movie.py`
(unverändert wiederverwendet, keine Änderung), `retrodisc_launcher.py`
(unverändert gegenüber der ersten Fassung dieses Blocks - keine Bridge-
Änderung in diesem Korrekturdurchlauf nötig). Book-Type-, Blu-ray-
Zielgrößen-, Preview-Player-, Quality-Bar-, Wizard-/Expert-Mode- und
On-the-fly-Themen unangetastet. Kein Commit, kein Push.
