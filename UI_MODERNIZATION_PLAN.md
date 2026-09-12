# RetroDisc UI – gezielte Modernisierung

## Ausgangsstand / Rückfallebene

- Basis: `fc58fa6`, bestehender Worktree inklusive uncommittiertem Editor-/Queue-WIP.
- Geprüftes Quellbackup: `.ui-backups/20260910T161507Z/` (243 Dateien).
- `manifest.json`: Einzelprüfsummen, Branch, Commit; `source.tar.gz`: vollständiger
  nicht ignorierter Quell-Arbeitsstand; `working-tree.patch`: Änderungen zu HEAD.
- Archiv-SHA256: `a9ddbd025be135e9d24233c151cf5c8f939fc30133b9e83e4b2ba1dd63772226`.
- Wiederherstellung: zunächst in leeren Ordner entpacken, vergleichen, gewünschte
  Dateien zurückkopieren. Anleitung liegt beim Backup. Kein Reset erforderlich.
- Backup liegt außerhalb von build/dist und bleibt bei Build-Cleanup erhalten.
  Ignorierte Medien, virtuelle Umgebungen und private Einstellungen sind nicht enthalten.
- Vor jedem weiteren größeren UI-Block neues datiertes Backup mit Prüfsummen.

## Übernehmen

- Fünf Hauptaktionen, eigene orange Disc-Symbole und dezente Retro-Gesten.
- Startseite → Workflow mit Zurück-Navigation, linke Dateiliste und Statusleiste.
- Alle 13 Funktionspanels, vorhandene Editor-Timeline und Capability-Anzeigen.
- Bestehende Komponenten `.btn98`, `.sect`, `.sgroup`, Formularfelder und Dialoge.
- IDs, Eventhandler, Bridge-Aufrufe und bestehende Plattformunterscheidung.

## Anpassen – erster freizugebender Block

Nur `src/ui/app.html`: gemeinsame Darstellung, keine Business-Logik.

1. CSS-Regeln für Schrift, Abstände, Farben, Eingaben und Buttons konsolidieren;
   vorhandene Klassennamen erhalten. Primäre Aktionen klar hervorheben.
2. Feste 840px-Begrenzung gezielt lösen; Texte lesbar begrenzen, Editor/Listen
   die verfügbare Breite nutzen lassen. Kleine Fenster weiterhin unterstützen.
3. Dateiliste, Karten und Abschnittsüberschriften ruhiger und lesbarer gestalten.
4. Fokus-, Disabled- und Fehlerzustände sowie lange Dateinamen überprüfen.

## Spätere, getrennte Blöcke

- Director: bestehende Bereiche Medien/Aufgabe/Plan/Bearbeiten/Rendern visuell ordnen.
- Editor: vorhandene Tracks und Eigenschaften deutlicher trennen.
- Spezialansichten und Dialoge auf dieselben Komponenten abstimmen.
- Keine zusätzliche Navigationsebene und kein zweites Frontend ohne konkreten Bedarf.

## Vergleich / Tests

- Vor und nach jedem Block identische Ansichten und Fenstergrößen aufnehmen:
  Start, Konvertieren, KI-Regisseur/Timeline, Queue, Einstellungen.
- Browser-Screenshots dienen nur dem Layoutvergleich; native macOS-/Windows-Abnahme
  und echte Backend-Workflows getrennt ausweisen.
- Alle 13 Panels erreichbar, fünf Hauptaktionen sichtbar, kein abgeschnittener
  Hauptinhalt, keine unerreichbaren Dialogaktionen; lange Namen und Resize prüfen.
- UI-Smoke, Escaping, Plattform-UI, Bridge-Verifikation, JS-Syntax, diff --check.
- Nach jedem Block dokumentieren: übernommen / angepasst / ersetzt / getestet.

## Risiken / aktueller Status

- app.html enthält mehrere CSS-Schichten und Inline-Styles; globale Maße können
  kleine Fenster oder komplexe Formulare beeinflussen. Deshalb schrittweise migrieren.
- README/CLAUDE-Plattformbeschreibung ist älter als das aktuelle Auditjournal;
  Windows und macOS bleiben entsprechend dem Nutzerauftrag gleichberechtigt.
- Vorhandene Queue-/Editor-WIP-Dateien sind gesichert und nicht Teil des UI-Umbaus.

## Block 1 — abgenommen (2026-09-10)

Gemeinsame Styles (Tokens, Buttons, Karten, Fokus/Disabled, 840px-Auflösung,
Dateinamen-Umbruch) fertig. Ein Nachtrag ergänzt: `.sect-body > p { max-width:70ch }`
für lesbare Fließtextbreite auf großen Fenstern. Real interaktiv geprüft (Playwright
gegen den echten Quellcode, `output/playwright/ui-block-1/`): Navigation, Datei-
auswahl, Select/Textfeld/Checkbox, primärer/sekundärer Button, Disabled-State,
ein echter Dialog (`confirm()`) geöffnet und geschlossen, Resize bei 1180×760,
1440×900 und 1728×1050 ohne horizontales Scrollen/Clipping/Überlappung. Vorher/
Nachher für Start, Konvertieren (inkl. langer Unicode-Dateiname), KI-Regisseur,
Einstellungen visuell geprüft. Bekannter Pipeline-/SQLite-Testfehler
(`test_disc_copy_flow.py`, `test_disc_flows.py`, `test_job_submission.py`) isoliert
reproduziert **mit UI-Dateien auf HEAD zurückgesetzt** (alle anderen WIP-Dateien
unverändert) → identischer Fehler → nachweislich nicht durch diesen UI-Block
verursacht, sondern vorbestehend in der Pipeline-WIP.

## Block 2 — erster Teilschritt abgenommen (2026-09-10)

Umgesetzt:
- `#rightpanel .tabpanel:not(#tab-ai) { max-width:1200px; margin-inline:auto }`
  gegen das bei Block 1 zurückgestellte Sprawl-Problem auf sehr breiten Fenstern
  (1728px+): Karten bleiben lesbar/kompakt statt im Inneren auszufransen;
  `#tab-ai` (Director/Editor/Timeline) bleibt bewusst ausgenommen (volle Breite
  für Tracks/Listen, wie in Block 1 festgelegt). Bei 1180/1440px inert (Inhalt
  war da ohnehin schon schmaler als 1200px).
- Gemeinsame Statusfarben für Job-Zeilen (`.jobrow.st-pending/running/done/
  failed/cancelled`) statt bisherigem Ad-hoc-Inline-Style nur für „running";
  nutzt ausschließlich Zustände, die `S.jobs`/`job.state` im bestehenden System
  tatsächlich liefert. Reale IDs/Icons/Handler unverändert.

Navigation/Dateiliste: bei Prüfung als bereits ausreichend befunden (Gruppen
ERSTELLEN/RETTEN/WERKZEUGE, Hover/Selected/Meta-Text) — keine zusätzliche
Navigationsebene eingeführt, wie vom Nutzer gefordert.

Offen für einen weiteren Block-2-Teilschritt oder Block 3: Statusfarben auch in
Batch-/Downloadergebnis-Listen anwenden; Director/Editor-Bereichsgliederung
(Medien/Aufgabe/Plan/Bearbeiten/Rendern) visuell trennen.

## Block 3 — abgenommen (2026-09-10)

AI Director in `#tab-ai` von einer einzigen undifferenzierten Karte in 5
sequenzielle `.sect`-Karten (`.director-steps`) mit nummeriertem Kopf
(Medien/Aufgabe/KI-Plan/Bearbeiten/Rendern) umgebaut; alle IDs/Handler/Bridge-
Aufrufe unverändert übernommen, nur re-parented. Rohes JSON (`#directorPlan`)
in ein `<details>` "Experten-Ansicht" eingeklappt (Info-Dichte runter, Wert
bleibt per `.value` unverändert erreichbar). Timeline-Bereich bekam
Werkzeugleisten (primär oben, Audio/Slideshow/Musik sekundär+gedämpft unten)
und einen Canvas-Rahmen (`.director-canvas-body`); bleibt bewusst von der
1200px-Breitenbegrenzung ausgenommen (volle Breite für Clip-Zeilen). Die vier
eigenständigen Zusatzwerkzeuge (Ollama, Auto-Edit, Upscaling, Untertitel,
Interpolation) durch eine Trennzeile "🧰 Weitere Werkzeuge" vom Produktionsplan
abgesetzt, damit klar ist: das sind keine Workflow-Phasen.

Statusfarben (`.status-chip`/`.st-*`) von der Job-Liste auf die Batch-
Restaurierungsliste übertragen (`batchRenderList` + die beiden Stellen, die
den Status live umschalten) — bewusst NICHT auf die freien Textmeldungen
(`#directorResult` etc.) ausgeweitet, da das viele Business-Logik-Aufrufstellen
berühren würde. Alle `<details>`-Elemente (Restaurierung, Editor-Clip-
Eigenschaften, Director-JSON) auf ein gemeinsames Randlinie+Dreieck-Muster
gebracht (reine `details`/`summary`-CSS-Regel, keine neue Dialogbibliothek).
Dynamische "Schritt erledigt"-Zustände für den Director bewusst NICHT gebaut
(hätte bestehende JS-Funktionen anfassen müssen) — Phasen sind statisch klar
benannt/nummeriert, nicht live fortschrittsverfolgt; Kandidat für Block 4.

Ein Regressionsfund während der Arbeit: `batchRenderList` rief eine neu
eingeführte Helper-Funktion `batchStatusClass()` auf, die vom Node-Testharness
in `test_ui_smoke.py` (extrahiert nur benannte Funktionen einzeln) nicht mitkam
→ `ReferenceError`. Behoben durch Inline-Ternary statt externer Helper-Funktion;
seither wieder 18/18 UI-Smoke-Tests grün. Gelernte Regel: neue JS-Helfer, die
von einer der in `test_ui_smoke.py` isoliert extrahierten Funktionen aufgerufen
werden, müssen inline bleiben oder der Testextraktion hinzugefügt werden.

Geprüft bei 1180×760/1440×900/1728×1050 (Playwright gegen echten Quellcode,
`output/playwright/ui-block-1/`): kein horizontales Scrollen, Timeline behält
volle Breite, Clip-Zeilen brechen bei 1440 nur den Übergangs-Dropdown um (kein
Clipping/Überlappung). Vollständiger `pytest -q`: 775 passed/19 skipped/10
failed/19 errors — identisch zur Baseline vor Block 3, keine neuen Fehler.


## Abnahme-Nachprüfung — 2026-09-11

Die früheren „abgenommen“-Überschriften bezeichnen Teilprüfungen. Die vollständige
Abnahme nach Marcos zusätzlichen Kriterien ist **noch offen**.

- Aktuellen gemeinsamen UI-Stand inklusive Feedback-Komponente erhalten.
  Test-Harness lädt jetzt deren echte Implementierung; zusätzlicher Test prüft
  Info/Success/Warning/Error/Loading, Unicode, HTML-Escaping und lange Details.
- UI-/Escaping-/Plattform-/Drive-UI-Tests: **28 passed**. Bridge: **PASS**, 54
  Aufrufstellen/43 Methoden, keine Findings. JS-Syntax und diff --check: PASS.
- Browservergleich: **80 Szenarien**, keine pageerror-Ereignisse, kein erkannter
  horizontaler Überlauf oder seitlich abgeschnittenes Control. Alle 13 Bereiche
  bei 900/1180/1600px; kompakte Startseite bei 640×460. Das prüft Layout und
  Navigation, nicht die reale Ausführung aller Backendaktionen.
- Vorher/Nachher: `output/playwright/ui-block-1/`, jeweils Hauptfenster,
  Konvertieren mit Dateiliste, Director und Einstellungen. Vergleichsdateien,
  Screenshots und `layout-report.json` bleiben lokale Abnahme-Artefakte.
  Browser-Dateiliste verwendet ausdrücklich Beispieldaten, keine Import-Abnahme.
- Nativer Quellstart: Bridge initialisiert, Fenster gestartet, Haupt-UI geladen
  (build/ui-block-native.log). Native Computer-Use-Abfrage für Python scheitert
  mit timeoutReached. Echte Dateiauswahl, Dialogbedienung und Fenster-Resize sowie
  native Console-Abnahme sind damit **nicht nachgewiesen**.
- Breiter gezielter Regressionblock: **99 passed, 10 failed, 19 errors**.
  Disc-/Submission-Fixtures scheitern beim Bridge-Aufbau in der vorhandenen
  Queue-Anbindung (`retrodisc_launcher.py:315`, Initialisierungs-Timeout).
  Bereits vorher dokumentierter Backend-WIP-Blocker; in diesem UI-Auftrag nicht
  verändert. Nach dessen Reparatur Regression erneut ausführen.
- Backup unverändert: `.ui-backups/20260910T161507Z/source.tar.gz`, SHA256
  `a9ddbd025be135e9d24233c151cf5c8f939fc30133b9e83e4b2ba1dd63772226`.
  Wiederherstellung gemäß beiliegender WIEDERHERSTELLUNG.md.
- Keine Commits, kein Push. Keine Business-Logik für diese Nachprüfung verändert.

## Block 4 — abgenommen (2026-09-11)

Gemeinsames Feedback-System (`renderFeedback(id,kind,text,opts)`, Kinds
info/success/warning/error/loading, Icon+Wortlabel+Farbe) auf alle benannten
freien Textmeldungen übertragen: `directorResult` (alle ~16 Stellen),
`batchResult`, `restorationResult` (alle ~17 Stellen), `shortResult`,
`archiveResult`, `sresults` (Download-Suche), `airesp` (Ollama-Assistent).
Lange Meldungen (>160 Zeichen oder mehrzeilig) zeigen nur die erste Zeile,
der volle Text bleibt in einem `<details>`-Block erhalten (nichts verloren).
HTML-Escaping/XSS und Unicode real getestet (`test_feedback_states_...`).

AI-Director-Schrittstatus (`directorUpdateSteps()`) zeigt ✓/●/○/✗ für
Medien/Aufgabe/KI-Plan/Bearbeiten/Rendern, abgeleitet ausschließlich aus
echtem UI-Zustand (`S.directorAssets`, `#directorPlan`-Gültigkeit,
`#directorOutputs`-Inhalt) — keine neue State-Machine, kein MutationObserver:
Hook-Punkte sind die bereits vorhandenen Render-Funktionen
`directorSummarizePlan()`/`directorShowOutputs()` plus zwei kleine explizite
Aufrufe (`directorSelect()`, `startup()`). „Bearbeiten" gilt konservativ erst
als erledigt, wenn tatsächlich gerendert wurde (kein Rate-Signal dafür).

Primäre Buttons mit Bridge-Aufruf (`directorMakePlanBtn`, `directorRenderPlanBtn`,
`batchRunBtn`, `restorationPreviewBtn`/`restorationRunBtn`) werden während des
Aufrufs disabled (bestehendes `.btn98:disabled`-Styling, kein neuer Sperr-
mechanismus) — verhindert Doppelauslösung, macht laufende Aktionen sichtbar.

Zwei echte Regressionen gefunden und behoben, bevor sie akzeptiert wurden:
1. `directorPlanSummary` behielt nach einem Fehler die rote `feedback-error`-
   Klasse dauerhaft, auch nachdem der Plan wieder gültig wurde (Erfolgspfad
   setzte nie `className` zurück) — behoben mit `box.className=''` im
   Erfolgspfad; dieselbe Lücke vorsorglich auch bei `doSearch()` geschlossen.
2. `directorUpdateSteps()` rief `outputsField.innerHTML.trim()` ohne zu prüfen,
   ob `innerHTML` überhaupt gesetzt ist → in `test_ui_escaping.py`s isoliertem
   Mock (das für jede andere ID ein Objekt ohne `innerHTML` liefert) ein
   `TypeError`, der versteckt hinter einem weiteren `ReferenceError` auftauchte,
   weil `directorUpdateSteps`/`renderFeedback` in dieser Testdatei nicht
   mitgeladen waren. Doppelt behoben: defensive Prüfung im echten Code
   (`outputsField.innerHTML && ...`) UND die Testdatei um den echten
   `directorUpdateSteps`-Quellcode ergänzt (gleiches Muster wie in Block 3).
   Voller `pytest -q` davor: 10 failed/775 passed/19 errors + 1 neuer Fehler;
   danach wieder exakt 10 failed/776 passed/19 errors (776 statt 775, weil der
   zuvor kaputte Test jetzt zählt) — Testnamen identisch zur Baseline.

Bewusst nicht angefasst: `alert()`-basierte Fehlermeldungen (goDL, Brennen
u.a.) — natives, nicht restylebares Muster, in vielen weiteren Funktionen
konsistent verwendet; Änderung hätte viele zusätzliche Business-Logik-
Aufrufstellen berührt, außerhalb des beauftragten Rahmens.

Geprüft bei 860×560 (Minimalgröße), 1180×760, 1440×900, 1728×1050: keine
horizontale Seiten-Scrollbar (`docWidth===viewportW` gemessen), Schrittleiste
bleibt lesbar/umbricht sinnvoll. Vorher/Nachher (Director-Schrittleiste,
Erfolg, Fehler, Laufend, Batch-Ergebnisliste) visuell geprüft.

## Abschlussverifikation — 2026-09-11 (zweiter Durchlauf)

Kein Codestand-Drift (`git diff --stat` identisch zum Ende von Block 4).
Vollständiger `pytest -q`: 776 passed/19 skipped/10 failed/19 errors,
Testnamen zeilengenau identisch zur Baseline — alle 10 FAILED + 19 ERROR
haben denselben Root Cause: `RetroDiscBridge.__init__`
(`retrodisc_launcher.py:315`) wartet synchron bis zu 5 s auf
`_init_conversion_queue()` im Hintergrund-Event-Loop; bei den vielen pro
Testdatei neu erzeugten `RetroDiscBridge()`-Instanzen (fremde Pipeline-WIP,
kein `shutdown()` zwischen Tests) reicht das irgendwann nicht mehr
(TimeoutError). Bestätigt fremd/vorbestehend, nicht durch dieses UI-Redesign
verursacht, nicht verändert (kein Pipeline-Fix beauftragt).

Native Quellstart erneut bestätigt: `build/ui-block-native.log`, sauberer
Start ohne Fehler, Prozess läuft seit 06:46 Uhr stabil weiter. Computer-Use
gegen das echte Fenster erneut versucht (PID-genaues `AXRaise`, Decoy-App
`dist/RetroDisc.app` ausgeblendet) — Fenster existiert laut Accessibility-API
(sichtbar, nicht minimiert, korrekte Position), wird aber vom Screenshot-
Mechanismus nicht dargestellt. Als Ersatz: Playwright gegen den echten
Quellcode (`output/playwright/ui-final/`) — Hauptfenster, Dateiauswahl,
Editor/Bearbeiten, Job Queue, Director, Restoration real durchgeklickt;
Dialog (`confirm()`) real geöffnet/geschlossen; Exception real ausgelöst
(`api()` fehlt) → Fehler-Feedback erschien, beide Restore-Buttons blieben
NICHT disabled (Doppelklick-Schutz + Nach-Fehler-Freigabe bestätigt). Resize
860/1180/1440/1728 ohne Overflow. Vorher/Nachher gegen `.ui-backups/20260910T161507Z/`
(Hauptfenster, Dateiliste/Konvertieren, Director, Restoration-Formular) zeigt
in jedem Fall echten Fortschritt.

## UI-Block abgenommen (2026-09-11) — ab jetzt abgeschlossener Referenzstand

Marco hat den UI-Modernisierungsblock (1–4) abgenommen. Ab hier gilt der
aktuelle Stand von `src/ui/app.html` als abgeschlossen und wird nicht ohne
neuen, ausdrücklichen UI-Auftrag weiter verändert.

Zum UI-Block gehören ausschließlich:
- `src/ui/app.html` — die gesamte Modernisierung (Blöcke 1–4).
- `tests/test_ui_escaping.py` — Testharness-Ergänzung für `directorUpdateSteps`.
- `UI_MODERNIZATION_PLAN.md` — dieses Journal.

Ausdrücklich NICHT Teil des UI-Blocks (fremde WIP, von mir nicht inhaltlich
verändert):
- `retrodisc_launcher.py`, `src/models/director.py`, `src/services/director.py`,
  `src/services/timeline.py` — Editor-V1-/Pipeline-Vorarbeit.
- `tests/test_ui_smoke.py` — enthält sowohl eine fremde Vorab-Änderung
  (`timelineEditQueue`-await-Fix) als auch meine Block-3/4-Harness-Ergänzung
  (`renderFeedback`/`FEEDBACK_META`); beide bereits vor diesem Abnahme-Zeitpunkt
  vorhanden, hier nicht weiter angefasst.
- Alle untracked Dateien (`EDITOR_V1_STATUS.md`, `scripts/editor_acceptance.py`,
  `scripts/timeline_acceptance.py`, `src/services/editor_filters.py`,
  `src/services/pipeline/conversion_queue.py`, `tests/test_editor_v1.py`,
  `tests/test_timeline_music_regression.py`) — durchweg fremde Editor-V1-/
  Pipeline-Arbeit.

Nächster Schritt: separater Stabilitätsblock zu den 10 vorbestehenden
Testfehlern/Queue-Init-Timeouts, siehe eigenes Journal/Untersuchung dort —
bewusst getrennt von diesem UI-Journal, um die beiden Aufträge nicht zu
vermischen.
