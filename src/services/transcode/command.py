"""Build an FFmpeg argument LIST (never a shell string) from profile+selection.

Encoder-specific rate control and preset mapping so one declarative profile works
across libx264/libx265/SVT-AV1/libaom and NVENC/QSV/AMF. Fully unit-testable.
"""
from __future__ import annotations

from typing import Optional

from src.services.transcode.profiles import (
    TranscodingProfile, QualityMode, ResolutionPolicy, AudioPolicy, SubtitlePolicy,
    DeinterlacePolicy,
)
from src.services.transcode.selection import EncoderSelection
from src.services.transcode.probe import SourceMediaInfo

_RES_WIDTH = {ResolutionPolicy.MAX_720: 1280, ResolutionPolicy.MAX_1080: 1920,
              ResolutionPolicy.MAX_2160: 3840}


def _rate_control(encoder: str, profile: TranscodingProfile) -> list[str]:
    value = str(profile.quality_value)
    if profile.quality_mode == QualityMode.BITRATE and profile.bitrate:
        args = ["-b:v", profile.bitrate]
        if profile.maxrate:
            args += ["-maxrate", profile.maxrate]
        if profile.bufsize:
            args += ["-bufsize", profile.bufsize]
        return args
    if encoder in ("libx264", "libx265", "libsvtav1"):
        return ["-crf", value]
    if encoder == "libaom-av1":
        return ["-crf", value, "-b:v", "0"]
    if encoder.endswith("_nvenc"):
        return ["-rc", "vbr", "-cq", value, "-b:v", "0"]
    if encoder.endswith("_qsv"):
        return ["-global_quality", value]
    if encoder.endswith("_amf"):
        return ["-rc", "cqp", "-qp_i", value, "-qp_p", value, "-qp_b", value]
    return ["-crf", value]


def _preset_args(encoder: str, preset: str) -> list[str]:
    if encoder == "libsvtav1":
        return ["-preset", str({"fast": 8, "medium": 6, "slow": 4}.get(preset, 6))]
    if encoder == "libaom-av1":
        return ["-cpu-used", str({"fast": 6, "medium": 4, "slow": 2}.get(preset, 4))]
    if encoder.endswith("_amf"):
        return ["-quality", {"fast": "speed", "medium": "balanced", "slow": "quality"}.get(preset, "balanced")]
    return ["-preset", preset]


def _pixel_format(encoder: str, requested: Optional[str]) -> Optional[str]:
    if not requested:
        return None
    if encoder.endswith(("_nvenc", "_qsv", "_amf")) and requested.endswith("10le"):
        return "p010le"                       # Hardware nutzt p010 statt planar 10-bit
    return requested


def _video_filters(profile: TranscodingProfile, source: SourceMediaInfo) -> list[str]:
    filters = []
    video = source.primary_video
    if profile.deinterlace_policy == DeinterlacePolicy.FORCE or (
            profile.deinterlace_policy == DeinterlacePolicy.AUTO and video and video.interlaced):
        filters.append("bwdif=mode=send_frame")
    width = _RES_WIDTH.get(profile.resolution_policy)
    if width:
        filters.append(f"scale='min(iw,{width})':-2:flags=lanczos")   # nur herunterskalieren
    return filters


def _audio_args(profile: TranscodingProfile) -> list[str]:
    if profile.audio_policy == AudioPolicy.COPY:
        return ["-map", "0:a?", "-c:a", "copy"]
    if profile.audio_policy == AudioPolicy.AAC_MULTI:
        return ["-map", "0:a?", "-c:a", "aac", "-b:a", "384k"]
    return ["-map", "0:a?", "-c:a", "aac", "-b:a", "192k", "-ac", "2"]   # AAC_STEREO


def _subtitle_args(profile: TranscodingProfile) -> list[str]:
    if profile.subtitle_policy == SubtitlePolicy.DROP:
        return ["-sn"]
    if profile.container == "mp4":
        return ["-map", "0:s?", "-c:s", "mov_text"]     # mp4 kann nur mov_text
    return ["-map", "0:s?", "-c:s", "copy"]


def _container_args(profile: TranscodingProfile) -> list[str]:
    return ["-movflags", "+faststart"] if profile.container == "mp4" else []


class FFmpegCommandBuilder:
    def __init__(self, ffmpeg_path: str = "ffmpeg"):
        self.ffmpeg_path = ffmpeg_path

    def build(self, source: SourceMediaInfo, profile: TranscodingProfile,
              selection: EncoderSelection, output_path: str, *,
              overwrite: bool = False, progress: bool = True) -> list[str]:
        if not selection.ok or not selection.encoder:
            raise ValueError("EncoderSelection ist nicht nutzbar – kein Command baubar.")
        args = [self.ffmpeg_path, "-hide_banner", "-nostdin", "-y" if overwrite else "-n"]
        args += ["-i", str(source.path)]
        args += ["-map", "0:v:0"]
        args += _audio_args(profile)
        args += _subtitle_args(profile)
        args += ["-map_metadata", "0"]         # Metadaten übernehmen

        filters = _video_filters(profile, source)
        if filters:
            args += ["-vf", ",".join(filters)]

        args += ["-c:v", selection.encoder]
        args += _rate_control(selection.encoder, profile)
        args += _preset_args(selection.encoder, profile.preset)
        pix = _pixel_format(selection.encoder, profile.pixel_format)
        if pix:
            args += ["-pix_fmt", pix]

        args += _container_args(profile)
        if progress:
            args += ["-progress", "pipe:1", "-nostats"]
        args.append(str(output_path))
        return args
