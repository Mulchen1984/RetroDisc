"""RetroDisc Settings — App-Einstellungen."""

from __future__ import annotations

import os
import platform
import tempfile
from pathlib import Path

from pydantic import BaseModel, Field


def _default_burn_device() -> str:
    """Return the platform-appropriate default optical drive."""
    system = platform.system()
    if system == "Darwin":
        return ""  # Erst ein tatsächlich erkanntes/ausgewähltes Laufwerk verwenden.
    return "D:" if system == "Windows" else "/dev/sr0"


class ToolPaths(BaseModel):
    """Pfade zu externen Tools."""
    ffmpeg: str = "ffmpeg"
    ffprobe: str = "ffprobe"
    ytdlp: str = "yt-dlp"
    dvdauthor: str = "dvdauthor"
    mkisofs: str = "mkisofs"
    growisofs: str = "growisofs"
    cdrecord: str = "cdrecord"


def default_media_directory(kind: str) -> Path:
    """Zentrale Medien-Defaults; bestehende Windows/Linux-Pfade beibehalten."""
    if platform.system() == "Darwin":
        folder = "Music" if kind == "audio" else "Movies"
    else:
        folder = "Downloads" if kind == "download" else "Videos"
    return Path.home() / folder / "RetroDisc"


class DirectorySettings(BaseModel):
    """Verzeichnis-Einstellungen."""
    output_dir: Path = Field(default_factory=lambda: default_media_directory("video"))
    temp_dir: Path = Field(default_factory=lambda: default_media_directory("video") / "_temp")
    download_dir: Path = Field(default_factory=lambda: default_media_directory("download"))

    audio_dir: Path = Field(default_factory=lambda: default_media_directory("audio"))


class SoundSettings(BaseModel):
    """Sound-Einstellungen."""
    play_on_complete: bool = True
    play_on_error: bool = True
    custom_sound_path: str | None = None
    volume: float = 0.8  # 0.0 - 1.0


class ConversionSettings(BaseModel):
    """Standard-Konvertierungseinstellungen."""
    default_video_preset: str = "mp4_h264_1080p"
    default_audio_preset: str = "mp3_320k"
    hardware_acceleration: str = "auto"  # "auto", "cuda", "qsv", "amf", "none"
    max_concurrent_jobs: int = 1
    overwrite_existing: bool = False
    dvd_standard: str = "PAL"  # "PAL" oder "NTSC"


class AISettings(BaseModel):
    """KI-Einstellungen."""
    whisper_model: str = "base"  # "tiny", "base", "small", "medium", "large"
    whisper_language: str | None = None  # None = Auto-Detect
    upscale_model: str = "realesrgan-x4plus"
    upscale_factor: int = 4
    ollama_model: str = "phi3:mini"  # Lokales LLM für den Assistenten
    ollama_host: str = "http://localhost:11434"


class BurnSettings(BaseModel):
    """Brenn-Einstellungen."""
    default_device: str = Field(default_factory=_default_burn_device)
    default_speed: int | None = None  # None = Auto
    verify_after_burn: bool = True
    eject_after_burn: bool = True


class AppSettings(BaseModel):
    """Haupteinstellungen der App."""
    tools: ToolPaths = Field(default_factory=ToolPaths)
    directories: DirectorySettings = Field(default_factory=DirectorySettings)
    sound: SoundSettings = Field(default_factory=SoundSettings)
    conversion: ConversionSettings = Field(default_factory=ConversionSettings)
    ai: AISettings = Field(default_factory=AISettings)
    burn: BurnSettings = Field(default_factory=BurnSettings)
    language: str = "de"
    theme: str = "dark_retro"
    first_run: bool = True
    # None = MediaLibrary's own default (~/.retrodisc/library.db in production).
    # Only ever set to a non-None value in tests, so they never touch the real
    # user database (see RELEASE_AUDIT_STATUS.md, Testisolationsblock).
    library_db_path: Path | None = None

    def ensure_directories(self) -> None:
        """Erstellt alle konfigurierten Verzeichnisse."""
        for _,path in self.directories:
            self.validate_directory(path)
        for _,path in self.directories:
            self.validate_directory(path, create=True)

    @staticmethod
    def validate_directory(path: Path, create: bool = False) -> dict:
        path = Path(path).expanduser()
        if not path.is_absolute():
            raise ValueError(f'Absoluter Verzeichnispfad erforderlich: {path}')
        if path.exists() and not path.is_dir():
            raise ValueError(f'Kein Verzeichnis: {path}')
        if create:
            path.mkdir(parents=True, exist_ok=True)
        probe = path
        while not probe.exists():
            probe = probe.parent
        # An actual short write probe detects ACL/read-only-volume failures too.
        with tempfile.TemporaryFile(dir=probe) as stream:
            stream.write(b'check')
            stream.flush()
        return {'path':str(path), 'exists':path.is_dir(), 'writable':True}

    def save(self, path: Path | None = None) -> None:
        """Speichert Einstellungen als JSON."""
        path = path or self._default_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temp_file:
                temp_path = Path(temp_file.name)
                temp_file.write(self.model_dump_json(indent=2))
                temp_file.flush()
                os.fsync(temp_file.fileno())
            os.replace(temp_path, path)
        except Exception:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
            raise

    @classmethod
    def load(cls, path: Path | None = None) -> "AppSettings":
        """Lädt Einstellungen aus JSON."""
        path = path or cls._default_config_path()
        if path.exists():
            try:
                return cls.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                # Keep the invalid file for diagnosis, but do not prevent startup.
                return cls()
        return cls()

    @staticmethod
    def _default_config_path() -> Path:
        """Standard-Pfad für die Konfigurationsdatei."""
        if platform.system() == "Windows":
            base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "RetroDisc"
        else:
            base = Path.home() / ".config" / "retrodisc"
        return base / "settings.json"
