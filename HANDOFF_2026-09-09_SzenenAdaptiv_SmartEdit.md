# Übergabe an Codex — 2026-09-09

Fortsetzung des unterbrochenen Stands (szenenadaptive Restauration) plus neuer
Smart-Edit/Short-Kern. **Keine Commits, kein Push, keine neuen Branches.**
Bestehende Codex-Arbeit wurde nicht verworfen oder refactored.

Kanonischer Worktree: `/Users/marco/Projects/RetroDisc-download-paths`
Branch: `codex/retrodisc-download-paths` (unverändert gegenüber Remote).

---

## TL;DR — was jetzt fertig und belegt ist

| Bereich | Status | Beleg |
|---|---|---|
| Szenenadaptiver Render (M1/M2) | **fertig, real belegt** | `scripts/restoration_acceptance.py` |
| RestorationReport (M3) | **neu strukturiert** | `Restoration.build_report` + Test |
| Archivmaster + Manifest (M4/M5) | vorhanden, real belegt | Acceptance |
| Stabilisierung none/basic/advanced (M6) | vorhanden | `capabilities()` (basic=deshake) |
| Batch (M7) | **neu** | `Restoration.batch` + Launcher + Test |
| Vorher/Nachher (M8) | vorhanden | `render(preview=True)` + Stale-Schutz |
| Smart-Edit-Modelle (M9/M22) | **neu** | `src/models/smart_edit.py` |
| Short-Workflow (M10) | **neu, real belegt** | `scripts/smart_edit_acceptance.py` |
| Highlight-Finder LLM+Fallback (M11) | **neu** | `Director.select_time_ranges` + Fallback |
| Sprechpausen kürzen (M12) | **neu, real belegt** | `plan_silence_segments` + silencedetect |
| Fülllaute (M13) | **neu** | `strip_fillers` (nur eindeutige Laute) |
| Smart Reframe V1 (M14) | **neu, real belegt** | `reframe_filter` (Center-Crop) |
| SubjectTracker (M15) | **Architektur** | `subject_tracker_capability` = unavailable |
| Captions ASS (M16) | **neu, unit-getestet** | `build_ass`; Burn libass-gated |
| Voice Enhance (M17) | **neu, real belegt** | `voice_enhance_af` |
| Auto Ducking (M18) | Modellfeld; Director-Ducking bleibt | `audio_mode` keep/duck/mute |
| Social Export (M19) | **neu** | `_SOCIAL_PROFILES` + `export_preset` |

---

## Geänderte / neue Dateien

**Restauration**
- `src/services/restoration.py` — neu: `build_report` (M3), `collect_sources`,
  `batch` (M7). Der Report-Aufruf in `render()` zeigt jetzt auf `build_report`.
  Die bestehende `filters()` wendet Szenen-Overrides bereits per `enable`-
  Zeitfenster an (kein cut+concat nötig — ein Graph, disjunkte Zeitfenster).
- `retrodisc_launcher.py` — Bridge `restoration_batch` + Api-Proxy.
- `tests/test_restoration.py` — 3 neue Tests (jetzt 24 PASS).
- `scripts/restoration_acceptance.py` — realer End-to-End-Nachweis.

**Smart Edit**
- `src/models/smart_edit.py` — **neu**, alle Modelle.
- `src/services/smart_edit.py` — **neu angehängt**: `SmartEditor` + reine Helfer
  (die alte `SmartEdit`-Highlight-Engine bleibt unangetastet).
- `src/services/director.py` — neu: `select_time_ranges` (M11).
- `src/services/assistant.py` — neu: `highlight_ranges` (Ollama-Transport, JSON-Schema).
- `retrodisc_launcher.py` — Bridge `smart_edit_short/_capabilities/_project` + Proxies.
- `tests/test_smart_edit.py` — **neu**, 19 PASS.
- `scripts/smart_edit_acceptance.py` — realer End-to-End-Nachweis.

---

## Reproduzieren (macOS, Homebrew ffmpeg 8.1.1)

Testumgebung ohne schwere ML-Pakete:
```bash
.venv-test/bin/python -m pytest tests/test_restoration.py tests/test_smart_edit.py -q
.venv-test/bin/python scripts/restoration_acceptance.py /tmp/retrodisc-accept   # GESAMT: PASS
.venv-test/bin/python scripts/smart_edit_acceptance.py /tmp/retrodisc-short     # GESAMT: PASS
.venv-test/bin/python scripts/verify_ui_bridge.py && node --check build/ui-audit/inline.js
```
Auf Windows gilt weiterhin der CLAUDE.md-Weg mit
`C:\Users\marco\.local\bin\python3.11.exe` und `set PYTHONPATH=.venv\Lib\site-packages`.

---

## Architektur-Kurznotizen (damit nichts doppelt gebaut wird)

- **Szenen-Overrides** werden im finalen Render über `enable='gte(t,s)*lt(t,e)'`
  je `hqdn3d`/`unsharp` angewendet — ein einziger Filtergraph, disjunkte
  Zeitfenster. Kein separates Schneiden/Concat.
- **Short-Schnitt** nutzt einen `-filter_complex` mit
  `select/aselect` + `setpts=N/FRAME_RATE/TB` / `asetpts=N/SR/TB`. A/V bleiben
  synchron, Segmente werden in Quell-Zeitreihenfolge aneinandergehängt.
- **Reihenfolge im Short:** explizite `cuts` > `highlight_selection` >
  LLM/Fallback; danach werden qualifizierende Sprechpausen *innerhalb* der
  Keep-Segmente getrimmt. Captions werden auf die geschnittene Timeline
  umgerechnet (`retime_segments`), Captions in geschnittenen Bereichen entfallen.
- **LLM offline/ungültig ist kein Blocker:** `SmartEditor.select_highlights`
  fängt jeden Fehler und nutzt den deterministischen `highlight_fallback`.
  Alle LLM-Zeiten laufen durch `validate_ranges` (Clamping, nichts außerhalb der
  Mediendauer).

---

## Echte offene Punkte (bewusst NICHT gefälscht)

1. **Captions-Burn** braucht ein libass-fähiges ffmpeg. Der Homebrew-Build hier
   ist ohne libass (`ffmpeg -buildconf` → kein `--enable-libass`), daher kein
   `subtitles`-Filter; der Short-Lauf hat Captions korrekt übersprungen. Auf dem
   Windows-Vendor (gyan.dev) den Burn-Pfad praktisch prüfen. Optionaler Fallback
   via `drawtext` (libfreetype) wäre möglich, ist aber bewusst nicht gebaut.
2. **UI-Panels** in `src/ui/app.html` für „Batch-Restaurieren" und
   „Short erstellen" fehlen noch (Missionen 20/21 UI-Seite). Bridge/Api sind
   fertig und vom `verify_ui_bridge`-Gate abgedeckt.
3. **LLM-Highlight** gegen ein laufendes Ollama noch nicht praktisch gefahren
   (nur Transport + Validierung + Fallback vorhanden/getestet).
4. **Windows-Praxistest**, **libvidstab** (advanced), optionale KI-/RF-Provider —
   unverändert offen.

## Bekannte, NICHT von dieser Arbeit verursachte Testfehler (Teil 1)
`pytest -q` Teil 1: 470 passed / 17 skipped / **4 failed** (umgebungs-/plattformbedingt).
In Teil 2 (unten) geklärt und bis auf einen behoben/geguardet.

---

# Übergabe Teil 2 — UI, Ollama-Realtest, Testklärung (2026-09-09)

Alle offenen Punkte aus Teil 1 abgearbeitet. Stand jetzt: `pytest -q` =
**476 passed / 19 skipped / 1 failed** (der eine Fehler = Packaging-Guard für die
schwere ML-Runtime `faster-whisper`, im schlanken macOS-Dev-venv nicht installiert).

## Neu/geändert in Teil 2
- `src/ui/app.html` — Panel `tab-short` (Short/Smart-Edit), Archiv- und Batch-
  Sektion im Restore-Panel, Toolbar-Buttons Short+Restaurieren, gruppierte
  Startseite (Erstellen/Retten/Werkzeuge), Handoffs, Caption-Capability-Gating,
  Job-Event-Anzeige für `smart_edit`/Batch/Archiv.
- `retrodisc_launcher.py` — `restoration_archive`-Bridge + Proxy; `smart_edit_short`
  nutzt jetzt `JobType.SMART_EDIT`; `_on_complete` reicht `archive`/`batch_summary`
  im `job_done`-Event durch (Archivmaster NICHT in Recent Media).
- `src/services/assistant.py` / `director.py` — bereits in Teil 1; in Teil 2 real
  gegen Ollama gefahren.
- `tests/test_smart_edit.py` — Caption-Capability-Test (beide Zustände).
- `tests/test_drive_detection_ui.py` — Harness-Lücke behoben (siehe unten).
- `tests/test_installer.py` — 2 Windows-only-Tests mit `skipif(win32)` konsistent
  zum vorhandenen Schwestertest.
- `scripts/ollama_highlight_realtest.py` — neuer Realtest (online + offline).

## Reproduzieren (Teil 2)
```bash
.venv-test/bin/python scripts/ollama_highlight_realtest.py /tmp/rd-ollama   # GESAMT PASS (falls Ollama läuft)
.venv-test/bin/python -m pytest tests/test_drive_detection_ui.py tests/test_installer.py -q
.venv-test/bin/python scripts/verify_ui_bridge.py && node --check build/ui-audit/inline.js
```

## Testklärung (jeder frühere Fehler)
- **drive_detection_ui** → BEHOBEN. Test-Harness rief `refreshQueue` (nutzt
  `finalOutputPaths`) ohne diese Funktion im Node-Stub → ReferenceError vom
  eigenen `catch{}` verschluckt. UI-Verhalten war korrekt. Fix nur im Harness
  (fehlende Helfer ergänzt), kein künstlicher Skip.
- **installer (2×)** → echt Windows-only (`os.path.expandvars('%APPDATA%')` nur
  unter Windows). `skipif(win32)` ergänzt, identisch zum vorhandenen Schwestertest.
- **whisper** → Packaging-Guard, braucht `faster-whisper`+`requests`. Im
  Windows-Build-venv importierbar. Bewusst NICHT geskippt.

## Echte offene Punkte (Stand Teil 2)
1. Caption-Burn praktisch auf libass-fähigem (Windows-)ffmpeg verifizieren.
2. Echter Klick-Durchlauf der Handoffs in der laufenden WebView (Bridge-Ebene fertig).
3. Windows-Praxistest, libvidstab (advanced), optionale KI-/RF-Provider.

---

# Übergabe Teil 3 — Produktionsreife (2026-09-09)

`pytest -q` = **480 passed / 19 skipped / 0 failed**. Alle 6 realen
Acceptance-Skripte GESAMT PASS.

## Neu/geändert in Teil 3
- `.venv-test`: vorgesehene Pflicht-Dependency `faster-whisper`+`requests` installiert
  (kein alternatives ASR). Packaging-Guard-Test grün.
- `retrodisc_final.spec`: `collect_submodules("src")` ergänzt → bündelt alle 40
  src-Submodule (viele Launcher-Imports sind lazy und fehlten in `hiddenimports`).
- `retrodisc_launcher.py`: `diagnostics()`-Bridge + Proxy (Capability-Dashboard).
- `src/ui/app.html`: Diagnose-Panel in Einstellungen (`loadDiagnostics`).
- Tests neu: `tests/test_ui_smoke.py`, `tests/test_diagnostics.py`, Caption-Capability.
- Realtest-Skripte: `scripts/whisper_asr_realtest.py`, `scripts/dubbing_realtest.py`,
  `scripts/edgecase_paths_realtest.py`.

## Reproduzieren (Teil 3)
```bash
.venv-test/bin/python scripts/whisper_asr_realtest.py /tmp/asr        # GESAMT PASS (lädt tiny einmalig)
.venv-test/bin/python scripts/dubbing_realtest.py /tmp/dub            # GESAMT PASS (Ollama nötig)
.venv-test/bin/python scripts/edgecase_paths_realtest.py /tmp/edge    # GESAMT PASS
.venv-test/bin/python -m pytest tests/test_ui_smoke.py tests/test_diagnostics.py -q
```

## Acceptance-Matrix (real, `-xerror`-Volldecode)
RESTORATION PASS · ARCHIVE PASS · SMART EDIT PASS · SHORT PASS ·
TRANSCRIPTION PASS · DUBBING PASS · SUBTITLES(SRT) PASS · HIGHLIGHTS(Ollama) PASS ·
EDGE-CASE-PFADE PASS · CAPABILITY-DASHBOARD PASS. MAC/WINDOWS-PACKAGE = nur Static
(kein Build-Rechner hier; Spec Windows-only).

## Echte offene Punkte (Stand Teil 3)
1. Caption-Burn praktisch auf libass-fähigem (Windows-)ffmpeg.
2. Echter macOS/Windows-Paket-Build auf dem Build-Rechner (`collect_submodules`-Fix greift dort).
3. Klick-Durchlauf in laufender WebView; libvidstab (advanced); optionale KI-/RF-Provider.
