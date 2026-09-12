# P0 Block 2: Kapazitätsplanung (2026-09-11)

Separater Auftrag, direkt auf P0 Block 1 (DiscContent, echte DVD-/Blu-ray-
Titelerkennung) aufbauend. Ziel ausschließlich: eine zentrale, medien-
unabhängige Kapazitätsplanung VOR jeder Kodierung bzw. jedem Authoring-
Vorgang. Ausdrücklich NICHT Teil dieses Blocks: Preview Player, Book-Type-UI,
Wizard Mode, Expert Mode, Quality Bar, ein vollständiger automatischer Smart
Space Optimizer, On-the-fly Disc Copy, größere UI-Überarbeitung. `src/ui/app.html`
wurde nicht angefasst.

## Architektur

Zwei neue, unabhängig testbare Bausteine plus eine dünne Bridge-Anbindung:

1. **`src/config/target_media.py`** - reine Datendefinition. Eine einzige
   Quelle für alle Zielgrößen (DVD-5/9, BDMV-auf-DVD-5/9, BD-25/50/100/128,
   Custom) statt über mehrere Dateien verstreuter Magic Numbers.
   **Korrektur (2026-09-11, siehe eigener Abschnitt unten):** die vormals
   als "BD-5"/"BD-9" bezeichneten Profile heißen jetzt eindeutig
   `bdmv_on_dvd5`/`bdmv_on_dvd9`; echte physische Blu-ray-Zielmedien
   (`bd25`/`bd50`/`bd100`/`bd128`) sind jetzt vollständig vertreten.
2. **`src/services/capacity_planner.py`** - `CapacityPlanner.plan()`, eine
   zustandslose, reine Berechnung. Nimmt `DiscTitle`-Objekte aus dem in
   P0 Block 1 eingeführten `DiscContent`-Modell entgegen - **keine neue
   parallele Titel-/Disc-Datenstruktur**.
3. **`RetroDiscBridge.plan_capacity(...)`** (`retrodisc_launcher.py`) - liest
   die Disc über den bereits vorhandenen `DiscAnalyzer` (P0 Block 1), wählt
   die gewünschten Titel/Spuren aus und ruft den `CapacityPlanner`. Reine
   Bridge-Verdrahtung, keine eigene Berechnungslogik.

Der Planer selbst hat keine Abhängigkeit zu Laufwerk, Dateisystem oder
Bridge - er ist mit handgebauten `DiscTitle`-Objekten vollständig isoliert
testbar (siehe Tests unten).

## Zielmedien und Kapazitäten

| ID | Anzeigename | Authoring-Format | Physisches BD-Medium? | Nominelle Kapazität | Nutzbare Kapazität |
|---|---|---|---|---|---|
| `dvd5` | DVD-5 (Single Layer, 4,7 GB) | DVD_VIDEO | - | 4.700.000.000 Bytes | 4.606.000.000 Bytes |
| `dvd9` | DVD-9 (Dual Layer, 8,5 GB) | DVD_VIDEO | - | 8.500.000.000 Bytes | 8.330.000.000 Bytes |
| `bdmv_on_dvd5` | BDMV auf DVD-5 (kein physisches Blu-ray-Medium) | BDMV | nein | 4.700.000.000 Bytes | 4.606.000.000 Bytes |
| `bdmv_on_dvd9` | BDMV auf DVD-9 (kein physisches Blu-ray-Medium) | BDMV | nein | 8.500.000.000 Bytes | 8.330.000.000 Bytes |
| `bd25` | BD-25 (Single Layer, 25 GB) | BDMV | ja | 25.000.000.000 Bytes | 24.500.000.000 Bytes |
| `bd50` | BD-50 (Dual Layer, 50 GB) | BDMV | ja | 50.000.000.000 Bytes | 49.000.000.000 Bytes |
| `bd100` | BD-100 / BDXL (Triple Layer, 100 GB) | BDMV | ja (BDXL) | 100.000.000.000 Bytes | 98.000.000.000 Bytes |
| `bd128` | BD-128 / BDXL (Quad Layer, 128 GB) | BDMV | ja (BDXL) | 128.000.000.000 Bytes | 125.440.000.000 Bytes |
| `custom` | Benutzerdefiniert | vom Aufrufer angegeben | vom Aufrufer angegeben | vom Aufrufer angegeben | nominell × 0,98 |

### Korrektur (2026-09-11): BD-5/BD-9 waren fachlich irreführend

Die ursprüngliche Fassung dieses Blocks führte "BD-5"/"BD-9" als eigene
Zielmedien - das war fachlich falsch: es gibt keinen physischen 4,7-GB- oder
8,5-GB-Blu-ray-Rohling. Korrigiert: die IDs heißen jetzt eindeutig
`bdmv_on_dvd5`/`bdmv_on_dvd9`, mit einem Anzeigenamen, der explizit "kein
physisches Blu-ray-Medium" nennt. Echte physische Blu-ray-Zielmedien sind
jetzt vollständig als `bd25`/`bd50`/`bd100`/`bd128` vertreten - inklusive
BDXL (100/128 GB).

**Disc-Struktur ≠ physisches Zielmedium:** `bdmv_on_dvd5`/`bdmv_on_dvd9`
beschreiben eine **BDMV-Struktur (Blu-ray-Authoring)**, die auf einem
gewöhnlichen **DVD-5- bzw. DVD-9-Rohling** gebrannt wird - damit auch
günstige DVD-Rohlinge auf einem Blu-ray-Player abspielbar sind. Deshalb
tragen sie exakt dieselbe Kapazität wie DVD-5/DVD-9, aber
`authoring_format=AuthoringFormat.BDMV` statt `DVD_VIDEO` und
`is_physical_bluray=False`. `AuthoringFormat` (Disc-*Struktur*) und
Kapazität (physisches Speichervermögen) sind im Modell zwei unabhängige
Achsen - genau wie gefordert wird "Blu-ray" hier nicht unnötig mit "große
Kapazität" gleichgesetzt.

**BDXL (BD-100/BD-128) behauptet nie Unterstützung ohne Beleg:** beide
Einträge tragen `requires_bdxl=True`. Die neue Funktion
`bdxl_capability_warning(medium, drive_capabilities)` prüft gegen die
bereits vorhandene `DriveCapabilities.bd_xl`-Erkennung
(`src/services/drive_inspector.py`, liest reale `dvd+rw-mediainfo`-Daten):
ohne bekannte Laufwerksdaten nur eine Warnung ("nicht bekannt"), bei
bestätigt fehlender BDXL-Fähigkeit ein `CapacityPlan.error`. `CapacityPlanner.plan()`
akzeptiert dafür einen neuen optionalen Parameter `drive_capabilities`.

### Dezimale Herstellerangabe vs. binäre Größe

`nominal_capacity_bytes` ist die **dezimale (SI, 10⁹) Herstellerangabe**, wie
sie auf der Verpackung steht - 4,7 GB = 4.700.000.000 Bytes bei DVD-5. Das
ist NICHT dasselbe wie 4,7 GiB (2³⁰-Einheiten): ein Werkzeug, das dieselbe
Byte-Zahl fälschlich durch 1024³ statt 1000³ teilt, zeigt für dieselbe Disc
"4,38 GB" an - ein in Consumer-Software verbreiteter Verwechslungsfehler.
Dieses Modul vermeidet ihn, indem sämtliche Kapazitäten ausschließlich als
ganze Bytes geführt werden; jede GB/GiB-Anzeige mit Rundung ist bewusst
Sache einer späteren UI-Schicht, nicht dieses Moduls.

### Nutzbare Kapazität und Sicherheitsmarge

`usable_capacity_bytes = nominal_capacity_bytes × 0,98` (einheitlich 2 %
Abzug für alle Medien). **Das ist eine bewusst gewählte, klar benannte
Ingenieurs-Sicherheitsmarge für Dateisystem-/Formatierungs-Overhead
(UDF-Bridge-Format bei DVD, UDF 2.50 bei Blu-ray) - KEINE aus Sektortabellen
exakt gemessene Größe.** Eine präzisere, sektorgenaue Herleitung (z. B. über
die tatsächliche UDF-Metadatengröße für eine konkrete Dateianzahl) wäre
möglich, würde aber eine Genauigkeit vortäuschen, die für eine Planung VOR
dem Encode weder nötig noch verlässlich ist - siehe "Bekannte
Einschränkungen".

## Verwendete Einheiten

Ausschließlich **Bytes** (ganzzahlig) für alle Kapazitäts-/Größenangaben,
**Sekunden** (Gleitkommazahl) für Laufzeiten, **Bit pro Sekunde** für
Bitraten (konsistent mit `DiscAudioTrack.bitrate` aus P0 Block 1, das
ffprobes `bit_rate`-Feld in bit/s übernimmt). Keine implizite Umrechnung in
MB/GB oder kbit/s innerhalb von `CapacityPlanner`/`TargetMedium` - das bleibt
Sache der aufrufenden Schicht (Bridge/UI).

## Overhead-Modell

Zwei bewusst getrennte Overhead-Konzepte, die nicht miteinander vermischt
werden:

1. **Medien-Overhead** (`TargetMedium.usable_capacity_bytes` vs.
   `nominal_capacity_bytes`, siehe oben) - ein pauschaler, medienweiter
   Dateisystem-/Formatierungs-Abzug, unabhängig vom konkreten Projekt.
2. **Projekt-Overhead** (`CapacityPlanner.AUTHORING_OVERHEAD_BY_FORMAT`) -
   eine grobe, konservative Reserve für die **Navigationsstruktur dieses
   konkreten Authoring-Vorgangs**:
   - `DVD_VIDEO`: 10.000.000 Bytes (VIDEO_TS-Navigationsdateien, IFO/BUP)
   - `BDMV`: 5.000.000 Bytes (`index.bdmv`/`MovieObject.bdmv`/`PLAYLIST`/`CLIPINF`)

   Beides sind **grobe, dokumentierte Schätzwerte, keine Messungen** - echte
   Navigationsstrukturgrößen hängen von Titel-/Kapitelanzahl und ggf. Menüs
   ab, die in diesem Block nicht modelliert werden (kein DVD-Menü-Authoring,
   siehe LV-Gap-Analyse).

Zusätzlich: `TargetMedium.authoring_overhead_bytes` (optionales Feld, für
alle Standardmedien aktuell `0`) - ein Erweiterungspunkt für eine künftige,
medienspezifische Zusatzreserve, ohne das Modell erneut ändern zu müssen.

## Audio-/Untertitel-Schätzwerte

Wenn eine ausgewählte Audiospur keine gemessene Bitrate trägt
(`DiscAudioTrack.bitrate is None` - z. B. bei DVD-Spuren, siehe P0 Block 1,
"Bekannte Einschränkungen"), wird eine dokumentierte Standardannahme
verwendet, **niemals stillschweigend**:

- Stereo (≤ 2 Kanäle): 192.000 bit/s (typischer AC-3-2.0-Wert)
- Mehrkanal (> 2 Kanäle): 448.000 bit/s (typischer AC-3-5.1-Wert)

Jede Verwendung einer solchen Standardannahme erzeugt einen Eintrag in
`CapacityPlan.warnings`, der explizit "Schätzung, keine Messung" nennt und
die betroffene Spur benennt.

Untertitel-Overhead: 5.000.000 Bytes pro ausgewählter Untertitelspur, eine
grobe, konservative Reserve (Bitmap-Untertitel für einen Spielfilm können
mehrere MB erreichen).

## Berechnungsformeln

```
verfügbare Zielkapazität        = TargetMedium.usable_capacity_bytes
minus Authoring-/Container-Overhead (Navigationsstruktur, siehe oben)
= verfügbare Nutzdatenkapazität  (CapacityPlan.available_payload_bytes)

verfügbare Nutzdatenkapazität
minus Audio-Budget                (Summe je Spur: Bitrate × Gesamtdauer ÷ 8)
minus sonstiger Overhead          (Untertitel-Reserve, siehe oben)
= verfügbares Video-Budget        (CapacityPlan.video_budget_bytes)

verfügbares Video-Budget × 8 ÷ Gesamtdauer(s)
= maximale durchschnittliche Video-Bitrate (bit/s)
  (CapacityPlan.max_average_video_bitrate_bps)
```

„Passt ohne Größenreduktion" vergleicht die **geschätzte Quellgröße** (Summe
der bereits mit Video+Audio+Untertitel gemultiplexten `DiscTitle.size_bytes`)
gegen die **verfügbare Nutzdatenkapazität** (vor Abzug des neu geplanten
Audio-/Untertitel-Budgets) - nicht gegen das Video-Budget. Grund: die
Quellgröße enthält bereits die aktuelle Tonspur der Disc, das neu berechnete
Audio-Budget bildet dagegen die für dieses Projekt *ausgewählte* (ggf.
andere) Tonkonfiguration ab. Beide Zahlen gegeneinander zu vergleichen wäre
ein Kategorienfehler.

## Randfälle

| Randfall | Verhalten |
|---|---|
| Laufzeit 0 | `max_average_video_bitrate_bps = None`, Warnung, keine Division durch 0 |
| Unbekannte Dateigröße (mind. 1 Titel) | `estimated_source_size_bytes = None`, `fits_without_reduction`/`transcoding_required = None`, Warnung - **kein Rückfall auf eine Teilsumme**, da eine unvollständige Summe fälschlich als vollständig gemessen erscheinen würde |
| Unbekannte Titel-Laufzeit (mind. 1 Titel) | Gesamtdauer = **Teilsumme** der bekannten Titel + Warnung - bewusst anders als bei der Größe, weil die Bitrate-Formel ohne eine konkrete Zahl gar nicht rechnen könnte; die Warnung macht die Lücke transparent |
| Unbekannte Audio-Bitrate | dokumentierte Standardannahme + Warnung (siehe oben) |
| Mehrere Titel | Laufzeit/Größe werden summiert (mit obigen Ausnahmen) |
| Mehrere Audiospuren | Budget wird je Spur berechnet und summiert |
| Mehrere Untertitel | Overhead skaliert linear mit der Spuranzahl |
| Zielmedium kleiner als Mindestbedarf | `error` gesetzt (zwei Stufen: Overhead allein bereits zu groß, oder Overhead+Audio+Untertitel bereits zu groß) |
| Custom-Zielgröße ungültig (≤ 0 oder fehlend) | `error` gesetzt, **keine Exception** |
| Custom ohne Authoring-Format | `error` gesetzt, **keine Exception** |
| Unbekannte Ziel-ID | `error` gesetzt, **keine Exception** (intern via `ValueError` aus `target_media.py`, von `CapacityPlanner.plan()` abgefangen) |
| Quellmaterial passt bereits vollständig | `fits_without_reduction=True`, `transcoding_required=False`, kein Fehler |
| Sehr kurze/sehr lange Inhalte | keine Sonderbehandlung nötig - reine Arithmetik, durch Tests mit 0 s und 10 h abgesichert |

Grundsatz durchgängig: **keine erfundenen Werte als gemessene Werte
ausgegeben.** Jede Ersetzung eines fehlenden Werts durch eine Annahme
erzeugt eine Warnung, die die Annahme explizit als Schätzung benennt.

## Datenfluss

```
UI (später)
   -> RetroDiscApi.plan_capacity(device, target_medium_id, ...)
   -> RetroDiscBridge.plan_capacity(...)
        -> self._async(self.disc_analyzer.analyze(device)).result(timeout=60)   # P0 Block 1, unverändert
        -> Titel-/Spur-Auswahl anhand der übergebenen Indizes filtern
        -> self.capacity_planner.plan(titles=..., target_medium_id=..., ...)
   -> CapacityPlan.to_dict() -> json.dumps(...)  bzw.  json.dumps({"error": ...})
```

Der `CapacityPlanner` selbst hat keinerlei Kenntnis von Geräten, Dateisystem
oder der Bridge - er bekommt fertige `DiscTitle`/`DiscAudioTrack`/
`DiscSubtitleTrack`-Objekte übergeben und rechnet rein synchron.

## Bridge-Methode

```python
def plan_capacity(self, device: str, target_medium_id: str,
                  selected_title_indices_json: str = "[]",
                  selected_audio_indices_json: str = "[]",
                  selected_subtitle_indices_json: str = "[]",
                  custom_target_bytes: Optional[int] = None,
                  custom_authoring_format: str = "") -> str: ...
```

Proxy: `RetroDiscApi.plan_capacity(self, *args)`. `self.capacity_planner`
wird in `RetroDiscBridge.__init__` direkt neben `self.disc_analyzer`
konstruiert (`CapacityPlanner()` - zustandslos, keine Konstruktionskosten,
keine Thread-Affinität wie beim `conversion_queue`-Fall aus dem
Stabilitätsblock).

Leere Auswahllisten (`"[]"`, Default) bedeuten "alle Titel/Spuren der Disc" -
eine bewusste, dokumentierte Vereinfachung, solange es noch keine eigene
Auswahl-UI gibt. `scripts/verify_ui_bridge.py` bestätigt PASS (0 Findings);
da `app.html` diese Methode noch nicht aufruft, ist das erwartungsgemäß -
wie bereits bei `get_disc_content` in P0 Block 1.

## Tests

### `tests/test_target_media.py` (Stand nach Korrektur 2026-09-11: 18 Tests)

Registrierung aller acht Zielmedien, DVD-Video- vs. BDMV-Zuordnung,
`bdmv_on_dvd5`/`bdmv_on_dvd9`-Kapazitätsgleichheit mit DVD-5/DVD-9 bei
`is_physical_bluray=False`, `bd100`/`bd128` mit `is_physical_bluray=True`
und `requires_bdxl=True`, eindeutige (nicht mit "BD-5"/"BD-9" verwechselbare)
Anzeigenamen, alte `bd5`/`bd9`-IDs lösen bewusst nicht mehr auf, dezimale
Nennkapazitäten, nutzbare < nominelle Kapazität, BD-50 = 2× BD-25,
BD-128 > BD-100 > BD-50, unbekannte ID wirft `ValueError`, Custom akzeptiert
Größe+Format, Custom lehnt nicht-positive Größe ab, BDXL-Warnung/-Fehler
je nach `DriveCapabilities`.

### `tests/test_capacity_planner.py` (Stand nach Korrektur 2026-09-11: 31 Tests)

| Geforderter Testfall | Test(s) |
|---|---|
| DVD-5, DVD-9, BDMV auf DVD-5/9, BD-25, BD-50, BD-100, BD-128 | `test_plan_resolves_every_required_target_medium` (parametrisiert) |
| Custom | `test_plan_accepts_explicit_custom_target_size` |
| Passt ohne Transcoding | `test_content_fits_without_transcoding_on_large_enough_medium` |
| Passt nur nach Größenreduktion | `test_content_requires_transcoding_on_too_small_medium` |
| Mehrere Audiospuren | `test_multiple_audio_tracks_sum_into_audio_budget_with_warning_for_unknown_bitrate`, `test_surround_default_bitrate_used_for_unknown_multichannel_track` |
| Mehrere Titel | `test_multiple_titles_sum_duration_and_size` |
| Sehr lange Laufzeit | `test_very_long_duration_computes_without_overflow_or_error` |
| Laufzeit 0 | `test_zero_duration_yields_no_bitrate_but_no_crash`, `test_empty_title_list_behaves_like_zero_duration` |
| Ungültige Custom-Größe | `test_invalid_custom_size_produces_error_not_exception` (parametrisiert: 0, -1, None), `test_custom_without_authoring_format_produces_error` |
| Overhead wird berücksichtigt | `test_reserved_overhead_matches_authoring_format_constant`, `test_bdmv_authoring_format_uses_its_own_overhead_constant` |
| Video-Bitrate aus Budget/Dauer | `test_max_average_video_bitrate_is_computed_exactly_from_budget_and_duration` |
| Unbekannte Metadaten -> kontrolliertes Verhalten | `test_unknown_title_size_makes_total_size_unknown_not_zero`, `test_unknown_title_duration_is_treated_as_partial_sum_with_warning` |
| Serialisierung | `test_plan_to_dict_round_trips_through_json`, `test_error_plan_serializes_cleanly_with_null_numeric_fields` |
| Bridge-Aufruf | `test_bridge_plan_capacity_requires_a_device`, `test_bridge_plan_capacity_returns_serialized_plan_for_all_titles_by_default`, `test_bridge_plan_capacity_supports_custom_target`, `test_bridge_plan_capacity_respects_selected_title_indices` |

Zusätzlich (zur Absicherung der Randfall-Tabelle):
`test_multiple_subtitle_tracks_scale_subtitle_overhead_linearly`,
`test_target_too_small_for_overhead_alone_sets_error`,
`test_target_too_small_for_audio_alone_sets_error`,
`test_unknown_target_medium_id_produces_error_not_exception`.

Die Bridge-Tests verwenden dieselbe `bare_bridge`-Fixture mit echtem
Hintergrund-Thread wie in P0 Block 1 (`tests/test_disc_content.py`) - lokal
dupliziert statt geteilt, da kein `conftest.py` existiert (siehe P0 Block 1
für die Begründung).

## Tests vorher / nachher

- Vorher (Stand nach P0 Block 1, Korrekturdurchlauf): 844 passed, 19 skipped,
  1 failed (bekannt/unabhängig, siehe `STABILITY_QUEUE_INIT.md`).
- Nachher: **888 passed**, 19 skipped, **1 failed** (derselbe, unveränderte
  Fehler `test_every_queueing_bridge_method_returns_a_usable_job` -
  `tests/test_job_submission.py` in diesem Block **nicht angefasst**,
  bestätigt via `git diff --stat -- tests/test_job_submission.py` = leer).
- +44 neue Tests (10 + 34), alle grün. Zusätzliche Gates: `compileall`
  (grün), `scripts/verify_ui_bridge.py` (PASS, 0 Findings), `git diff --check`
  (grün).

## Vorbereitung für den Smart Space Optimizer

Bewusst so strukturiert, dass ein späterer Smart Space Optimizer auf diesem
Planer aufbauen kann, ohne ihn zu ersetzen:

- **`max_average_video_bitrate_bps`** ist bereits exakt die Zahl, die ein
  Optimizer als Ziel-Bitrate für die Neukodierung verwenden würde.
- **`required_space_bytes`** ist bewusst ein von `estimated_source_size_bytes`
  getrenntes Feld, obwohl beide in diesem Block identisch sind. Ein
  Optimizer würde `required_space_bytes` auf Basis einer *gewählten*
  reduzierten Bitrate neu berechnen, während `estimated_source_size_bytes`
  unverändert die ursprüngliche Quellgröße zum Vergleich bliebe.
- **`warnings`** ist der bereits etablierte Kanal, über den ein Optimizer
  seine eigenen Annahmen (z. B. gewählte Zielbitrate, Downscaling-Faktor)
  transparent machen kann, statt einen neuen Mechanismus zu erfinden.
- **`video_mode_hint`** wird bereits entgegengenommen und durchgereicht,
  beeinflusst die Berechnung in diesem Block aber bewusst noch nicht -
  Platzhalter für codec-abhängige Verfeinerungen (z. B. unterschiedliche
  Container-/Encoder-Overheads je nach H.264/H.265/MPEG-2), die eine
  vollständige Optimierungslogik wären und ausdrücklich nicht Teil dieses
  Blocks sind.

Der eigentliche Smart Space Optimizer (automatische Bitrate-/Auflösungswahl,
Multi-Pass-Planung, Encoder-Preset-Auswahl) wurde **nicht** implementiert -
wie beauftragt.

## Bekannte Einschränkungen

- **2 %-Sicherheitsmarge ist eine Pauschale, keine sektorgenaue Messung.**
  Für alle Medien einheitlich, nicht individuell aus UDF-Metadatengrößen
  hergeleitet - siehe "Nutzbare Kapazität und Sicherheitsmarge" oben.
- **Authoring-/Container-Overhead ist eine grobe, konstante Schätzung**
  (10 MB DVD-Video, 5 MB BDMV), unabhängig von der tatsächlichen Titel-/
  Kapitelanzahl. Für die in P0 Block 1 dokumentierten typischen Fälle
  (Einzelfilm-DVD/BD) ist das eine sichere Überschätzung; bei sehr vielen
  Titeln/Kapiteln könnte der reale Overhead höher liegen.
- **Audio-Standardannahmen (192/448 kbit/s) sind grobe AC-3-Richtwerte**,
  keine formatspezifische Modellierung (DTS, TrueHD, LPCM haben andere
  typische Bitraten). Für P0 Block 1s dokumentierte DVD-Sprachlücke ist das
  ohnehin meist der Fall, da Bitraten dort selten gemessen vorliegen.
- **Untertitel-Overhead (5 MB/Spur) ist eine pauschale Reserve**, keine
  Unterscheidung zwischen Bitmap- (DVD/PGS) und Text-Untertiteln
  (die real deutlich kleiner sind).
- **Kein Menü-Authoring-Overhead.** Da RetroDisc laut LV-Gap-Analyse aktuell
  kein DVD-/BD-Menü-Authoring anbietet, ist dafür auch keine Reserve
  vorgesehen. Sollte Menü-Authoring später hinzukommen, muss der
  Projekt-Overhead entsprechend erweitert werden.
- **`fits_without_reduction`/`transcoding_required` sind `Optional[bool]`,
  nicht strikt `bool`.** Eine bewusste Abweichung von der wörtlichen
  "ja/nein"-Formulierung: wenn die Quellgröße unbekannt ist, wäre ein
  erzwungener `True`/`False`-Wert selbst eine Form von erfundenem Wert -
  siehe Randfall-Tabelle oben.
- **Bestehende, unabhängige Größenprüfung bleibt unverändert.** In
  `retrodisc_launcher.py` (Zeile ~1089, im Rip-/Burn-Pfad) existiert bereits
  eine *reaktive* Kapazitätsprüfung (`capacity < job.output_path.stat().st_size`
  nach fertigem Abbild). Sie wurde in diesem Block bewusst **nicht**
  angefasst oder auf den neuen Planer migriert ("nicht ungefragt
  großflächig refaktorieren") - eine Migration ist ein guter Kandidat für
  einen künftigen Block, sobald der Planer produktiv in einem echten
  Authoring-Ablauf eingebunden ist.
- **Getestet nur mit handgebauten `DiscTitle`-Objekten**, nicht mit einer
  echten eingelegten Disc oder echtem Encoding - konsistent mit der in
  P0 Block 1 dokumentierten Einschränkung (kein optisches Laufwerk in
  dieser Umgebung verfügbar).
- **Keine UI-Anbindung.** `plan_capacity` ist über die Bridge erreichbar,
  aber von keiner Stelle in `app.html` aufgerufen - wie beauftragt.

## Nicht verändert

`src/ui/app.html`, `src/services/disc_analyzer.py`, `src/services/dvd_ifo.py`,
`src/services/bluray_mpls.py`, `src/models/disc_content.py`,
`src/services/main_movie.py`, `src/services/ripper.py`,
`src/services/dvd_workflow.py`, `src/core/disc.py`, die bestehende
reaktive Kapazitätsprüfung in `retrodisc_launcher.py` (Rip-/Burn-Pfad),
`tests/test_job_submission.py`. Kein Commit, kein Push.
