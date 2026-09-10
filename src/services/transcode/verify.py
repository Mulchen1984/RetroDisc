"""Post-transcode verification. Reuses the shared VerifyResult vocabulary.

Never trusts exit code 0 alone: checks the output exists, is big enough, is
readable by ffprobe, has a plausible duration and the expected video codec.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from src.services.verify import VerifyResult, Check
from src.services.transcode.probe import MediaProbeService

_CODEC_FAMILY = {
    "hevc": "h265", "h265": "h265", "libx265": "h265", "hevc_nvenc": "h265",
    "hevc_qsv": "h265", "hevc_amf": "h265",
    "h264": "h264", "avc1": "h264", "libx264": "h264", "h264_nvenc": "h264",
    "h264_qsv": "h264", "h264_amf": "h264",
    "av1": "av1", "libaom-av1": "av1", "libsvtav1": "av1",
    "av1_nvenc": "av1", "av1_qsv": "av1", "av1_amf": "av1",
}


def _canon(codec: str) -> str:
    return _CODEC_FAMILY.get((codec or "").lower(), (codec or "").lower())


async def verify_transcode(output_path, probe: MediaProbeService, *,
                           expected_duration: Optional[float] = None,
                           expected_codec: str = "", min_bytes: int = 4096,
                           expected_audio: bool = False) -> VerifyResult:
    path = Path(output_path)
    if not path.is_file():
        return VerifyResult.from_checks([Check("exists", False, "Ausgabedatei fehlt.")])

    checks: list[Check] = []
    size = path.stat().st_size
    checks.append(Check("size", size >= min_bytes,
                        f"{size} Bytes" if size >= min_bytes else f"zu klein ({size} < {min_bytes} Bytes)"))

    info = await probe.probe(str(path))
    video = info.primary_video
    checks.append(Check("readable", info.duration > 0 or bool(info.video),
                        "" if (info.duration > 0 or info.video) else "ffprobe konnte Ausgabe nicht lesen"))
    checks.append(Check("video_stream", video is not None,
                        "" if video else "kein Videostream in der Ausgabe"))

    if expected_codec and video:
        ok = _canon(video.codec) == _canon(expected_codec)
        checks.append(Check("codec", ok,
                            "" if ok else f"Codec {video.codec} statt erwartet {expected_codec}"))

    if expected_audio:
        checks.append(Check("audio_stream", bool(info.audio), "Audiospur fehlt." if not info.audio else ""))

    if expected_duration:
        tolerance = max(1.0, expected_duration * 0.05)
        ok = info.duration > 0 and abs(info.duration - expected_duration) <= tolerance
        checks.append(Check("duration", ok,
                            "" if ok else f"Dauer {info.duration:.1f}s statt ~{expected_duration:.1f}s",
                            severity="error"))
    return VerifyResult.from_checks(checks)
