"""RetroDisc Datenmodelle - MediaFile, Job, Preset, Pipeline-States."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

import structlog


log = structlog.get_logger()

# ─── Enums ───────────────────────────────────────────────────────────

class JobState(Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobType(Enum):
    CONVERT = "convert"
    BURN_DVD = "burn_dvd"
    BURN_BLURAY = "burn_bluray"
    BURN_CD = "burn_cd"
    RIP_DVD = "rip_dvd"
    RIP_BLURAY = "rip_bluray"
    DOWNLOAD = "download"
    MEDIATHEK_DOWNLOAD = "mediathek_download"
    CREATE_ISO = "create_iso"
    DVD_AUTHOR = "dvd_author"
    SUBTITLE_GENERATE = "subtitle_generate"
    UPSCALE = "upscale"
    INTERPOLATE = "interpolate"
    SMART_EDIT = "smart_edit"
    TRIM = "trim"
    MERGE = "merge"
    # Media AI Pipeline. Eigene Typen, damit Jobhistorie und Oberflaeche einen
    # Import von einem gewoehnlichen Download unterscheiden koennen.
    MEDIA_AI_IMPORT = "media_ai_import"
    MEDIA_AI_AUDIO = "media_ai_audio"
    MEDIA_AI_VIDEO = "media_ai_video"
    MEDIA_AI_TRANSCRIBE = "media_ai_transcribe"
    MEDIA_AI_FRAMES = "media_ai_frames"


class MediaType(Enum):
    VIDEO = "video"
    AUDIO = "audio"
    IMAGE = "image"
    SUBTITLE = "subtitle"
    DISC = "disc"
    ISO = "iso"
    UNKNOWN = "unknown"


class DiscType(Enum):
    DVD = "dvd"
    BLURAY = "bluray"
    CD = "cd"


# ─── Media Info ──────────────────────────────────────────────────────

@dataclass
class AudioStream:
    index: int
    codec: str
    channels: int
    sample_rate: int
    bitrate: Optional[int] = None
    language: Optional[str] = None


@dataclass
class VideoStream:
    index: int
    codec: str
    width: int
    height: int
    fps: float
    bitrate: Optional[int] = None
    hdr: bool = False


@dataclass
class SubtitleStream:
    index: int
    codec: str
    language: Optional[str] = None


@dataclass
class MediaFile:
    """Repräsentiert eine Mediendatei mit allen Metadaten."""
    path: Path
    media_type: MediaType = MediaType.UNKNOWN
    container: str = ""
    duration_seconds: float = 0.0
    file_size_bytes: int = 0
    video_streams: list[VideoStream] = field(default_factory=list)
    audio_streams: list[AudioStream] = field(default_factory=list)
    subtitle_streams: list[SubtitleStream] = field(default_factory=list)
    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    thumbnail_path: Optional[Path] = None

    @property
    def has_video(self) -> bool:
        return len(self.video_streams) > 0

    @property
    def has_audio(self) -> bool:
        return len(self.audio_streams) > 0

    @property
    def resolution(self) -> Optional[str]:
        if self.video_streams:
            v = self.video_streams[0]
            return f"{v.width}x{v.height}"
        return None

    @property
    def duration_formatted(self) -> str:
        total = int(self.duration_seconds)
        h, remainder = divmod(total, 3600)
        m, s = divmod(remainder, 60)
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    @property
    def file_size_formatted(self) -> str:
        size = self.file_size_bytes
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"


# ─── Conversion Presets ──────────────────────────────────────────────

@dataclass
class ConversionPreset:
    """Ein Konvertierungs-Preset mit allen FFmpeg-Parametern."""
    name: str
    display_name: str
    category: str  # "video", "audio", "device", "disc"
    container: str  # "mp4", "mkv", "mp3", "wav", etc.
    video_codec: Optional[str] = None  # "libx264", "libx265", "copy"
    audio_codec: Optional[str] = None  # "aac", "libmp3lame", "copy"
    video_bitrate: Optional[str] = None  # "5M", "10M"
    audio_bitrate: Optional[str] = None  # "192k", "320k"
    resolution: Optional[str] = None  # "1920:1080", "1280:720"
    fps: Optional[float] = None
    sample_rate: Optional[int] = None  # 44100, 48000
    extra_args: list[str] = field(default_factory=list)
    description: str = ""


# ─── Jobs ────────────────────────────────────────────────────────────

@dataclass
class Job:
    """Ein Verarbeitungs-Job in der Pipeline."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    job_type: JobType = JobType.CONVERT
    state: JobState = JobState.PENDING
    input_files: list[Path] = field(default_factory=list)
    output_path: Optional[Path] = None
    preset: Optional[ConversionPreset] = None
    params: dict[str, Any] = field(default_factory=dict)
    progress: float = 0.0  # 0.0 - 100.0
    progress_text: str = ""
    error_message: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    on_progress: Optional[Callable[[float, str], None]] = field(
        default=None, repr=False
    )
    on_complete: Optional[Callable[[Job], None]] = field(
        default=None, repr=False
    )

    @property
    def elapsed_seconds(self) -> float:
        if self.started_at is None:
            return 0.0
        end = self.finished_at or datetime.now()
        return (end - self.started_at).total_seconds()

    def update_progress(self, progress: float, text: str = "") -> None:
        self.progress = min(progress, 100.0)
        self.progress_text = text
        if self.on_progress:
            try:
                self.on_progress(self.progress, self.progress_text)
            except Exception as observer_error:
                log.error(
                    "Progress-Observer fehlgeschlagen",
                    job_id=self.id,
                    error=str(observer_error),
                )

    def mark_running(self) -> None:
        self.state = JobState.RUNNING
        self.started_at = datetime.now()

    def mark_done(self) -> None:
        self.state = JobState.DONE
        self.progress = 100.0
        self.finished_at = datetime.now()
        if self.on_complete:
            try:
                self.on_complete(self)
            except Exception as observer_error:
                log.error(
                    "Job-Completion-Observer fehlgeschlagen",
                    job_id=self.id,
                    error=str(observer_error),
                )

    def mark_failed(self, error: str) -> None:
        self.state = JobState.FAILED
        self.error_message = error
        self.finished_at = datetime.now()

    def mark_cancelled(self) -> None:
        self.state = JobState.CANCELLED
        self.finished_at = datetime.now()


# ─── Search Results ──────────────────────────────────────────────────

@dataclass
class SearchResult:
    """Ein Suchergebnis aus YouTube oder Mediathek."""
    title: str
    url: str
    source: str  # "youtube", "ard", "zdf", "arte", etc.
    duration_seconds: Optional[float] = None
    thumbnail_url: Optional[str] = None
    description: Optional[str] = None
    published_at: Optional[str] = None
    quality: Optional[str] = None  # "HD", "4K", etc.
    channel: Optional[str] = None


# ─── Smart Edit / Highlights ─────────────────────────────────────────

@dataclass
class SceneScore:
    """Bewertung einer Szene für Smart Highlights."""
    start_time: float
    end_time: float
    audio_energy: float = 0.0  # 0.0 - 1.0
    motion_score: float = 0.0  # 0.0 - 1.0
    face_count: int = 0
    combined_score: float = 0.0

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time


@dataclass
class HighlightConfig:
    """Konfiguration für KI Auto-Edit."""
    target_duration_seconds: float = 300.0  # 5 Minuten Standard
    prefer_faces: bool = True
    prefer_audio_peaks: bool = True
    prefer_motion: bool = True
    add_transitions: bool = True
    transition_duration: float = 0.5  # Sekunden
    min_clip_duration: float = 3.0
    max_clip_duration: float = 30.0
