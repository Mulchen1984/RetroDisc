# Editor V1 — 2026-09-09

Gemeinsamer Windows/macOS-Code auf ProductionProject, Scene, Director und TimelineHistory.
Keine zweite Timeline, kein neues Framework, keine Dependency installiert.
Claudes Waveform-/Disc-Erweiterungen bleiben erhalten.

## Fertiger Funktionsblock

- Strukturierte Transition (Typ/Dauer/lineares Easing), alte Projektstrings bleiben ladbar.
  Cut, Dissolve/Fade, Fade from/to Black, Dip to Black, Wipe L/R, Slide L/R,
  Zoom und Blur Dissolve. Überlappende Übergänge reduzieren Video/Audio identisch;
  zu kurze Clips/zu lange Übergänge werden vor Rendern zurückgewiesen.
- 0.25–4× Tempo mit verketteten atempo-Filtern. Split/Trim berücksichtigen Tempo.
- Standbild am Quellzeitpunkt einfügen; Audio dabei still. Standbilder werden nicht
  erneut geteilt/beschleunigt; dazu vorerst entfernen und neu einfügen.
- Clip-Lautstärke/Mute/Fades, Sichtbarkeit (schwarz bei verstecktem Hauptvideo),
  Lock einschließlich Schutz gegen indirekte Positionsänderung.
- PNG/JPG/WebP-Overlay und Video-PIP teilen denselben Compositor. Position, Größe,
  Deckkraft, PIP-Lautstärke, Sichtbarkeit/Lock und Entfernen; transparente PNGs.
- Texttrack mit Inhalt, Zeiten, Position/Ausrichtung, Größe, Deckkraft und Fades;
  Title/Subtitle/Lower Third/Caption/Credits als Parameter-Presets. Renderer nutzt
  drawtext/textfile (Text wird nicht als Filtercode interpoliert).
- Nicht destruktive Basisparameter: Helligkeit/Kontrast/Sättigung/Wärme,
  Schärfe/Blur/Vignette/Graustufen/Sepia; sieben Look-Presets. Crop, Rotation, Flip.
- Smart Suggestions sind explizite Vorschläge aus Cliplänge/Bild-Assets, keine
  behauptete Action-/Gesichts-/Motiverkennung; Anwendung ist rückgängig machbar.
- Bestehende JSON-Persistenz speichert sämtliche Felder. UI-Edits und Undo/Redo
  werden serialisiert, damit parallele Bridge-Antworten nichts überschreiben.
- Absolute Voiceover/Musik/Text/Overlay-Positionen werden nicht heimlich verändert:
  bei Verkürzung über die Trackgrenzen hinaus ist eine Anpassung nötig.

## Reale Belege

`scripts/editor_acceptance.py` erzeugt lokale Quellen (320×240/25fps und
480×270/30fps), transparentes PNG und prüft den echten Director-Renderer.
17 Renderfälle: acht Cross-Transition-Varianten, PNG-Overlay, PIP mit Audio,
Speed+Freeze, 2×/4×, lokale Schwarzblenden und Effects+Transform.
Jeweils FFprobe, erwartete Dauer/Audio, vollständiger Decode, Recent Media und
unveränderte Quell-SHA256. Zusätzlich aktiven Render abgebrochen, Temp/Outputs
bereinigt. Keine manuelle visuelle Qualitätsbehauptung.

Artefaktgebundene Checksummen und Ergebnisse:
`build/editor-acceptance/result.json` (17 SHA-256-Werte). Logs unter
`build/macos-release/editor-acceptance.log`.

Text ist auf dem lokalen FFmpeg ohne drawtext korrekt CAPABILITY_UNAVAILABLE;
der positive Text-/Font-Render sowie Titel-Kombinationen B/E bleiben ungetestet.
Keine alternativen Fonts/Renderer installiert, kein Erfolg vorgetäuscht.

## Echte Restpunkte

- Text-Positive-Acceptance auf FFmpeg mit drawtext/Fonts; echter Windows-Render.
- Projektauflösung/FPS/Samplerate und neuer Exportdialog: Director weiterhin
  bestehendes 720p30/48kHz-Ziel, Hardware/CPU über bestehenden Converter.
- Kurze Editor-Vorschau/Preview-Player; aktuell finale Renderprüfung statt Proxy.
- Overlay-Rotation/Border, Solo, Pan/Normalisierung, Ducking Attack/Release,
  VHS-Preset und erweiterte Effekt-Einzelregler noch nicht in der einfachen UI.
- Kein nonlineares Transition-Easing, keine Beat-/Gesichtserkennung.

Keine Commits, kein Push, kein neuer Branch durch Codex.

Tests: 597 passed, 19 skipped in 14.91s; 0 failed. Bridge 0 findings, JS-Syntax, compileall und git diff --check PASS.
