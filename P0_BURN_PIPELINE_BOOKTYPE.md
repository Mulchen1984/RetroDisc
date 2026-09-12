# P0 Block 3: Ein kanonischer Brennpfad, Book Type, Verify (2026-09-11)

Separater Auftrag, auf P0 Block 1 (DiscContent) und P0 Block 2
(Kapazitätsplanung) aufbauend. Ziel ausschließlich: die parallelen
Brennpfade vereinheitlichen, Book Type in den produktiv verwendeten Pfad
integrieren, die vorhandene Verify-Logik konsistent nutzen. Ausdrücklich
NICHT Teil dieses Blocks: Preview Player, Smart Space Optimizer, Wizard
Mode, Expert Mode, Quality Bar, Titel-/Kapitel-/Audio-/Untertitel-UI,
On-the-fly Disc Copy. Keine Änderung am sichtbaren UI-Design.

## Ausgangssituation

### Bisherige parallele Brennpfade

`src/core/disc.py` enthielt zwei unterschiedlich fähige Methoden:

- **`burn_iso()`** - die tatsächlich produktiv verwendete Methode: schreibt
  das ISO-Image via `growisofs`/`cdrecord`, verifiziert optional über das
  einfache `verify_iso()` (wirft `DiscError` bei Abweichung), gibt `bool`
  zurück. **Kein** Book-Type-Parameter.
- **`burn_iso_result()`** - die funktional reichere Methode: setzt vor dem
  Brennen optional Book Type, liefert ein strukturiertes `BurnResult`
  (`src/services/booktype.py`) mit `book_type_actual`, `verify_result` als
  bloßer String ("PASS"/"NOT_AVAILABLE"), `warnings`. Delegiert das
  eigentliche Schreiben bereits intern an `burn_iso()` - dupliziert also
  keine Low-Level-Brennlogik.

### Analyse der tatsächlichen Aufrufer (vor jeder Änderung durchgeführt)

| Aufrufer | Ruft auf | Übergibt Book Type? |
|---|---|---|
| `src/services/dvd_workflow.py::DVDWorkflow.run()` (Schritt 5, `create_dvd`-Job) | `self.disc.burn_iso(...)` | Nein |
| `retrodisc_launcher.py::copy_disc()`-Handler (Disc-Copy-Job) | `self.disc.burn_iso(...)` | Nein |
| `scripts/verify_disc_workflow.py` (Smoke-Skript, kein pytest) | `tools.burn_iso(...)` | Nein |
| `tests/test_burn_result.py` (eigene Testdatei) | `t.burn_iso_result(...)` (mit `t.burn_iso` gefaked) | Ja |

**Ergebnis der Analyse:** `burn_iso_result()` hatte **null produktive
Aufrufer** - ausschließlich seine eigene Testdatei. Book Type und das
strukturierte Verify-Ergebnis existierten also bereits vollständig
implementiert, wurden aber vom tatsächlich genutzten Pfad nie erreicht.
Das ist exakt die im Auftrag beschriebene Doppelstruktur.

### Parameter-/Rückgabewert-Unterschiede (vor der Änderung)

| | `burn_iso()` | `burn_iso_result()` |
|---|---|---|
| Book Type | nicht vorhanden | `book_type: str = "automatic"` |
| Medientyp | nicht vorhanden | `media_type: str = "unknown"` |
| Rückgabe | `bool` | `BurnResult` (dataclass) |
| Verify-Detail | wirft bei Fehlschlag, keine Unterscheidung Burn-/Verify-Fehler | `verify_result: str` - aber **verifizierte nie strukturiert**: `"PASS"`/`"NOT_AVAILABLE"` wurde direkt aus dem `verify`-Flag abgeleitet, nicht aus einer echten Prüfung; ein Verify-Fehlschlag hätte (da `burn_iso()` dabei wirft) die Exception ungefiltert durchgereicht, statt ihn im Ergebnis abzubilden |
| Fehlerzustand | Exception | Exception (Burn) / kein separates Feld |

## Neue kanonische Architektur

**Es gibt jetzt genau eine Methode mit eigener Brennlogik: `DiscTools.burn_iso()`.**
Sie wurde selbst zum kanonischen Pfad erweitert, statt eine weitere neue
Methode einzuführen - dadurch profitieren beide bestehenden produktiven
Aufrufer (`DVDWorkflow`, `copy_disc`) automatisch, ohne dass ihr Aufruf-
Name sich ändert.

```python
async def burn_iso(
    self, iso_path, device="/dev/sr0", speed=None, verify=True,
    disc_type=DiscType.DVD, job=None,
    book_type: BookType = BookType.NATIVE,   # Standard: keine Änderung (Rückwärtskompatibilität)
    media_type: Optional[str] = None,         # None -> automatisch über get_disc_info ermittelt
) -> BurnOutcome:
    ...
```

Ablauf:
1. Book Type **vor** dem Schreiben anwenden (`dvd+rw-booktype` wirkt auf
   den Rohling, nicht auf den ISO-Inhalt) - nie eine Exception, nur
   Status/Warnung im Ergebnis.
2. Das eigentliche Schreiben (`growisofs`/`cdrecord`) - **unverändert**
   gegenüber vorher; wirft weiterhin `DiscError` bei echtem Brennfehler.
3. Book Type zurücklesen, falls angewendet.
4. Verifikation über `verify_iso_result()` (bereits vorhandene, getestete
   Methode aus `src/core/disc.py`) - strukturiert, wirft nie.
5. Rückgabe eines `BurnOutcome` (`src/services/burn_outcome.py`).

**`burn_iso()` wirft weiterhin `DiscError` bei einem echten Brennfehler**
(Rückwärtskompatibilität: bestehende Aufrufer werten Erfolg über
Exceptions aus, nicht über ein Rückgabefeld - siehe `test_copy_io_errors_fail_job_without_unwanted_burn`).
Ein fehlgeschlagener Book-Type-Versuch oder eine fehlgeschlagene
Verifikation lösen dagegen **nie** eine Exception in `burn_iso()` selbst
aus - beides wird stattdessen im zurückgegebenen `BurnOutcome` gemeldet;
migrierte Aufrufer entscheiden selbst, ob sie einen Verify-Fehlschlag zum
Job-Fehler machen (siehe „Migrierte Aufrufer").

`BurnOutcome` deckt alle geforderten Felder ab: ISO-Pfad (Parameter),
Ziel-Laufwerk (`device`), Verify an/aus (`verify.status`), Book Type
(`book_type_requested`/`book_type_status`/`book_type_actual`), klarer
Fehlerstatus (`error`, `burn_success`), Burn-Ergebnis (`burn_success`,
`written_size`, `burn_speed`), Verify-Ergebnis (`verify: VerifyResult`).

## Book-Type-Modell

Neue zentrale Enum in `src/services/booktype.py` - keine frei verteilten
String-Vergleiche mehr für die Kernentscheidung:

```python
class BookType(Enum):
    AUTO = "automatic"
    NATIVE = "native"
    DVD_ROM = "dvd_rom"
```

Werte identisch zur bestehenden `BookTypeSetting`-Literal-Definition
gehalten, damit bestehende Aufrufer/Tests, die rohe Strings übergeben,
unverändert weiterfunktionieren; `_as_book_type()` normalisiert
zentral zwischen String und Enum. `booktype_command()` vergleicht intern
nur noch gegen die Enum, nicht mehr gegen rohe Strings.

Neue `BookTypeStatus`-Enum (`src/services/burn_outcome.py`) für das
Ergebnis - unterscheidet genau die im Auftrag geforderten Zustände:

```python
class BookTypeStatus(Enum):
    NOT_REQUESTED = "not_requested"    # NATIVE
    NOT_APPLICABLE = "not_applicable"   # Medium/Disc-Typ kann grundsätzlich kein Bitsetting
    NOT_SUPPORTED = "not_supported"      # Medium geeignet, aber Backend/Werkzeug fehlt
    APPLIED = "applied"                   # erfolgreich gesetzt
    FAILED = "failed"                      # Werkzeug-Aufruf schlug fehl
```

### AUTO

Entscheidet anhand von Medium **und** Backend, ob eine Änderung sinnvoll
ist: ist das Medium bitsettbar (`DVD+R`/`DVD+RW`/`DVD+R DL`) **und** das
Backend (`dvd+rw-booktype`) vorhanden, wird - wie bei einer expliziten
DVD-ROM-Anfrage - versucht, DVD-ROM zu setzen (`APPLIED`/`FAILED`). Fehlt
das Backend, `NOT_SUPPORTED` + Warnung. Ist das Medium grundsätzlich nicht
bitsettbar (falsche DVD-Familie oder Blu-ray), `NOT_APPLICABLE`, keine
Warnung - eine nicht anwendbare Operation ist kein Fehler.

### NATIVE

Erzwingt **nie** eine Änderung, unabhängig von Medium oder Backend -
`NOT_REQUESTED`. Das ist zugleich der **Standardwert** von `burn_iso()`,
wenn kein `book_type` übergeben wird, damit bestehende Aufrufer
(`scripts/verify_disc_workflow.py`, direkte `DiscTools()`-Nutzung ohne
Kenntnis von Book Type) unverändert funktionieren.

### DVD-ROM

Versucht explizit, DVD-ROM zu setzen, **nur** wenn Medium und Backend das
unterstützen (`APPLIED`/`FAILED`), sonst `NOT_APPLICABLE`/`NOT_SUPPORTED`
wie bei AUTO. AUTO und DVD-ROM teilen sich dieselbe zugrunde liegende
Mechanik (`_apply_book_type()`) - der einzige Unterschied ist, dass NATIVE
diese Mechanik von vornherein gar nicht erst aufruft.

**Eine erfolgreiche Brennung behauptet nie automatisch eine erfolgreiche
Book-Type-Änderung:** `burn_success` und `book_type_status` sind getrennte
Felder in `BurnOutcome`. Ein Book-Type-Fehlschlag setzt niemals
`burn_success=False`.

## Medienabhängigkeit

Blu-ray bekommt **strukturell nie** eine DVD-spezifische Book-Type-
Operation - zwei unabhängige Sperren in `_apply_book_type()`:

1. `disc_type == DiscType.BLURAY` → sofort `NOT_APPLICABLE`, unabhängig
   davon, wie `media_type` klassifiziert wurde (Verteidigung in der
   Tiefe - falls `media_type` einmal falsch oder `"unknown"` klassifiziert
   würde, bliebe die Sperre trotzdem wirksam).
2. `not supports_bitsetting(media_type)` (bestehende Funktion aus
   `booktype.py`, unverändert: nur `DVD+R`/`DVD+RW`/`DVD+R DL` gelten als
   bitsettbar - die DVD-Familie mit Minus und alle Blu-ray-Profile fallen
   durch) → ebenfalls `NOT_APPLICABLE`.

Beide Fälle sind ein **nachvollziehbares, strukturiertes Ergebnis**
(`BookTypeStatus.NOT_APPLICABLE`), keine Exception und keine unnötige
Warnung.

## Verify

`burn_iso()` verifiziert jetzt über **`verify_iso_result()`** (bereits
vorhandene, in `tests/test_verify.py` getestete Methode) statt über das
rohe `verify_iso()` - derselbe gemeinsame Verify-Pfad wie überall sonst im
Projekt, keine neue parallele Implementierung. `VerifyResult` (aus
`src/services/verify.py`) wird direkt als `BurnOutcome.verify` übernommen:

- **durchgeführt ja/nein**: `verify=False` → `status=NOT_AVAILABLE`,
  Nachricht „Verifikation deaktiviert."
- **erfolgreich ja/nein/unbekannt**: `status` ∈ {`PASS`, `PASS_WITH_WARNINGS`,
  `FAIL`, `NOT_AVAILABLE`}
- **Fehler/Warnung**: `message`, `checks` (strukturierte Einzelprüfungen)
- **Prüfmethode**: implizit über die vorhandene `Check`-Struktur
  (`name="hash"`/`"size"` etc.)

## Migrierte Aufrufer

### `src/services/dvd_workflow.py::DVDWorkflow.run()`

- `DVDProject` bekommt ein neues Feld `book_type: str = "automatic"`
  (Standard = AUTO - sinnvoller, sofort nutzbarer Produktivwert ohne
  neue UI).
- Der Burn-Aufruf übergibt `book_type=_as_book_type(project.book_type)`.
- Das zurückgegebene `BurnOutcome` wird auf `job.params["burn_outcome"]`
  gespeichert (Vorbereitung für eine spätere UI-Anzeige, ohne dass diese
  in diesem Block gebaut wird) und bei `outcome.verify.status == FAIL`
  wird explizit `DiscError` geworfen - **dasselbe für den Nutzer sichtbare
  Verhalten wie vorher** (Verify-Fehlschlag lässt den Job fehlschlagen),
  jetzt aber über ein strukturiertes Zwischenergebnis statt über eine
  durchgereichte, nicht weiter unterscheidbare Exception.

### `retrodisc_launcher.py::copy_disc()`

- Bekommt einen neuen optionalen Parameter `book_type: str = "automatic"`,
  im Job-Handler an `burn_iso()` weitergereicht (`_as_book_type(...)`).
- Gleiches Verify-Fehlschlag-Verhalten wie bei `DVDWorkflow` (explizites
  `raise DiscError(...)` bei `outcome.verify.status == FAIL`), `BurnOutcome`
  ebenfalls auf `job.params["burn_outcome"]` gespeichert.

### Bridge/API

- `RetroDiscBridge.create_dvd(...)`: neuer Parameter `book_type: str = "automatic"`,
  landet in `job.params["book_type"]` und wird an `DVDProject` durchgereicht.
- `RetroDiscBridge.copy_disc(...)`: neuer Parameter `book_type: str = "automatic"`.
- `RetroDiscApi.create_dvd`/`copy_disc` sind bereits als `(*args)`-Proxys
  implementiert - keine Änderung an der Proxy-Schicht nötig,
  `scripts/verify_ui_bridge.py` bleibt PASS (0 Findings).
- **Keine UI-Anbindung** - `app.html` ruft die neuen Parameter nirgends
  auf; wie beauftragt keine Änderung am sichtbaren UI-Design.

### Nicht migriert (bewusst)

`scripts/verify_disc_workflow.py` (Smoke-Skript) ruft `burn_iso()` weiterhin
ohne `book_type` auf - bekommt automatisch `BookType.NATIVE`, also exakt
das bisherige Verhalten. Keine Änderung nötig oder vorgenommen.

## Kompatibilitäts-Wrapper

`burn_iso_result()` bleibt als dünner Wrapper bestehen, **unverändert im
Code** - er ruft weiterhin ausschließlich `self.burn_iso(...)`,
`self._run_tool(...)` und `self._read_book_type(...)` auf und enthält
selbst keine Brennlogik (das war schon vor diesem Block so). Da er
`burn_iso()` ohne `book_type`/`media_type` aufruft, bekommt er automatisch
den neuen `BookType.NATIVE`-Standardwert (keine Doppelausführung der
Book-Type-Logik: `burn_iso_result()` erledigt Book Type weiterhin selbst
mit seiner eigenen, alten Logik; der intern aufgerufene `burn_iso()` lässt
Book Type dabei unangetastet). Das alte `BurnResult` (`src/services/booktype.py`)
bleibt als eigene, unveränderte Datenklasse bestehen - bewusst getrennt vom
neuen `BurnOutcome`, weil `burn_iso_result()`s Form (`verify_result` als
bloßer String) exakt für die bestehenden, weiterhin grünen Tests in
`tests/test_burn_result.py` erhalten bleiben muss. Das ist eine gezielte,
schmale Kompatibilitätsausnahme, keine Fortführung der ursprünglichen
Doppelstruktur: die eigentliche Brennlogik existiert nur noch einmal
(in `burn_iso()`), nur die alte Ergebnis-Form bleibt für den alten Wrapper
erhalten.

`burn_iso_result()` wird **weiterhin von keinem produktiven Pfad
aufgerufen** - ausschließlich von seiner eigenen Testdatei.

## CapacityPlanner (P0 Block 2)

Keine Änderung an `src/services/capacity_planner.py` oder
`src/config/target_media.py` in diesem Block. Der Burn-Aufruf selbst
prüft aktuell **nicht** gegen einen vorhandenen `CapacityPlan` - eine
solche Prüfung (z. B. „Burn ablehnen, wenn `CapacityPlan.error` gesetzt
ist") würde diesen Block unnötig vergrößern, da sie eine Entscheidung
verlangt, wo/wie ein `CapacityPlan` für einen Burn-Auftrag überhaupt
angefordert wird (derzeit unabhängige Bridge-Methode `plan_capacity`,
nicht in `create_dvd`/`copy_disc` eingebunden). **Das wird ausdrücklich
nicht in diesem Block behandelt** und bleibt offener Punkt für einen
späteren Block (siehe unten).

## Tests

### `tests/test_burn_pipeline.py` (neu, 22 Tests)

| Geforderter Testfall | Test(s) |
|---|---|
| AUTO | `test_auto_applies_dvd_rom_when_medium_and_backend_support_it`, `test_auto_is_not_applicable_on_non_bitsettable_medium` |
| NATIVE | `test_native_never_attempts_a_change_even_on_capable_medium`, `test_burn_iso_default_book_type_is_native_for_backward_compatibility` |
| DVD-ROM | `test_dvd_rom_supported_applies_and_reads_back` |
| DVD-ROM unterstützt | `test_dvd_rom_supported_applies_and_reads_back` |
| DVD-ROM nicht unterstützt | `test_dvd_rom_not_supported_medium_family_is_not_applicable`, `test_dvd_rom_capable_medium_but_missing_backend_is_not_supported` |
| Book-Type-Fehler bei sonst erfolgreicher Brennung | `test_book_type_tool_failure_does_not_fail_an_otherwise_successful_burn` |
| Blu-ray ohne DVD-Book-Type-Manipulation | `test_bluray_never_gets_dvd_book_type_operation_even_if_requested`, `test_bluray_disc_type_overrides_even_a_dvd_like_media_classification` |
| Verify erfolgreich | `test_verify_success_is_reflected_in_structured_result` |
| Verify fehlgeschlagen | `test_verify_failure_does_not_raise_and_is_distinguishable_from_burn_failure` |
| Verify deaktiviert | `test_verify_disabled_yields_not_available_status` |
| Burn fehlgeschlagen | `test_burn_failure_raises_disc_error`, `test_missing_iso_raises_before_any_subprocess_call` |
| Strukturierte Ergebnisserialisierung | `test_burn_outcome_serializes_to_json_safe_dict`, `test_burn_outcome_is_always_truthy_on_success_for_legacy_if_checks` |
| Alter Wrapper nutzt den neuen Pfad | `test_burn_iso_result_wrapper_delegates_to_real_burn_iso_subprocess_layer` |
| Queue/DVD-Workflow nutzt den kanonischen Pfad | `test_dvd_workflow_burn_step_uses_canonical_path_with_auto_book_type`, `test_dvd_workflow_raises_when_verify_fails_even_though_burn_succeeded`, `test_create_dvd_bridge_threads_book_type_into_dvd_project` |
| Disc-Copy nutzt den kanonischen Pfad | `test_copy_disc_handler_passes_book_type_to_canonical_burn_iso` |

### Angepasste bestehende Tests

`tests/test_disc_copy_flow.py`: die gemeinsame `burn()`-Testdouble in der
`copy_runtime`-Fixture akzeptiert jetzt `**kwargs` und gibt ein
`BurnOutcome(burn_success=True)` zurück (vorher: keine Rückgabe, feste
Parameterliste ohne `book_type`) - notwendig, weil `copy_disc()` jetzt
`book_type` an `burn_iso()` übergibt und `burn_iso()` jetzt ein
`BurnOutcome` statt `None`/`bool` liefert. Alle bestehenden Prüfungen
(`c[0] for c in r.calls`, Fehlerpfade, Medienbestätigung) bleiben
unverändert und weiterhin grün.

## Tests vorher / nachher

- Vorher: 888 passed, 19 skipped, 1 failed (bekannt/unabhängig).
- Nachher: **910 passed**, 19 skipped, **1 failed** (derselbe, unveränderte
  Fehler `test_every_queueing_bridge_method_returns_a_usable_job` -
  `tests/test_job_submission.py` in diesem Block nicht angefasst, bestätigt
  via `git diff --stat` = leer). +22 neue Tests, alle grün.
- Zusätzliche Gates: `compileall` (grün), `scripts/verify_ui_bridge.py`
  (PASS, 0 Findings), `git diff --check` (grün).

## Verbleibende Einschränkungen

- **Kein Zusammenspiel mit dem CapacityPlanner** beim eigentlichen
  Brennen - siehe Abschnitt oben, bewusst nicht in diesem Block.
- **`burn_iso_result()`s alte Ergebnis-Form bleibt ungenau**: ihr eigenes
  `verify_result`-Feld ist weiterhin ein simples "PASS"/"NOT_AVAILABLE"
  ohne echte Fehlerunterscheidung (unverändert seit vor diesem Block) -
  das ist die bewusst erhaltene Alt-Form für Rückwärtskompatibilität,
  nicht der empfohlene Weg für neue Aufrufer.
- **`DiscRipper` (Rip-Feature) bleibt unverändert** und nutzt weiterhin
  seine eigene, ältere Main-Movie-Heuristik (siehe P0 Block 1) - mit dem
  Brennpfad dieses Blocks nicht verwandt, nur der Vollständigkeit halber
  erwähnt.
- **Kein Menü-Authoring, kein DVD-9/BD-Zielgrößen-Bezug beim Brennen** -
  weiterhin außerhalb des Umfangs (siehe LV-Gap-Analyse, P0 Block 2).
- **Nur mit gefakter Subprozess-/Werkzeug-Ebene getestet**, nicht mit
  echter Hardware (kein optisches Laufwerk in dieser Umgebung verfügbar) -
  konsistent mit allen bisherigen Disc-Fähigkeiten dieses Projekts.
- **Keine UI-Anbindung** für Book Type - Bridge/API-seitig vorbereitet,
  aber `app.html` ruft die neuen Parameter nirgends auf, wie beauftragt.

## Offene Punkte

- Integration des `CapacityPlanner` in den Burn-Aufruf (Prüfen/Validieren
  einer vorhandenen Kapazitätsplanung vor dem Brennen) - ausdrücklich für
  einen späteren Block vorgesehen.
- UI für Book-Type-Auswahl (AUTO/NATIVE/DVD-ROM) - Bridge/API ist bereits
  vorbereitet (`create_dvd`/`copy_disc` akzeptieren `book_type`).
- Anzeige des gespeicherten `job.params["burn_outcome"]` in der Job-Queue-
  Oberfläche - Datenfluss ist vorbereitet, aber keine UI dafür gebaut.
- `burn_iso_result()` könnte in einem späteren, ausdrücklich beauftragten
  Aufräum-Block ganz entfernt werden, sobald sicher ist, dass kein Code
  mehr auf seine spezifische alte Ergebnis-Form angewiesen ist.
