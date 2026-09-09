#!/usr/bin/env python3
"""Echter Timeline-Render: 2 Videos -> Trim/Split/Move (+Undo/Redo) -> Render (Mission 3).

Baut einen ProductionProject aus zwei lokalen Videos, editiert die Timeline über
TimelineHistory (inkl. Undo/Redo) und rendert real via Director.render. Prüft
Reihenfolge/Dauer/Streams und vollständigen Decode.

Aufruf:  python3 scripts/timeline_render_realtest.py [dir]
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.ffmpeg import FFmpeg
from src.models.director import MediaAsset, ProductionProject, Scene
from src.services.assistant import Assistant
from src.services.director import Director
from src.services.timeline import TimelineHistory

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")


class MemoryLibrary:
    def __init__(self, db_path, ffmpeg):
        self.db_path = Path(db_path); self._ffmpeg = ffmpeg
    async def asset(self, path):
        path = Path(path).resolve(); info = await self._ffmpeg.probe(path)
        v = info.video_streams[0] if info.video_streams else None
        a = info.audio_streams[0] if info.audio_streams else None
        return MediaAsset(id=hashlib.sha256(str(path).encode()).hexdigest()[:16], path=str(path),
            kind="video" if v else "audio", duration=info.duration_seconds,
            video_codec=v.codec if v else None, audio_codec=a.codec if a else None,
            width=v.width if v else None, height=v.height if v else None, title=path.stem)
    def attach_transcript(self, *a, **k): pass


def run_ffmpeg(*a):
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", *a], check=True)


def decodes_fully(path):
    r = subprocess.run([FFMPEG, "-hide_banner", "-v", "error", "-xerror", "-i", str(path), "-f", "null", "-"],
                       capture_output=True)
    return r.returncode == 0 and not r.stderr.strip()


def make_clip(path, source, freq):
    run_ffmpeg("-f", "lavfi", "-i", f"{source}=s=640x480:r=25", "-f", "lavfi",
               "-i", f"sine=frequency={freq}:sample_rate=48000", "-map", "0:v", "-map", "1:a",
               "-t", "8", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "22", "-c:a", "aac",
               "-shortest", "-y", str(path))


async def main():
    if not FFMPEG:
        print("SKIP: ffmpeg fehlt"); return 0
    base = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/retrodisc-timeline")
    base.mkdir(parents=True, exist_ok=True)
    a_path = base / "clipA.mp4"; b_path = base / "clipB.mp4"
    make_clip(a_path, "testsrc2", 440); make_clip(b_path, "mandelbrot", 880)
    print("# Timeline-Render-Realtest  A=testsrc2 B=mandelbrot")

    ffmpeg = FFmpeg()
    library = MemoryLibrary(base / "library.db", ffmpeg)
    asset_a = await library.asset(a_path); asset_b = await library.asset(b_path)
    director = Director(library, ffmpeg, Assistant(), base / "out", base / "audio", base / "temp")

    project = ProductionProject(prompt="Timeline-Test", target_duration=16, assets=[asset_a, asset_b],
        timeline=[Scene(asset_id=asset_a.id, start=0, end=8, position=0),
                  Scene(asset_id=asset_b.id, start=0, end=8, position=8)])

    # Timeline editieren über die History (deckt Undo/Redo mit ab).
    h = TimelineHistory(project)
    h.apply("trim", 0, {"end": 4})           # A -> [0,4]
    h.apply("split", 1, {"time": 4})          # B -> [0,4] + [4,8]
    h.apply("move", 2, {"target": 0})         # letztes B-Stück nach vorne
    h.apply("delete", 1)                      # ein Stück löschen
    h.undo()                                  # delete rückgängig
    h.redo()                                  # delete wieder
    edited = h.current()

    expected = round(sum(s.end - s.start for s in edited.timeline), 2)
    order = [(s.asset_id[:4], s.start, s.end) for s in edited.timeline]
    print(f"  Editierte Timeline ({len(edited.timeline)} Clips), erwartete Dauer {expected}s")
    print(f"  Reihenfolge: {order}")

    out = Path(await director.render(edited))
    info = json.loads(subprocess.run([FFPROBE, "-v", "error", "-show_streams", "-show_format",
        "-of", "json", str(out)], capture_output=True, text=True, check=True).stdout)
    vid = next(s for s in info["streams"] if s["codec_type"] == "video")
    actual = round(float(info["format"]["duration"]), 2)

    result = {
        "clips": len(edited.timeline),
        "expected_duration": expected,
        "actual_duration": actual,
        "duration_ok": abs(actual - expected) < 0.6,
        "resolution": [vid["width"], vid["height"]],
        "has_video": True,
        "has_audio": any(s["codec_type"] == "audio" for s in info["streams"]),
        "decodes_fully": decodes_fully(out),
        "output": out.name,
    }
    print("\n" + json.dumps(result, ensure_ascii=False, indent=2))

    # ── Transition-Acceptance (Mission 4/5): fade + dip_black real rendern ──
    trans = ProductionProject(prompt="Transitions", target_duration=8, assets=[asset_a, asset_b],
        timeline=[Scene(asset_id=asset_a.id, start=0, end=4, position=0, transition="cut"),
                  Scene(asset_id=asset_b.id, start=0, end=4, position=4, transition="fade")])
    tout = Path(await director.render(trans))
    tinfo = json.loads(subprocess.run([FFPROBE, "-v", "error", "-show_format", "-of", "json", str(tout)],
        capture_output=True, text=True, check=True).stdout)
    dip = ProductionProject(prompt="Dip", target_duration=4, assets=[asset_a],
        timeline=[Scene(asset_id=asset_a.id, start=0, end=4, position=0, transition="dip_black")])
    dout = Path(await director.render(dip))
    transition_result = {
        "fade_duration": round(float(tinfo["format"]["duration"]), 2),
        "fade_decodes": decodes_fully(tout),
        "dip_black_decodes": decodes_fully(dout),
    }
    print("Transition-Acceptance: " + json.dumps(transition_result, ensure_ascii=False))

    ok = (result["duration_ok"] and result["has_audio"] and result["decodes_fully"] and result["clips"] >= 2
          and abs(transition_result["fade_duration"] - 8) < 0.6
          and transition_result["fade_decodes"] and transition_result["dip_black_decodes"])
    print("\nGESAMT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
