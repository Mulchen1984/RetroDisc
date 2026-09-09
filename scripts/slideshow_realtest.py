#!/usr/bin/env python3
"""Echte Slideshow: 3 Bilder + Musik -> Crossfade/Zoom -> H.264/AAC (Missionen 6-11).

Bilder als image-Assets, Ken-Burns-Zoom, Fade-Transition, echte Musikspur (mp3)
gemischt via Director.render. Prüft H.264/AAC, Dauer, Video+Audio, Volldecode.

Aufruf:  python3 scripts/slideshow_realtest.py [dir]
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
from src.models.director import MediaAsset, ProductionProject, Scene, AudioPlacement
from src.services.assistant import Assistant
from src.services.director import Director

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac"}


class ImageAwareLibrary:
    """Classifies assets by extension so images become kind='image' (Mission 6)."""
    def __init__(self, db_path, ffmpeg):
        self.db_path = Path(db_path); self._ffmpeg = ffmpeg
    async def asset(self, path):
        path = Path(path).resolve(); ext = path.suffix.lower()
        info = await self._ffmpeg.probe(path)
        v = info.video_streams[0] if info.video_streams else None
        a = info.audio_streams[0] if info.audio_streams else None
        kind = "image" if ext in IMAGE_EXTS else "audio" if ext in AUDIO_EXTS else "video"
        return MediaAsset(id=hashlib.sha256(str(path).encode()).hexdigest()[:16], path=str(path),
            kind=kind, duration=info.duration_seconds if kind != "image" else 0,
            video_codec=v.codec if v else None, audio_codec=a.codec if a and kind != "image" else None,
            width=v.width if v else None, height=v.height if v else None, title=path.stem)
    def attach_transcript(self, *a, **k): pass


def run_ffmpeg(*a):
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", *a], check=True)


def decodes_fully(path):
    r = subprocess.run([FFMPEG, "-hide_banner", "-v", "error", "-xerror", "-i", str(path), "-f", "null", "-"],
                       capture_output=True)
    return r.returncode == 0 and not r.stderr.strip()


async def main():
    if not FFMPEG:
        print("SKIP: ffmpeg fehlt"); return 0
    base = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/retrodisc-slideshow")
    base.mkdir(parents=True, exist_ok=True)
    # 3 visuell verschiedene Bilder (png/jpg/png) + Musik (mp3)
    imgs = []
    for i, src in enumerate(["color=c=crimson:s=1280x720", "testsrc2=s=1280x720", "mandelbrot=s=1280x720"]):
        ext = ".jpg" if i == 1 else ".png"
        p = base / f"img{i}{ext}"
        run_ffmpeg("-f", "lavfi", "-i", src, "-frames:v", "1", "-y", str(p))
        imgs.append(p)
    music = base / "music.mp3"
    run_ffmpeg("-f", "lavfi", "-i", "sine=frequency=330:sample_rate=44100", "-t", "12",
               "-c:a", "libmp3lame", "-b:a", "192k", "-y", str(music))
    print(f"# Slideshow-Realtest  Bilder={[p.name for p in imgs]}  Musik={music.name}")

    ffmpeg = FFmpeg()
    library = ImageAwareLibrary(base / "library.db", ffmpeg)
    image_assets = [await library.asset(p) for p in imgs]
    music_asset = await library.asset(music)
    director = Director(library, ffmpeg, Assistant(), base / "out", base / "audio", base / "temp")

    per = 3.0
    total = per * len(image_assets)
    project = ProductionProject(prompt="Slideshow", title="Foto-Slideshow", target_duration=total,
        assets=image_assets + [music_asset],
        timeline=[Scene(asset_id=a.id, start=0, end=per, position=i * per,
                        transition="fade", zoom="subtle") for i, a in enumerate(image_assets)],
        original_audio="mute",  # Bilder haben keinen Originalton
        music=[AudioPlacement(asset_id=music_asset.id, position=0, start=0, duration=total,
                              volume=0.4, fade_in=0.5, fade_out=1.0, duck=False)])

    out = Path(await director.render(project))
    info = json.loads(subprocess.run([FFPROBE, "-v", "error", "-show_streams", "-show_format",
        "-of", "json", str(out)], capture_output=True, text=True, check=True).stdout)
    vid = next(s for s in info["streams"] if s["codec_type"] == "video")
    aud = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    result = {
        "images": len(image_assets),
        "expected_duration": total,
        "actual_duration": round(float(info["format"]["duration"]), 2),
        "video_codec": vid["codec_name"],
        "audio_codec": aud["codec_name"] if aud else None,
        "resolution": [vid["width"], vid["height"]],
        "decodes_fully": decodes_fully(out),
        "output": out.name,
    }
    print("\n" + json.dumps(result, ensure_ascii=False, indent=2))
    ok = (result["video_codec"] == "h264" and result["audio_codec"] == "aac"
          and abs(result["actual_duration"] - total) < 0.6 and result["decodes_fully"])
    print("\nGESAMT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
