"""Declarative transcoding profiles — structured fields, never full command strings.

The command builder turns a profile + encoder selection into FFmpeg args, so the
same profile works for CPU or any hardware encoder.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class QualityMode(str, Enum):
    CRF = "crf"          # x264/x265/svt-av1 constant quality
    CQ = "cq"            # NVENC constant quality
    QP = "qp"            # constant quantiser
    BITRATE = "bitrate"  # target bitrate


class ResolutionPolicy(str, Enum):
    KEEP = "keep"
    MAX_720 = "max_720"
    MAX_1080 = "max_1080"
    MAX_2160 = "max_2160"
    DVD_SD = "dvd_sd"    # preserve SD DVD geometry


class FrameratePolicy(str, Enum):
    KEEP = "keep"


class HDRPolicy(str, Enum):
    KEEP = "keep"
    TONEMAP_SDR = "tonemap_sdr"
    STRIP = "strip"


class AudioPolicy(str, Enum):
    COPY = "copy"
    AAC_STEREO = "aac_stereo"
    AAC_MULTI = "aac_multi"


class SubtitlePolicy(str, Enum):
    COPY = "copy"
    DROP = "drop"


class DeinterlacePolicy(str, Enum):
    NONE = "none"
    AUTO = "auto"        # bwdif only if source flagged interlaced
    FORCE = "force"


@dataclass
class TranscodingProfile:
    name: str
    description: str = ""
    codec: str = "h264"                       # bevorzugter Ziel-Codec
    fallback_codecs: list[str] = field(default_factory=list)  # geordnete Downgrade-Kette
    allow_hardware: bool = True
    hardware_priority: list[str] = field(default_factory=lambda: ["nvidia", "intel", "amd"])
    quality_mode: QualityMode = QualityMode.CRF
    quality_value: int = 22
    preset: str = "medium"
    bitrate: Optional[str] = None
    maxrate: Optional[str] = None
    bufsize: Optional[str] = None
    resolution_policy: ResolutionPolicy = ResolutionPolicy.KEEP
    framerate_policy: FrameratePolicy = FrameratePolicy.KEEP
    pixel_format: Optional[str] = None        # None = Quelle behalten
    hdr_policy: HDRPolicy = HDRPolicy.KEEP
    audio_policy: AudioPolicy = AudioPolicy.AAC_STEREO
    subtitle_policy: SubtitlePolicy = SubtitlePolicy.DROP
    deinterlace_policy: DeinterlacePolicy = DeinterlacePolicy.AUTO
    container: str = "mp4"

    def to_dict(self) -> dict:
        out = {}
        for k, v in self.__dict__.items():
            out[k] = v.value if isinstance(v, Enum) else v
        return out


BUILTIN_PROFILES: dict[str, TranscodingProfile] = {
    "h264_compatibility": TranscodingProfile(
        name="h264_compatibility", description="Maximale Kompatibilität",
        codec="h264", quality_mode=QualityMode.CRF, quality_value=20, preset="medium",
        pixel_format="yuv420p", audio_policy=AudioPolicy.AAC_STEREO,
        subtitle_policy=SubtitlePolicy.DROP, container="mp4"),
    "h265_quality": TranscodingProfile(
        name="h265_quality", description="Kleinere Dateien, gute Qualität",
        codec="h265", fallback_codecs=["h264"], quality_value=22, preset="medium",
        audio_policy=AudioPolicy.COPY, subtitle_policy=SubtitlePolicy.COPY, container="mkv"),
    "av1_archive": TranscodingProfile(
        name="av1_archive", description="Hohe Kompression / Archiv",
        codec="av1", fallback_codecs=["h265"], quality_value=30, preset="slow",
        audio_policy=AudioPolicy.COPY, subtitle_policy=SubtitlePolicy.COPY, container="mkv"),
    "fast_hardware": TranscodingProfile(
        name="fast_hardware", description="Maximale Geschwindigkeit (Hardware bevorzugt)",
        codec="h264", fallback_codecs=["h265"], allow_hardware=True,
        quality_mode=QualityMode.CQ, quality_value=23, preset="fast",
        audio_policy=AudioPolicy.AAC_STEREO, container="mp4"),
    "dvd_preserve": TranscodingProfile(
        name="dvd_preserve", description="DVD deinterlacen und behutsam transcodieren",
        codec="h264", quality_value=18, preset="slow", pixel_format="yuv420p",
        resolution_policy=ResolutionPolicy.DVD_SD, deinterlace_policy=DeinterlacePolicy.FORCE,
        audio_policy=AudioPolicy.AAC_STEREO, container="mp4"),
    "bluray_preserve": TranscodingProfile(
        name="bluray_preserve", description="1080p hochwertig erhalten",
        codec="h265", fallback_codecs=["h264"], quality_value=18, preset="slow",
        resolution_policy=ResolutionPolicy.MAX_1080, audio_policy=AudioPolicy.COPY,
        subtitle_policy=SubtitlePolicy.COPY, container="mkv"),
    "uhd_preserve": TranscodingProfile(
        name="uhd_preserve", description="4K/HDR möglichst sinnvoll erhalten",
        codec="h265", fallback_codecs=[], quality_value=20, preset="slow",
        resolution_policy=ResolutionPolicy.MAX_2160, pixel_format="yuv420p10le",
        hdr_policy=HDRPolicy.KEEP, audio_policy=AudioPolicy.COPY,
        subtitle_policy=SubtitlePolicy.COPY, container="mkv"),
}


def get_profile(name: str) -> TranscodingProfile:
    if name not in BUILTIN_PROFILES:
        raise KeyError(f"Unbekanntes Profil: {name}")
    return BUILTIN_PROFILES[name]
