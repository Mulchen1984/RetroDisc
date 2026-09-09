"""Capability-Dashboard: ehrliche Aggregation echter Detektion (Mission 12)."""
import asyncio
import json

from retrodisc_launcher import RetroDiscBridge


class _Fut:
    def __init__(self, value):
        self._value = value
    def result(self, timeout=None):
        return self._value


def _bridge():
    bridge = object.__new__(RetroDiscBridge)
    bridge.get_tool_status = lambda: json.dumps({
        "ffmpeg": {"available": True, "path": "/opt/ffmpeg"},
        "ffprobe": {"available": True, "path": "/opt/ffprobe"},
        "ytdlp": {"available": False, "path": "yt-dlp"}})
    bridge._async = lambda coro: _Fut(asyncio.run(coro))

    class Director:
        async def capabilities(self):
            return {"llm_models": ["llama3.2:3b"], "whisper": {"status": "model_missing", "note": "kein Modell"},
                    "tts": {"available": True, "engine": "macOS say"}}

    class SmartEditor:
        async def capabilities(self):
            return {"hardware_encode": ["h264_videotoolbox"], "captions": False}

    class Restoration:
        async def capabilities(self):
            return {"stabilization": {"level": "basic"},
                    "providers": {"qtgmc": {"note": "n/a"}, "rife": {"note": "n/a"}}}

    bridge._director_service = lambda: Director()
    bridge._smart_editor_service = lambda: SmartEditor()
    bridge._restoration_service = lambda: Restoration()
    return bridge


def test_diagnostics_reports_real_status_no_fake_availability():
    data = json.loads(_bridge().diagnostics())
    flat = {item["name"]: item for group in data["groups"] for item in group["items"]}

    assert flat["FFmpeg"]["status"] == "available" and flat["FFmpeg"]["detail"] == "/opt/ffmpeg"
    assert flat["yt-dlp"]["status"] == "unavailable"
    assert flat["Ollama (LLM)"]["status"] == "available" and "llama3.2:3b" in flat["Ollama (LLM)"]["detail"]
    assert flat["Whisper (ASR)"]["status"] == "model_missing"        # ehrlich: Paket da, Modell fehlt
    assert flat["TTS (Systemstimmen)"]["status"] == "available"
    assert flat["Hardware-Encoder"]["status"] == "available" and "videotoolbox" in flat["Hardware-Encoder"]["detail"]
    assert flat["libass (Untertitel einbrennen)"]["status"] == "unavailable"   # kein Fake
    assert flat["libvidstab (Stabilisierung)"]["status"] == "optional"          # nur deshake/basic
    assert flat["QTGMC/VapourSynth"]["status"] == "optional"
    assert flat["RIFE"]["status"] == "optional"
    # Kategorien vorhanden
    assert {g["category"] for g in data["groups"]} == {"Werkzeuge", "KI & Sprache", "Encoder", "Restaurierung"}
