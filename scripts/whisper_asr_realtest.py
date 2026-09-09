#!/usr/bin/env python3
"""Real Whisper ASR + transcript->short with the smallest local model (Missionen 1-3).

Lädt EINMAL das kleinste faster-whisper-Modell (tiny) in ein lokales Verzeichnis
(kein großes Modell), erzeugt echte deutsche Sprache via macOS `say` und fährt:

  A) SubtitleGenerator: Audio -> Sprache erkennen -> Segmente start/end/text -> SRT
  B) Director.transcribe: Video -> Audio extrahieren -> ASR -> Transcript ->
     Projekt speichern -> neu laden
  C) Smart Edit mit ECHTEM ASR: reales Transcript -> Highlights/Pausen -> Short

Aufruf:  python3 scripts/whisper_asr_realtest.py [dir]
"""
from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.ffmpeg import FFmpeg
from src.models.director import MediaAsset
from src.models.smart_edit import SmartEditProject, SilenceSettings, CaptionStyle
from src.services.assistant import Assistant
from src.services.director import Director
from src.services.smart_edit import SmartEditor
from src.services.subtitle import SubtitleGenerator

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
SAY = shutil.which("say")

GERMAN_TEXT = ("Willkommen zu diesem kurzen Testvideo. Heute sprechen wir über die "
               "automatische Untertitelung. Der spannendste Teil kommt jetzt: die "
               "Spracherkennung funktioniert vollständig offline. Zum Schluss ein "
               "kurzes Fazit und vielen Dank fürs Zuschauen.")


def run_ffmpeg(*args):
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", *args], check=True)


def duration_of(path):
    out = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nk=1:nw=1", str(path)], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def decodes_fully(path):
    r = subprocess.run([FFMPEG, "-hide_banner", "-v", "error", "-xerror", "-i", str(path), "-f", "null", "-"],
                       capture_output=True)
    return r.returncode == 0 and not r.stderr.strip()


class MemoryLibrary:
    """In-memory library: probe via ffprobe, store attached transcripts."""
    def __init__(self, db_path, ffmpeg):
        self.db_path = Path(db_path); self._ffmpeg = ffmpeg; self._transcripts = {}
    async def asset(self, path):
        import hashlib
        path = Path(path).resolve(); info = await self._ffmpeg.probe(path)
        v = info.video_streams[0] if info.video_streams else None
        a = info.audio_streams[0] if info.audio_streams else None
        return MediaAsset(id=hashlib.sha256(str(path).encode()).hexdigest()[:16], path=str(path),
            kind="video" if v else "audio", duration=info.duration_seconds,
            video_codec=v.codec if v else None, audio_codec=a.codec if a else None,
            width=v.width if v else None, height=v.height if v else None,
            transcript=self._transcripts.get(str(path)), title=path.stem)
    def attach_transcript(self, path, transcript):
        self._transcripts[str(Path(path).resolve())] = transcript


def ensure_tiny_model(models_dir: Path) -> Path:
    """Download the smallest model once into a flat dir with model.bin (offline afterwards)."""
    target = models_dir / "whisper-tiny"
    if (target / "model.bin").is_file():
        return target
    from huggingface_hub import snapshot_download
    target.mkdir(parents=True, exist_ok=True)
    snapshot_download(repo_id="Systran/faster-whisper-tiny", local_dir=str(target),
                      allow_patterns=["*.bin", "*.json", "*.txt"])
    return target


def make_speech_wav(path: Path, work: Path) -> None:
    aiff = work / "speech.aiff"
    subprocess.run([SAY, "-v", "Anna", "-o", str(aiff), GERMAN_TEXT], check=True)
    run_ffmpeg("-i", str(aiff), "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", "-y", str(path))


def make_video(path: Path, speech: Path) -> None:
    dur = max(8.0, duration_of(speech))
    run_ffmpeg("-f", "lavfi", "-i", "testsrc2=s=1280x720:r=25", "-i", str(speech),
               "-map", "0:v", "-map", "1:a", "-t", f"{dur:.2f}", "-pix_fmt", "yuv420p",
               "-c:v", "libx264", "-crf", "22", "-c:a", "aac", "-shortest", "-y", str(path))


async def main():
    if not (FFMPEG and SAY):
        print("SKIP: ffmpeg/say fehlen"); return 0
    base = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/retrodisc-asr")
    base.mkdir(parents=True, exist_ok=True)
    work = base / "work"; work.mkdir(exist_ok=True)
    ffmpeg = FFmpeg()

    print("# Whisper-ASR-Realtest (Modell: tiny, lokal)")
    model_dir = ensure_tiny_model(base / "models")
    print(f"  Modell: {model_dir}  model.bin={ (model_dir/'model.bin').is_file() }")
    cap = SubtitleGenerator.capability(str(model_dir))
    print(f"  Capability: available={cap['available']} status={cap['status']} engines={cap['engines']}")

    speech = base / "speech16k.wav"; make_speech_wav(speech, work)
    print(f"  Deutsche Testsprache: {speech.name} ({duration_of(speech):.1f}s)")

    results = {}

    # ── A) SubtitleGenerator direkt ─────────────────────────────────────────
    t0 = time.monotonic()
    gen = SubtitleGenerator(str(model_dir))
    srt = base / "speech.srt"
    await gen.generate(speech, srt, format="srt", language="de")
    js = base / "speech.json"
    await gen.generate(speech, js, format="json", language="de")
    data = json.loads(js.read_text(encoding="utf-8"))
    segs = data.get("segments", [])
    results["A_subtitle"] = {
        "asr_seconds": round(time.monotonic() - t0, 2),
        "language": data.get("language"),
        "segments": len(segs),
        "valid_timings": all(0 <= s["start"] < s["end"] for s in segs),
        "has_text": all(str(s.get("text", "")).strip() for s in segs),
        "srt_has_timecodes": "-->" in srt.read_text(encoding="utf-8"),
        "first_text": (segs[0]["text"].strip()[:60] if segs else ""),
    }

    # ── B) Director.transcribe (Video -> Audio -> ASR -> Projekt) ────────────
    video = base / "german_video.mp4"; make_video(video, speech)
    library = MemoryLibrary(base / "library.db", ffmpeg)
    director = Director(library, ffmpeg, Assistant(host="http://127.0.0.1:11434"),
                        base / "out", base / "audio", base / "temp")
    asset = await library.asset(video)
    transcribed = await director.transcribe(asset, model=str(model_dir))
    editor = SmartEditor(library, ffmpeg, base / "out", base / "temp")
    project = SmartEditProject(source_assets=[transcribed], target_duration=10.0, aspect_ratio="9:16",
        silence=SilenceSettings(preset="natural"), captions=CaptionStyle(style="modern"))
    editor.save(project)
    reloaded = editor.load(project.id)
    results["B_director_transcribe"] = {
        "segments": len(transcribed.transcript.get("segments", [])),
        "language": transcribed.transcript.get("language"),
        "project_reload_ok": reloaded.id == project.id,
        "transcript_on_asset": bool(reloaded.source_assets[0].transcript),
    }

    # ── C) Smart Edit mit echtem ASR (keine vorgegebenen Segmente) ───────────
    t1 = time.monotonic()
    short = await editor.render_short(project, director=director, wish="Finde die interessantesten 10 Sekunden.")
    out = Path(short.outputs[-1])
    info = json.loads(subprocess.run([FFPROBE, "-v", "error", "-show_streams", "-show_format",
        "-of", "json", str(out)], capture_output=True, text=True, check=True).stdout)
    vid = next(s for s in info["streams"] if s["codec_type"] == "video")
    results["C_short_from_real_asr"] = {
        "render_seconds": round(time.monotonic() - t1, 2),
        "resolution": [vid["width"], vid["height"]],
        "duration": round(float(info["format"]["duration"]), 2),
        "has_audio": any(s["codec_type"] == "audio" for s in info["streams"]),
        "decodes_fully": decodes_fully(out),
        "kept": short.report["edit"]["kept_segments"],
        "captions_burned": short.report["edit"]["captions_burned"],
    }

    print("\n===== ERGEBNIS =====")
    print(json.dumps(results, ensure_ascii=False, indent=2, default=str))
    a, b, c = results["A_subtitle"], results["B_director_transcribe"], results["C_short_from_real_asr"]
    checks = [a["segments"] > 0, a["valid_timings"], a["has_text"], a["srt_has_timecodes"],
              b["segments"] > 0, b["project_reload_ok"], b["transcript_on_asset"],
              c["resolution"] == [1080, 1920], c["decodes_fully"], c["has_audio"]]
    print("\nGESAMT:", "PASS" if all(checks) else "FAIL")
    return 0 if all(checks) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
