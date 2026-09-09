#!/usr/bin/env python3
"""Reale Edge-Case-Pfade: Leerzeichen, Umlaut, ß, Emoji, Klammern, Apostroph (Mission 10).

Erzeugt ein Video mit pathologischem Dateinamen und fährt Restoration-Render und
Short-Render real durch FFmpeg. Keine shell=True-Konstruktionen im Code.
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
from src.models.director import MediaAsset
from src.models.smart_edit import SmartEditProject, SilenceSettings
from src.services.restoration import Restoration
from src.services.smart_edit import SmartEditor

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
NAME = "Te st (ä ö ü ß 🎬) 'quote' [v1].mp4"


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
            width=v.width if v else None, height=v.height if v else None, title=path.stem)


def decodes_fully(path):
    r = subprocess.run([FFMPEG, "-hide_banner", "-v", "error", "-xerror", "-i", str(path), "-f", "null", "-"],
                       capture_output=True)
    return r.returncode == 0 and not r.stderr.strip()


async def main():
    if not FFMPEG:
        print("SKIP: ffmpeg fehlt"); return 0
    base = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/retrodisc-edge")
    base.mkdir(parents=True, exist_ok=True)
    src = base / NAME
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                    "-i", "testsrc2=s=640x480:r=25", "-f", "lavfi", "-i", "sine=frequency=300:sample_rate=48000",
                    "-t", "6", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "22", "-c:a", "aac",
                    "-shortest", "-y", str(src)], check=True)
    print(f"# Edge-Case-Pfad: {NAME}")
    print(f"  Quelle decode_ok={decodes_fully(src)}")

    ffmpeg = FFmpeg()
    library = ProbeLibrary(base / "library.db", ffmpeg)

    # Restoration
    rest = Restoration(library, ffmpeg, base / "out", base / "temp")
    plan = await rest.analyze(src)
    plan.options.size = "720p"
    plan = await rest.render(plan, preview=False)
    rest_out = Path(plan.outputs[-1])

    # Short
    editor = SmartEditor(library, ffmpeg, base / "out", base / "temp")
    asset = await library.asset(src)
    project = SmartEditProject(source_assets=[asset], target_duration=5.0, aspect_ratio="9:16",
                               silence=SilenceSettings(preset="off"))
    short = await editor.render_short(project)
    short_out = Path(short.outputs[-1])

    result = {
        "restoration_output": rest_out.name,
        "restoration_decodes": decodes_fully(rest_out),
        "short_output": short_out.name,
        "short_decodes": decodes_fully(short_out),
        "short_resolution": short.report["result"]["resolution"],
    }
    print("\n" + json.dumps(result, ensure_ascii=False, indent=2))
    ok = result["restoration_decodes"] and result["short_decodes"] and result["short_resolution"] == [1080, 1920]
    print("\nGESAMT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
