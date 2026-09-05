"""RetroDisc Settings — App-Einstellungen."""

from __future__ import annotations

import os
import platform
import tempfile
from pathlib import Path

from pydantic import BaseModel, Field


def _default_burn_device() -> str:
    """Return the platform-appropriate default optical drive."""
    return "D:" if platform.system() == "Windows" else "/dev/sr0"


def _default_media_root() -> Path:
    """Return the single user-visible root for RetroDisc media results."""
    return Path.home() / "Videos" / "RetroDisc"


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
    """Verzeichnis-Einstellungen für den nachvollziehbaren Medien-Workflow.

    Alle benutzerrelevanten Ergebnisse liegen standardmäßig unter genau einem
    Stammordner: ``~/Videos/RetroDisc``. Die nummerierten Unterordner bilden
    den typischen Arbeitsablauf ab und verhindern, dass Ergebnisse unbemerkt
    neben Quelldateien oder im allgemeinen Download-Ordner landen.
    """

    media_root: Path = Field(default_factory=_default_media_root)
    download_dir: Path = Field(
        default_factory=lambda: _default_media_root() / "01_Quellen" / "Downloads"
    )
    rip_dir: Path = Field(
        default_factory=lambda: _default_media_root() / "01_Quellen" / "Rips"
    )
    output_dir: Path = Field(
        default_factory=lambda: _default_media_root() / "02_Konvertiert"
    )
    edited_dir: Path = Field(
        default_factory=lambda: _default_media_root() / "03_Bearbeitet"
    )
    disc_dir: Path = Field(
        default_factory=lambda: _default_media_root() / "04_Disc"
    )
    temp_dir: Path = Field(
        default_factory=lambda: _default_media_root() / "_temp"
    )

    @property
    def trim_dir(self) -> Path:
        return self.edited_dir / "Geschnitten"

    @property
    def merge_dir(self) -> Path:
        return self.edited_dir / "Zusammengefuegt"

    @property
    def upscale_dir(self) -> Path:
        return self.edited_dir / "Hochskaliert"

    @property
    def interpolate_dir(self) -> Path:
        return self.edited_dir / "Framerate"

    @property
    def subtitle_dir(self) -> Path:
        return self.edited_dir / "Untertitel"

    @property
    def highlights_dir(self) -> Path:
        return self.edited_dir / "Highlights"

    @property
    def dvd_dir(self) -> Path:
        return self.disc_dir / "DVD"

    @property
    def iso_dir(self) -> Path:
        return self.disc_dir / "ISO"

    def ensure_directories(self) -> None:
        """Create the complete workflow tree."""
        for path in (
            self.media_root,
            self.download_dir,
            self.rip_dir,
            self.output_dir,
            self.edited_dir,
            self.trim_dir,
            self.merge_dir,
            self.upscale_dir,
            self.interpolate_dir,
            self.subtitle_dir,
            self.highlights_dir,
            self.disc_dir,
            self.dvd_dir,
            self.iso_dir,
            self.temp_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def migrate_legacy_defaults(self) -> bool:
        """Move only historical *default settings* to the workflow layout.

        Custom user paths are deliberately left untouched. This only changes
        values that exactly match RetroDisc's former defaults.
        """
        changed = False
        old_output = Path.home() / "Videos" / "RetroDisc"
        old_download = Path.home() / "Downloads" / "RetroDisc"
        root = _default_media_root()

        if self.output_dir == old_output:
            self.output_dir = root / "02_Konvertiert"
            changed = True
        if self.download_dir == old_download:
            self.download_dir = root / "01_Quellen" / "Downloads"
            changed = True

        return changed


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

    def ensure_directories(self) -> None:
        """Erstellt alle konfigurierten Verzeichnisse."""
        self.directories.ensure_directories()

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
        """Lädt Einstellungen aus JSON und migriert nur alte Standardpfade."""
        path = path or cls._default_config_path()
        if path.exists():
            try:
                settings = cls.model_validate_json(path.read_text(encoding="utf-8"))
                if settings.directories.migrate_legacy_defaults():
                    settings.ensure_directories()
                    settings.save(path)
                return settings
            except (OSError, ValueError):
                # Keep the invalid file for diagnosis, but do not prevent startup.
                return cls()
        return cls()

    @staticmethod
    def _default_config_path() -> Path:
        """Standard-Pfad für die Konfigurationsdatei."""
        if platform.system() == "Windows":
            base = Path.home() / "AppData" / "Local" / "RetroDisc"
        else:
            base = Path.home() / ".config" / "retrodisc"
        return base / "settings.json"
