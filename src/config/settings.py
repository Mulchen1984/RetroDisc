"""RetroDisc Settings — App-Einstellungen."""

from __future__ import annotations

import os
import platform
import tempfile
from pathlib import Path

from pydantic import BaseModel, Field, field_validator


def _default_burn_device() -> str:
    """Return the platform-appropriate default optical drive."""
    return "D:" if platform.system() == "Windows" else "/dev/sr0"


class ToolPaths(BaseModel):
    """Pfade zu externen Tools."""
    ffmpeg: str = "ffmpeg"
    ffprobe: str = "ffprobe"
    ytdlp: str = "yt-dlp"
    dvdauthor: str = "dvdauthor"
    mkisofs: str = "mkisofs"
    growisofs: str = "growisofs"
    cdrecord: str = "cdrecord"


def data_root() -> Path:
    """Persistent user data, independent of cwd, EXE and _MEIPASS."""
    return Path.home() / "RetroDisc"


def resolve_user_path(value: Path | str) -> Path:
    text = os.path.expandvars(str(value)).strip()
    if not text:
        raise ValueError("Bitte einen Ordner angeben.")
    path = Path(text).expanduser()
    if path.anchor and not path.is_absolute():
        raise ValueError(f"Bitte einen vollständigen Pfad angeben: {text}")
    return (path if path.is_absolute() else data_root() / path).resolve()


def ensure_writable_directory(path: Path) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=path):
            pass
    except OSError as exc:
        raise OSError(f"Ordner nicht beschreibbar: {path}. Bitte in den Einstellungen ein anderes Ziel wählen. ({exc})") from exc


#: Die Unterordner unter dem Medienordner. Ein Eintrag hier reicht:
#: ``DirectorySettings.derived`` und ``ensure_directories`` lesen beide aus
#: dieser Tabelle, damit Struktur und Anlage nicht auseinanderlaufen.
MEDIA_SUBFOLDERS = {
    "download_dir": "Downloads",
    "output_dir": "Videos",
    "temp_dir": "Temp",
    "log_dir": "Logs",
}

#: Die Bibliotheksdatenbank liegt als Datei neben den Ordnern, nicht darin.
LIBRARY_DB_NAME = "library.db"


class DirectorySettings(BaseModel):
    """Visible persistent media folders; explicit existing settings are retained.

    ``media_root`` ist der eine Ordner, den der Nutzer waehlt. Die vier
    Unterordner und die Bibliotheksdatenbank leiten sich daraus ab, bleiben
    aber einzeln einstellbar: wer sie bewusst woanders hin gelegt hat, behaelt
    sie, bis er den Medienordner ausdruecklich neu setzt.
    """
    media_root: Path = Field(default_factory=data_root)
    output_dir: Path = Field(default_factory=lambda: data_root() / "Videos")
    temp_dir: Path = Field(default_factory=lambda: data_root() / "Temp")
    download_dir: Path = Field(default_factory=lambda: data_root() / "Downloads")
    log_dir: Path = Field(default_factory=lambda: data_root() / "Logs")
    library_db: Path = Field(
        default_factory=lambda: data_root() / LIBRARY_DB_NAME)

    @field_validator("media_root", "output_dir", "temp_dir", "download_dir",
                     "log_dir", "library_db", mode="before")
    @classmethod
    def normalize_path(cls, value):
        return str(resolve_user_path(value))

    @classmethod
    def derived(cls, root: Path | str) -> "DirectorySettings":
        """Leitet die vollstaendige Ordnerstruktur aus *root* ab."""
        resolved = resolve_user_path(root)
        folders = {key: resolved / name for key, name in MEDIA_SUBFOLDERS.items()}
        return cls(media_root=resolved,
                   library_db=resolved / LIBRARY_DB_NAME,
                   **folders)

    def managed_directories(self) -> list[Path]:
        """Alle Ordner, die die Anwendung anlegen und beschreiben muss."""
        return [getattr(self, key) for key in MEDIA_SUBFOLDERS]


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
        """Erstellt alle konfigurierten Verzeichnisse.

        Der Logordner kommt aus derselben Tabelle wie die uebrigen. Vorher
        stand er hier fest auf ``data_root()/"Logs"`` und wanderte deshalb
        nicht mit, wenn der Nutzer den Medienordner verlegte.
        """
        for path in self.directories.managed_directories():
            ensure_writable_directory(path)

    def set_media_root(self, root: Path | str) -> None:
        """Setzt den Medienordner und legt die Struktur darunter neu fest.

        Ausdruecklicher Aufruf, keine Ableitung im Hintergrund: einzeln
        eingestellte Ordner werden hier bewusst ersetzt, und der Nutzer hat
        das mit der Auswahl des Medienordners genau so verlangt.
        """
        self.directories = DirectorySettings.derived(root)
        self.ensure_directories()

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
                settings = cls.model_validate_json(path.read_text(encoding="utf-8"))
                legacy = {"output_dir": Path.home() / "Videos" / "RetroDisc",
                          "temp_dir": Path.home() / "Videos" / "RetroDisc" / "_temp",
                          "download_dir": Path.home() / "Downloads" / "RetroDisc"}
                defaults = DirectorySettings()
                for key, old in legacy.items():
                    if getattr(settings.directories, key) == old:
                        setattr(settings.directories, key, getattr(defaults, key))
                return settings
            except (OSError, ValueError):
                # Keep the invalid file for diagnosis, but do not prevent startup.
                return cls()
        return cls()

    @staticmethod
    def _default_config_path() -> Path:
        """Standard-Pfad für die Konfigurationsdatei."""
        if platform.system() == "Windows":
            base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "RetroDisc"
        else:
            base = Path.home() / ".config" / "retrodisc"
        return base / "settings.json"
