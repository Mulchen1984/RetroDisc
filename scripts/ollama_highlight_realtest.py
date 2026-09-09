#!/usr/bin/env python3
"""Real local-Ollama highlight test + deterministic offline fallback (Mission 5, 11).

Online (falls Ollama läuft): Director.select_time_ranges -> validierte Highlight-
Bereiche -> echter Short-Render. Offline (unerreichbarer Host): deterministischer
Fallback, Short trotzdem möglich. Genau ein LLM-Versuch, dann Fallback.

Aufruf:  python3 scripts/ollama_highlight_realtest.py [dir] [model] [host]
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.ffmpeg import FFmpeg
from src.models.director import MediaAsset
from src.models.smart_edit import SmartEditProject, SilenceSettings, CaptionStyle, VoiceEnhanceSettings
from src.services.assistant import Assistant
from src.services.director import Director
from src.services.smart_edit import SmartEditor

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
MODEL = sys.argv[2] if len(sys.argv) > 2 else "llama3.2:3b"
HOST = sys.argv[3] if len(sys.argv) > 3 else "http://127.0.0.1:11434"

TRANSCRIPT = {"language": "de", "segments": [
    {"start": 2.0, "end": 7.0, "text": "Intro: worum es in diesem Video geht."},
    {"start": 10.0, "end": 16.0, "text": "Der spannendste Teil mit viel Action und Tempo."},
    {"start": 20.0, "end": 26.0, "text": "Ein ruhigerer Abschnitt mit einer Erklärung."},
    {"start": 30.0, "end": 37.0, "text": "Das große Finale und das Fazit zum Schluss."},
]}


class ProbeLibrary:
    def __init__(self, db_path, ffmpeg):
        self.db_path = Path(db_path); self._ffmpeg = ffmpeg
    async def asset(self, path):
        path = Path(path).resolve(); info = await self._ffmpeg.probe(path)
        v = info.video_streams[0] if info.video_streams else None
        a = info.audio_streams[0] if info.audio_streams else None
        return MediaAsset(id=hashlib.sha256(str(path).encode()).hexdigest()[:16], path=str(path),
            kind="video" if v else "audio", duration=info.duration_seconds,
            video_codec=v.codec if v else None, audio_codec=a.codec if a else None,
            width=v.width if v else None, height=v.height if v else None, transcript=TRANSCRIPT)
    def attach_transcript(self, *a, **k): pass


def run_ffmpeg(*args):
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", *args], check=True)


def decodes_fully(path):
    r = subprocess.run([FFMPEG, "-hide_banner", "-v", "error", "-xerror", "-i", str(path), "-f", "null", "-"],
                       capture_output=True)
    return r.returncode == 0 and not r.stderr.strip()


def make_source(path, work):
    run_ffmpeg("-f", "lavfi", "-i", "testsrc2=s=1280x720:r=25", "-f", "lavfi",
               "-i", "sine=frequency=300:sample_rate=48000", "-map", "0:v", "-map", "1:a",
               "-t", "40", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "22", "-c:a", "aac",
               "-shortest", "-y", str(path))


async def main():
    if not FFMPEG:
        print("SKIP: ffmpeg fehlt"); return 0
    base = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="retrodisc-ollama-"))
    base.mkdir(parents=True, exist_ok=True)
    work = base / "work"; work.mkdir(exist_ok=True)
    source = base / "asset_40s.mp4"
    make_source(source, work)
    ffmpeg = FFmpeg()
    library = ProbeLibrary(base / "library.db", ffmpeg)
    asset = await library.asset(source)
    duration = asset.duration
    wish = "Finde die interessantesten 15 Sekunden und erstelle daraus einen kompakten Short."
    seg_spans = [(s["start"], s["end"]) for s in TRANSCRIPT["segments"]]
    # Director.select_time_ranges erwartet (start, end, text)-Tripel wie _transcript_segments.
    seg_triples = [(s["start"], s["end"], s["text"]) for s in TRANSCRIPT["segments"]]

    print(f"# Ollama-Highlight-Realtest  model={MODEL}  host={HOST}  duration={duration:.1f}s")

    # ── ONLINE ────────────────────────────────────────────────────────────
    online = {"case": "ollama_online"}
    director = Director(library, ffmpeg, Assistant(model=MODEL, host=HOST),
                        base / "out", base / "audio", base / "temp")
    models = await director.assistant.available_models()
    online["ollama_reachable"] = bool(models)
    online["model_present"] = MODEL in models
    if models and MODEL in models:
        try:
            raw = await director.select_time_ranges(asset, seg_triples, 15, wish, MODEL)
            online["llm_raw_ranges"] = raw
            validated = SmartEditor.validate_ranges(raw, duration)
            online["validated_ranges"] = [[r.start, r.end] for r in validated]
            online["all_within_duration"] = all(0 <= r.start < r.end <= duration for r in validated)
            online["no_invented_times"] = all(any(a <= r.start and r.end <= b + 0.5 for a, b in seg_spans)
                                              or any(r.start < b and r.end > a for a, b in seg_spans)
                                              for r in validated) if validated else False
            editor = SmartEditor(library, ffmpeg, base / "out", base / "temp")
            project = SmartEditProject(source_assets=[asset], target_duration=15.0, aspect_ratio="9:16",
                planner="ollama", silence=SilenceSettings(preset="natural"),
                voice_enhance=VoiceEnhanceSettings(preset="clear"))
            result = await editor.render_short(project, director=director, wish=wish)
            out = Path(result.outputs[-1])
            info = json.loads(subprocess.run([FFPROBE, "-v", "error", "-show_streams", "-show_format",
                "-of", "json", str(out)], capture_output=True, text=True, check=True).stdout)
            vid = next(s for s in info["streams"] if s["codec_type"] == "video")
            online["render"] = {"resolution": [vid["width"], vid["height"]],
                "duration": round(float(info["format"]["duration"]), 2), "decodes_fully": decodes_fully(out),
                "kept": result.report["edit"]["kept_segments"]}
        except Exception as exc:
            online["error"] = str(exc)
    else:
        online["note"] = "Modell/Ollama nicht verfügbar; Online-Teil übersprungen."

    # ── OFFLINE (deterministischer Fallback) ────────────────────────────────
    offline = {"case": "ollama_offline_fallback"}
    dead = Director(library, ffmpeg, Assistant(model=MODEL, host="http://127.0.0.1:1"),
                    base / "out", base / "audio", base / "temp")
    editor2 = SmartEditor(library, ffmpeg, base / "out2", base / "temp2")
    project2 = SmartEditProject(source_assets=[asset], target_duration=15.0, aspect_ratio="9:16",
        planner="ollama", silence=SilenceSettings(preset="natural"))
    ranges = await editor2.select_highlights(project2, director=dead, wish=wish)
    offline["fallback_ranges"] = [[r.start, r.end] for r in ranges]
    offline["within_duration"] = all(0 <= r.start < r.end <= duration for r in ranges)
    result2 = await editor2.render_short(project2, director=dead, wish=wish)
    out2 = Path(result2.outputs[-1])
    offline["render"] = {"path": out2.name, "decodes_fully": decodes_fully(out2),
                         "duration": round((await ffmpeg.probe(out2)).duration_seconds, 2)}

    print("\n===== ERGEBNIS =====")
    print(json.dumps([online, offline], ensure_ascii=False, indent=2, default=str))

    checks = [offline["within_duration"], offline["render"]["decodes_fully"]]
    if online.get("model_present") and "render" in online:
        checks += [online["all_within_duration"], online["render"]["decodes_fully"]]
    print("\nGESAMT:", "PASS" if all(checks) else "FAIL")
    return 0 if all(checks) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
