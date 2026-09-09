"""MediaProbeService around ffprobe -of json. Robust against missing/odd fields."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Optional

from src.services.transcode.process import run_process
from src.services.transcode.selection import SourceHints

_HDR_TRANSFERS = {"smpte2084", "arib-std-b67", "smpte428", "bt2020-10", "bt2020-12"}
_INTERLACED = {"tt", "bb", "tb", "bt", "interlaced"}


@dataclass
class VideoStream:
    index: int = 0
    codec: str = ""
    width: int = 0
    height: int = 0
    fps: float = 0.0
    bit_depth: int = 8
    pixel_format: str = ""
    hdr: bool = False
    field_order: str = ""
    language: str = ""
    default: bool = False
    forced: bool = False

    @property
    def interlaced(self) -> bool:
        return self.field_order in _INTERLACED


@dataclass
class AudioStream:
    index: int = 0
    codec: str = ""
    channels: int = 0
    sample_rate: int = 0
    language: str = ""
    default: bool = False
    forced: bool = False


@dataclass
class SubtitleStream:
    index: int = 0
    codec: str = ""
    language: str = ""
    default: bool = False
    forced: bool = False


@dataclass
class SourceMediaInfo:
    path: str = ""
    container: str = ""
    duration: float = 0.0
    size: int = 0
    video: list[VideoStream] = field(default_factory=list)
    audio: list[AudioStream] = field(default_factory=list)
    subtitles: list[SubtitleStream] = field(default_factory=list)

    @property
    def primary_video(self) -> Optional[VideoStream]:
        return self.video[0] if self.video else None

    def to_hints(self) -> SourceHints:
        v = self.primary_video
        if not v:
            return SourceHints()
        return SourceHints(width=v.width, height=v.height, bit_depth=v.bit_depth,
                           hdr=v.hdr, source_codec=v.codec)


def _to_int(value, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _fps(stream: dict) -> float:
    for key in ("avg_frame_rate", "r_frame_rate"):
        raw = stream.get(key) or ""
        try:
            value = float(Fraction(raw)) if "/" in str(raw) else float(raw)
            if value > 0:
                return round(value, 3)
        except (ValueError, ZeroDivisionError):
            continue
    return 0.0


def _bit_depth(stream: dict) -> int:
    depth = _to_int(stream.get("bits_per_raw_sample"), 0)
    if depth:
        return depth
    pix = (stream.get("pix_fmt") or "").lower()
    if "p010" in pix or "10le" in pix or "10be" in pix:
        return 10
    if "p016" in pix or "12le" in pix or "12be" in pix:
        return 12
    return 8


def _disposition(stream: dict, key: str) -> bool:
    return bool((stream.get("disposition") or {}).get(key, 0))


def _language(stream: dict) -> str:
    return (stream.get("tags") or {}).get("language", "") or ""


def parse_probe_json(path: str, data: dict) -> SourceMediaInfo:
    fmt = data.get("format") or {}
    info = SourceMediaInfo(path=str(path), container=fmt.get("format_name", "") or "",
                           duration=_to_float(fmt.get("duration")), size=_to_int(fmt.get("size")))
    for stream in data.get("streams") or []:
        kind = stream.get("codec_type")
        if kind == "video":
            if _disposition(stream, "attached_pic"):
                continue                      # Cover-Bild ist kein Videostream
            transfer = (stream.get("color_transfer") or "").lower()
            primaries = (stream.get("color_primaries") or "").lower()
            info.video.append(VideoStream(
                index=_to_int(stream.get("index")), codec=stream.get("codec_name", "") or "",
                width=_to_int(stream.get("width")), height=_to_int(stream.get("height")),
                fps=_fps(stream), bit_depth=_bit_depth(stream),
                pixel_format=stream.get("pix_fmt", "") or "",
                hdr=transfer in _HDR_TRANSFERS or primaries == "bt2020",
                field_order=(stream.get("field_order") or "").lower(),
                language=_language(stream), default=_disposition(stream, "default"),
                forced=_disposition(stream, "forced")))
        elif kind == "audio":
            info.audio.append(AudioStream(
                index=_to_int(stream.get("index")), codec=stream.get("codec_name", "") or "",
                channels=_to_int(stream.get("channels")),
                sample_rate=_to_int(stream.get("sample_rate")),
                language=_language(stream), default=_disposition(stream, "default"),
                forced=_disposition(stream, "forced")))
        elif kind == "subtitle":
            info.subtitles.append(SubtitleStream(
                index=_to_int(stream.get("index")), codec=stream.get("codec_name", "") or "",
                language=_language(stream), default=_disposition(stream, "default"),
                forced=_disposition(stream, "forced")))
    return info


class MediaProbeService:
    def __init__(self, ffprobe_path: str = "ffprobe", *, runner=run_process, timeout: float = 30.0):
        self.ffprobe_path = ffprobe_path
        self._run = runner
        self.timeout = timeout

    def probe_args(self, path: str) -> list[str]:
        return [self.ffprobe_path, "-v", "error", "-show_format", "-show_streams",
                "-of", "json", str(path)]

    async def probe(self, path: str) -> SourceMediaInfo:
        result = await self._run(self.probe_args(path), self.timeout)
        try:
            data = json.loads(result.stdout or "{}")
            if not isinstance(data, dict):
                data = {}
        except ValueError:
            data = {}                          # kaputtes JSON -> leere, aber gültige Info
        return parse_probe_json(path, data)
