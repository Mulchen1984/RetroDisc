#!/usr/bin/env python3
"""Real dubbing: DE video -> Whisper -> Ollama translate EN -> TTS -> mix (Mission 4).

Nutzt das lokale tiny-Whisper-Modell, lokales Ollama zum Übersetzen und macOS
`say` als TTS. Fährt prepare_dubbing + render_dubbing und prüft die englische
Ausgabe (Decoding, Audio, SRT). Kurze Gegenprobe EN->DE der Übersetzung.

Aufruf:  python3 scripts/dubbing_realtest.py [dir] [model_dir] [ollama_model]
"""
from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.ffmpeg import FFmpeg
from src.models.director import (MediaAsset, ProductionProject, Scene, DubbingPlan, DubbingCue)
from src.services.assistant import Assistant
from src.services.director import Director
from src.services.translation import LocalOllamaTranslationProvider
from src.services.voice import LocalVoice

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
SAY = shutil.which("say")
MODEL_DIR = sys.argv[2] if len(sys.argv) > 2 else "/tmp/retrodisc-asr/models/whisper-tiny"
OLLAMA_MODEL = sys.argv[3] if len(sys.argv) > 3 else "llama3.2:3b"
HOST = "http://127.0.0.1:11434"

GERMAN_TEXT = ("Willkommen zu diesem kurzen Testvideo. Heute geht es um die automatische "
               "Übersetzung und Synchronisation. Vielen Dank fürs Zuschauen.")


def run_ffmpeg(*a):
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", *a], check=True)


def duration_of(path):
    out = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nk=1:nw=1", str(path)], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def decodes_fully(path):
    r = subprocess.run([FFMPEG, "-hide_banner", "-v", "error", "-xerror", "-i", str(path), "-f", "null", "-"],
                       capture_output=True)
    return r.returncode == 0 and not r.stderr.strip()


class MemoryLibrary:
    def __init__(self, db_path, ffmpeg):
        self.db_path = Path(db_path); self._ffmpeg = ffmpeg; self._t = {}
    async def asset(self, path):
        import hashlib
        path = Path(path).resolve(); info = await self._ffmpeg.probe(path)
        v = info.video_streams[0] if info.video_streams else None
        a = info.audio_streams[0] if info.audio_streams else None
        return MediaAsset(id=hashlib.sha256(str(path).encode()).hexdigest()[:16], path=str(path),
            kind="video" if v else "audio", duration=info.duration_seconds,
            video_codec=v.codec if v else None, audio_codec=a.codec if a else None,
            width=v.width if v else None, height=v.height if v else None,
            transcript=self._t.get(str(path)), title=path.stem)
    def attach_transcript(self, path, transcript):
        self._t[str(Path(path).resolve())] = transcript


def make_video(path, work):
    aiff = work / "de.aiff"; wav = work / "de.wav"; padded = work / "de_pad.wav"
    subprocess.run([SAY, "-v", "Anna", "-o", str(aiff), GERMAN_TEXT], check=True)
    run_ffmpeg("-i", str(aiff), "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", "-y", str(wav))
    # Headroom: die englische TTS ist meist länger als die deutsche Quelle.
    # Trailing-Stille gibt dem Dubbing genug Fenster (max. 25% Tempo erlaubt).
    total = round(duration_of(wav) + 6.0, 2)
    run_ffmpeg("-i", str(wav), "-af", f"apad=whole_dur={total}", "-t", f"{total:.2f}",
               "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", "-y", str(padded))
    run_ffmpeg("-f", "lavfi", "-i", "testsrc2=s=854x480:r=25", "-i", str(padded),
               "-map", "0:v", "-map", "1:a", "-t", f"{total:.2f}", "-pix_fmt", "yuv420p",
               "-c:v", "libx264", "-crf", "22", "-c:a", "aac", "-y", str(path))
    return total


async def main():
    if not (FFMPEG and SAY):
        print("SKIP: ffmpeg/say fehlen"); return 0
    if not (Path(MODEL_DIR) / "model.bin").is_file():
        print(f"SKIP: kein tiny-Modell unter {MODEL_DIR} (zuerst whisper_asr_realtest.py laufen lassen)"); return 0
    base = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/retrodisc-dub")
    base.mkdir(parents=True, exist_ok=True)
    work = base / "work"; work.mkdir(exist_ok=True)
    ffmpeg = FFmpeg()
    tts = LocalVoice.capability()
    print(f"# Dubbing-Realtest  model={OLLAMA_MODEL}  tts_available={tts['available']}")

    video = base / "de_video.mp4"; duration = make_video(video, work)
    library = MemoryLibrary(base / "library.db", ffmpeg)
    director = Director(library, ffmpeg, Assistant(model=OLLAMA_MODEL, host=HOST),
                        base / "out", base / "audio", base / "temp")
    asset = await library.asset(video)

    # DE -> Whisper
    transcribed = await director.transcribe(asset, model=MODEL_DIR)
    segs = transcribed.transcript.get("segments", [])
    duration = transcribed.duration  # echte ffprobe-Dauer, nicht die say-Länge
    print(f"  DE-Segmente: {len(segs)} · Sprache: {transcribed.transcript.get('language')} · Dauer {duration:.2f}s")

    # Ollama verfügbar?
    provider = LocalOllamaTranslationProvider(director.assistant)
    if OLLAMA_MODEL not in await director.assistant.available_models():
        print(f"SKIP: Ollama-Modell {OLLAMA_MODEL} nicht verfügbar"); return 0

    # Ein Cue über die volle Klammer: die englische TTS muss ins Zeitfenster
    # passen (Director erlaubt max. 25% Beschleunigung). Bei sehr kurzen
    # Einzelsegmenten ist EN länger als DE — ganzer Clip als eine Passage ist
    # das realistische Dubbing für dieses kurze Testvideo.
    full_text = " ".join(str(s["text"]).strip() for s in segs)
    cues = [DubbingCue(start=0.0, end=round(duration - 0.01, 2),
                       source_text=full_text, speaker="speaker_1")]
    project = ProductionProject(prompt="Synchronisiere dieses Video ins Englische.",
        target_duration=duration, assets=[transcribed],
        timeline=[Scene(asset_id=transcribed.id, start=0, end=duration, position=0)],
        original_audio="duck",
        dubbing=DubbingPlan(asset_id=transcribed.id, source_language="de", target_language="en",
                            cues=cues, original_audio="duck"))
    director.save(project)

    # DE -> EN Übersetzung
    prepared = await director.prepare_dubbing(project, provider)
    translated = [c.translated_text for c in prepared.dubbing.cues]
    print("  Übersetzung EN:", json.dumps(translated, ensure_ascii=False)[:200])

    # Render EN-Video (TTS + Ducking)
    out = await director.render_dubbing(prepared)
    out = Path(out)
    stored = director.load(prepared.id)
    info = json.loads(subprocess.run([FFPROBE, "-v", "error", "-show_streams", "-show_format",
        "-of", "json", str(out)], capture_output=True, text=True, check=True).stdout)
    has_audio = any(s["codec_type"] == "audio" for s in info["streams"])
    srts = [p for p in stored.subtitle_paths if p.endswith(".srt") and Path(p).is_file()]

    # Gegenprobe EN -> DE (nur Übersetzung)
    back = await provider.translate(translated, "en", "de") if translated else []

    result = {
        "de_segments": len(segs),
        "translated_all_nonempty": all(t and t.strip() for t in translated),
        "output": out.name,
        "output_decodes": decodes_fully(out),
        "output_has_audio": has_audio,
        "output_duration": round(float(info["format"]["duration"]), 2),
        "srt_files": [Path(p).name for p in srts],
        "srt_has_content": bool(srts) and "-->" in Path(srts[0]).read_text(encoding="utf-8"),
        "generated_audio": len(stored.generated_audio),
        "back_translation_de": json.dumps(back, ensure_ascii=False)[:200],
    }
    print("\n===== ERGEBNIS =====")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    checks = [result["de_segments"] > 0, result["translated_all_nonempty"], result["output_decodes"],
              result["output_has_audio"], result["generated_audio"] > 0]
    print("\nGESAMT:", "PASS" if all(checks) else "FAIL")
    return 0 if all(checks) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
