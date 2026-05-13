"""RetroDisc MediaInfo — Dateianalyse Utility."""

from __future__ import annotations

from pathlib import Path
from typing import Optional


async def get_mediainfo_text(file_path: Path | str) -> str:
    """Gibt einen formatierten MediaInfo-Text zurück."""
    try:
        from pymediainfo import MediaInfo
        info = MediaInfo.parse(str(file_path))
        return info.to_data()
    except ImportError:
        # Fallback auf FFprobe
        from src.core.ffmpeg import FFmpeg
        ffmpeg = FFmpeg()
        media = await ffmpeg.probe(file_path)
        lines = [
            f"Datei: {media.path.name}",
            f"Typ: {media.media_type.value}",
            f"Container: {media.container}",
            f"Dauer: {media.duration_formatted}",
            f"Größe: {media.file_size_formatted}",
        ]
        if media.video_streams:
            v = media.video_streams[0]
            lines.append(f"Video: {v.codec} {v.width}x{v.height} @ {v.fps}fps")
        if media.audio_streams:
            a = media.audio_streams[0]
            lines.append(f"Audio: {a.codec} {a.channels}ch @ {a.sample_rate}Hz")
        if media.subtitle_streams:
            langs = [s.language or "?" for s in media.subtitle_streams]
            lines.append(f"Untertitel: {', '.join(langs)}")
        return "\n".join(lines)
