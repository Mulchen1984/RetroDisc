#!/usr/bin/env python3
"""Real-FFmpeg acceptance for the Smart-Edit / Short pipeline (Missionen 10–19, 25).

Erzeugt ein 20 s SD-Testvideo mit einer echten Sprechpause, hängt ein
synthetisches Transkript an und fährt render_short() ohne Mocks:

  Highlight-Fallback -> Sprechpausen kürzen -> Center-Reframe 9:16 ->
  Voice-Enhance -> moderne Captions -> H.264/AAC.

Prüft danach: Auflösung 1080x1920, Audio vorhanden, vollständiges Decoding,
plausible Dauer. Aufruf:  python3 scripts/smart_edit_acceptance.py [dir]
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
from src.models.smart_edit import CaptionStyle, SilenceSettings, SmartEditProject, VoiceEnhanceSettings
from src.services.smart_edit import SmartEditor

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")


class ProbeLibrary:
    def __init__(self, db_path, ffmpeg):
        self.db_path = Path(db_path)
        self._ffmpeg = ffmpeg

    async def asset(self, path):
        path = Path(path).resolve()
        info = await self._ffmpeg.probe(path)
        video = info.video_streams[0] if info.video_streams else None
        audio = info.audio_streams[0] if info.audio_streams else None
        return MediaAsset(id=hashlib.sha256(str(path).encode()).hexdigest()[:16], path=str(path),
            kind="video" if video else "audio", duration=info.duration_seconds,
            video_codec=video.codec if video else None, audio_codec=audio.codec if audio else None,
            width=video.width if video else None, height=video.height if video else None)


def run_ffmpeg(*args):
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", *args], check=True)


def decodes_fully(path):
    result = subprocess.run([FFMPEG, "-hide_banner", "-v", "error", "-xerror", "-i", str(path), "-f", "null", "-"],
                            capture_output=True)
    return result.returncode == 0 and not result.stderr.strip()


def make_source(path, work):
    """20 s, 1280x720, Ton mit deutlicher Pause 6–10 s (für silencedetect)."""
    speech = work / "speech.wav"
    # sine 0–6 s, Stille 6–10 s, sine 10–20 s
    run_ffmpeg("-f", "lavfi", "-i", "sine=frequency=280:sample_rate=48000", "-t", "6", "-y", str(work / "a.wav"))
    run_ffmpeg("-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", "4", "-y", str(work / "b.wav"))
    run_ffmpeg("-f", "lavfi", "-i", "sine=frequency=330:sample_rate=48000", "-t", "10", "-y", str(work / "c.wav"))
    lst = work / "al.txt"
    lst.write_text("".join(f"file '{(work / n).resolve()}'\n" for n in ("a.wav", "b.wav", "c.wav")), encoding="utf-8")
    run_ffmpeg("-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", "-y", str(speech))
    run_ffmpeg("-f", "lavfi", "-i", "testsrc2=s=1280x720:r=25", "-i", str(speech),
               "-map", "0:v", "-map", "1:a", "-t", "20", "-pix_fmt", "yuv420p",
               "-c:v", "libx264", "-crf", "20", "-c:a", "aac", "-shortest", "-y", str(path))


async def main():
    if not FFMPEG:
        print("SKIP: ffmpeg nicht gefunden"); return 0
    base = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="retrodisc-short-"))
    base.mkdir(parents=True, exist_ok=True)
    work = base / "work"; work.mkdir(exist_ok=True)
    source = base / "source_20s.mp4"
    print(f"# Smart-Edit-Acceptance  base={base}")
    make_source(source, work)
    print(f"  Quelle: {source.name}  decode_ok={decodes_fully(source)}")

    ffmpeg = FFmpeg()
    library = ProbeLibrary(base / "library.db", ffmpeg)
    editor = SmartEditor(library, ffmpeg, base / "out", base / "temp")
    caps = await editor.capabilities()
    print(f"  Capabilities: silence={caps['silence_detection']} captions={caps['captions']} "
          f"hw={caps['hardware_encode']}")

    src_asset = await library.asset(source)
    # Transkript: ein Satz vor, einer nach der Pause -> mind. einer überlebt den Schnitt.
    transcript = {"segments": [{"start": 2.0, "end": 4.5, "text": "erster gesprochener satz hier"},
                                {"start": 12.0, "end": 15.5, "text": "zweiter satz nach der pause im clip"}]}
    project_asset = src_asset.model_copy(update={"transcript": transcript})
    project = SmartEditProject(source_assets=[project_asset], target_duration=15.0, aspect_ratio="9:16",
        silence=SilenceSettings(preset="natural"), captions=CaptionStyle(style="modern", max_words=4, capitalization="upper"),
        voice_enhance=VoiceEnhanceSettings(preset="clear"), export_preset="youtube_shorts", remove_fillers=True)

    result = await editor.render_short(project)
    output = Path(result.outputs[-1])
    info = json.loads(subprocess.run([FFPROBE, "-v", "error", "-show_streams", "-show_format",
        "-of", "json", str(output)], capture_output=True, text=True, check=True).stdout)
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    has_audio = any(s["codec_type"] == "audio" for s in info["streams"])

    report = {
        "output": output.name,
        "resolution": [video["width"], video["height"]],
        "codec": video["codec_name"],
        "duration": round(float(info["format"]["duration"]), 2),
        "has_audio": has_audio,
        "decodes_fully": decodes_fully(output),
        "kept_segments": result.report["edit"]["kept_segments"],
        "kept_duration": result.report["edit"]["kept_duration"],
        "captions_burned": result.report["edit"]["captions_burned"],
        "reload_ok": editor.load(result.id).id == result.id,
    }
    print("\n===== SHORT-REPORT =====")
    print(json.dumps(report, ensure_ascii=False, indent=2))

    checks = [report["resolution"] == [1080, 1920], report["codec"] == "h264",
              report["has_audio"], report["decodes_fully"], report["reload_ok"],
              report["kept_duration"] < 15.5, len(report["kept_segments"]) >= 2]
    print("\nGESAMT:", "PASS" if all(checks) else "FAIL")
    return 0 if all(checks) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
