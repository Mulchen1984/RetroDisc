"""Real local end-to-end smoke checks for RetroDisc media workflows."""
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path

from src.core.disc import DiscTools
from src.core.ffmpeg import FFmpeg
from src.models.media import HighlightConfig
from src.services.dvd_workflow import DVDProject, DVDWorkflow
from src.services.smart_edit import SmartEdit
from src.services.subtitle import SubtitleGenerator
from src.services.upscaler import VideoUpscaler

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "test_video.mp4"
SPEECH_FIXTURE = ROOT / "tests" / "fixtures" / "spoken_de.wav"
FFMPEG = ROOT / "vendor" / "ffmpeg.exe"
FFPROBE = ROOT / "vendor" / "ffprobe.exe"
DVDTOOLS = ROOT / "vendor" / "dvdtools"


async def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=False)
    ffmpeg = FFmpeg(ffmpeg_path=str(FFMPEG), ffprobe_path=str(FFPROBE))

    trim_a = await ffmpeg.trim(FIXTURE, out / "trim-a.mp4", 0, 3)
    trim_b = await ffmpeg.trim(FIXTURE, out / "trim-b.mp4", 3, 6)
    merged = await ffmpeg.merge([trim_a, trim_b], out / "merged.mp4")

    upscaler = VideoUpscaler(ffmpeg_path=str(FFMPEG))
    upscaled = await upscaler.upscale(FIXTURE, out / "upscaled-2x.mp4", scale=2)
    interpolated = await upscaler.interpolate(FIXTURE, out / "interpolated-50fps.mp4", target_fps=50)

    smart = SmartEdit(ffmpeg=ffmpeg)
    highlights = await smart.create_highlights(
        FIXTURE,
        out / "highlights.mp4",
        HighlightConfig(target_duration_seconds=6, min_clip_duration=2, max_clip_duration=6),
    )

    subtitles = await SubtitleGenerator(model="base", device="cpu").generate(
        SPEECH_FIXTURE, out / "spoken-test.srt", language="de", format="srt"
    )

    disc = DiscTools(
        dvdauthor_path=str(DVDTOOLS / "dvdauthor.exe"),
        mkisofs_path=str(DVDTOOLS / "mkisofs.exe"),
        growisofs_path=str(DVDTOOLS / "growisofs.exe"),
    )
    dvd = DVDWorkflow(ffmpeg=ffmpeg, disc_tools=disc, temp_dir=out / "dvd-temp")
    iso = await dvd.run(DVDProject(
        title="RetroDisc Smoke",
        input_files=[FIXTURE],
        output_dir=out,
        standard="PAL",
        aspect="16:9",
        only_iso=True,
    ))

    outputs = [trim_a, trim_b, merged, upscaled, interpolated, highlights, subtitles, iso]
    result = {}
    for path in outputs:
        if not path.is_file():
            raise RuntimeError(f"Missing output: {path}")
        result[path.name] = path.stat().st_size
    subtitle_text = subtitles.read_text(encoding="utf-8")
    if not subtitle_text.strip() or "-->" not in subtitle_text:
        raise RuntimeError(f"Whisper produced no timed subtitle segment: {subtitles}")

    probes = {}
    for path in [merged, upscaled, interpolated, highlights]:
        media = await ffmpeg.probe(path)
        probes[path.name] = {
            "duration": media.duration_seconds,
            "width": media.video_streams[0].width if media.video_streams else None,
            "height": media.video_streams[0].height if media.video_streams else None,
            "fps": media.video_streams[0].fps if media.video_streams else None,
        }
    print(json.dumps({"output_dir": str(out), "files": result, "probes": probes}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Echte lokale RetroDisc-End-to-End-Smokes")
    parser.add_argument(
        "--output",
        type=Path,
        help="Neuer, noch nicht existierender Ausgabeordner (Standard: Zeitstempel unter build)",
    )
    args = parser.parse_args()
    output = args.output or (
        ROOT / "build" / f"e2e-smoke-{datetime.now():%Y%m%d-%H%M%S}"
    )
    asyncio.run(main(output.resolve()))
