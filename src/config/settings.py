"""RetroDisc Settings — App-Einstellungen."""

from __future__ import annotations

from pathlib import Path
from pydantic import BaseModel, Field


class ToolPaths(BaseModel):
    """Pfade zu externen Tools."""
    ffmpeg: str = "ffmpeg"
    ffprobe: str = "ffprobe"
    ytdlp: str = "yt-dlp"
    dvdauthor: str = "dvdauthor"
    mkisofs: str = "mkisofs"
    growisofs: str = "growisofs"
    cdrecord: str = "cdrecord"


class DirectorySettings(BaseModel):
    """Verzeichnis-Einstellungen."""
    output_dir: Path = Field(default_factory=lambda: Path.home() / "Videos" / "RetroDisc")
    temp_dir: Path = Field(default_factory=lambda: Path.home() / "Videos" / "RetroDisc" / "_temp")
    download_dir: Path = Field(default_factory=lambda: Path.home() / "Downloads" / "RetroDisc")


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
    default_device: str = "/dev/sr0"  # Linux/Mac, Windows: "D:"
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

    def ensure_directories(self) -> None:
        """Erstellt alle konfigurierten Verzeichnisse."""
        self.directories.output_dir.mkdir(parents=True, exist_ok=True)
        self.directories.temp_dir.mkdir(parents=True, exist_ok=True)
        self.directories.download_dir.mkdir(parents=True, exist_ok=True)

    def save(self, path: Path | None = None) -> None:
        """Speichert Einstellungen als JSON."""
        path = path or self._default_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2))

    @classmethod
    def load(cls, path: Path | None = None) -> "AppSettings":
        """Lädt Einstellungen aus JSON."""
        path = path or cls._default_config_path()
        if path.exists():
            return cls.model_validate_json(path.read_text())
        return cls()

    @staticmethod
    def _default_config_path() -> Path:
        """Standard-Pfad für die Konfigurationsdatei."""
        import platform
        if platform.system() == "Windows":
            base = Path.home() / "AppData" / "Local" / "RetroDisc"
        else:
            base = Path.home() / ".config" / "retrodisc"
        return base / "settings.json"
