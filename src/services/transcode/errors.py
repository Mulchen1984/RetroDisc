"""FFmpeg error classification from stderr — concise table, honest UNKNOWN fallback.

Not a wall of 200 regexes: a small ordered keyword table covers the common,
actionable cases; anything else stays UNKNOWN and keeps the original stderr so
nothing is misreported.
"""
from __future__ import annotations

from enum import Enum


class FFmpegErrorClass(str, Enum):
    INPUT_NOT_FOUND = "INPUT_NOT_FOUND"
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    DECODER_ERROR = "DECODER_ERROR"
    ENCODER_NOT_AVAILABLE = "ENCODER_NOT_AVAILABLE"
    HARDWARE_INIT_FAILED = "HARDWARE_INIT_FAILED"
    DEVICE_LOST = "DEVICE_LOST"
    OUT_OF_DISK = "OUT_OF_DISK"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    OUTPUT_WRITE_ERROR = "OUTPUT_WRITE_ERROR"
    PROCESS_TIMEOUT = "PROCESS_TIMEOUT"
    PROCESS_CANCELLED = "PROCESS_CANCELLED"
    UNKNOWN = "UNKNOWN"


# Ordered: earlier, more specific classes win. Keep this list short and curated.
_TABLE: list[tuple[FFmpegErrorClass, tuple[str, ...]]] = [
    (FFmpegErrorClass.OUT_OF_DISK, ("no space left", "enospc", "disk full")),
    (FFmpegErrorClass.PERMISSION_DENIED, ("permission denied", "eacces", "access is denied")),
    (FFmpegErrorClass.INPUT_NOT_FOUND, ("no such file or directory", "could not open input",
                                        "input/output error", "does not exist")),
    (FFmpegErrorClass.ENCODER_NOT_AVAILABLE, ("unknown encoder", "encoder not found",
                                              "cannot load", "not implemented")),
    (FFmpegErrorClass.HARDWARE_INIT_FAILED, ("cannot init", "failed to initialise", "failed to initialize",
                                             "device creation failed", "no capable devices",
                                             "no nvenc capable devices", "openencodesessionex failed",
                                             "hwaccel", "cannot open the device")),
    (FFmpegErrorClass.DEVICE_LOST, ("device lost", "gpu has fallen", "device removed",
                                    "no longer available")),
    (FFmpegErrorClass.DECODER_ERROR, ("decoder", "error while decoding", "invalid data found")),
    (FFmpegErrorClass.UNSUPPORTED_FORMAT, ("invalid data found when processing input",
                                           "unknown format", "unsupported", "could not find codec")),
    (FFmpegErrorClass.OUTPUT_WRITE_ERROR, ("could not write header", "error writing trailer",
                                           "muxer does not support")),
    (FFmpegErrorClass.INVALID_ARGUMENT, ("invalid argument", "option not found",
                                         "error parsing", "unrecognized option")),
]


def classify_ffmpeg_error(stderr: str, *, returncode: int | None = None,
                          timed_out: bool = False, cancelled: bool = False) -> FFmpegErrorClass:
    if cancelled:
        return FFmpegErrorClass.PROCESS_CANCELLED
    if timed_out:
        return FFmpegErrorClass.PROCESS_TIMEOUT
    low = (stderr or "").lower()
    for error_class, needles in _TABLE:
        if any(n in low for n in needles):
            return error_class
    return FFmpegErrorClass.UNKNOWN
