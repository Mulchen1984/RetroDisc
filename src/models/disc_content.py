"""DiscContent - vereinheitlichtes Modell für den Inhalt einer optischen Disc.

Bewusst getrennt von den generischen Datei-Stream-Modellen in
``src/models/media.py`` (``AudioStream``/``VideoStream``/``SubtitleStream``):
jene beschreiben Streams innerhalb einer bereits vorliegenden Mediendatei,
dieses Modul beschreibt den Inhalt einer Disc *vor* jeder Konvertierung
(Titel, Kapitel, Spuren, Main-Movie-Kennzeichnung). Die Felder unterscheiden
sich absichtlich (z. B. ``forced``/``default`` bei Untertiteln, ``is_main_movie``
bei Titeln) - eine Wiederverwendung der Datei-Stream-Klassen würde diese
Disc-spezifischen Eigenschaften nicht abbilden können.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from src.models.media import DiscType


class DiscContentError(Exception):
    """Eine Disc konnte nicht (vollständig) analysiert werden."""


@dataclass
class DiscChapter:
    """Ein einzelnes Kapitel.

    ``start_seconds``/``duration_seconds`` sind ``None``, wenn nur die
    Existenz bzw. Anzahl der Kapitel real bekannt ist (z. B. aus der DVD-
    IFO-Titeltabelle: ``nr_of_ptts``), ihre Zeitposition aber ohne tiefere
    Struktur-Analyse (VTS_PGCITI/Cell-Tabellen) nicht ermittelt werden kann.
    Ein ``None`` darf NICHT durch eine geschätzte/gleichmäßig verteilte
    Zeit ersetzt werden - das wäre eine erfundene, als echt ausgegebene
    Kapitelposition.
    """
    index: int
    start_seconds: Optional[float] = None
    duration_seconds: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "start_seconds": self.start_seconds,
            "duration_seconds": self.duration_seconds,
        }


@dataclass
class DiscVideoInfo:
    codec: str = ""
    width: int = 0
    height: int = 0
    fps: float = 0.0

    def to_dict(self) -> dict:
        return {"codec": self.codec, "width": self.width, "height": self.height, "fps": self.fps}


@dataclass
class DiscAudioTrack:
    index: int
    codec: str = ""
    language: Optional[str] = None
    channels: int = 0
    bitrate: Optional[int] = None
    default: bool = False

    def to_dict(self) -> dict:
        return {
            "index": self.index, "codec": self.codec, "language": self.language,
            "channels": self.channels, "bitrate": self.bitrate, "default": self.default,
        }


@dataclass
class DiscSubtitleTrack:
    index: int
    language: Optional[str] = None
    format: str = ""
    forced: bool = False
    default: bool = False

    def to_dict(self) -> dict:
        return {
            "index": self.index, "language": self.language, "format": self.format,
            "forced": self.forced, "default": self.default,
        }


@dataclass
class DiscTitle:
    """Ein echter logischer Disc-Titel - NICHT gleichzusetzen mit einer
    einzelnen Datei (weder ``VTS_XX_Y.VOB`` noch ``*.m2ts``). ``duration_seconds``
    und ``size_bytes`` sind ``None``, wenn sie ohne verlässliche Struktur-
    Zuordnung (z. B. mehrere DVD-Titel teilen sich einen Titelsatz) nicht
    eindeutig ermittelt werden können - dann lieber unbekannt als falsch.
    """
    index: int
    name: Optional[str] = None
    duration_seconds: Optional[float] = None
    size_bytes: Optional[int] = None
    chapters: list[DiscChapter] = field(default_factory=list)
    video: Optional[DiscVideoInfo] = None
    audio_tracks: list[DiscAudioTrack] = field(default_factory=list)
    subtitle_tracks: list[DiscSubtitleTrack] = field(default_factory=list)
    is_main_movie: bool = False
    main_movie_confidence: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "name": self.name,
            "duration_seconds": self.duration_seconds,
            "size_bytes": self.size_bytes,
            "chapters": [c.to_dict() for c in self.chapters],
            "video": self.video.to_dict() if self.video else None,
            "audio_tracks": [a.to_dict() for a in self.audio_tracks],
            "subtitle_tracks": [s.to_dict() for s in self.subtitle_tracks],
            "is_main_movie": self.is_main_movie,
            "main_movie_confidence": self.main_movie_confidence,
        }


@dataclass
class DiscContent:
    disc_type: DiscType = DiscType.DVD
    label: str = ""
    device: str = ""
    capacity_bytes: Optional[int] = None
    available_bytes: Optional[int] = None
    titles: list[DiscTitle] = field(default_factory=list)

    @property
    def main_movie(self) -> Optional[DiscTitle]:
        for t in self.titles:
            if t.is_main_movie:
                return t
        return None

    def to_dict(self) -> dict:
        return {
            "disc_type": self.disc_type.value,
            "label": self.label,
            "device": self.device,
            "capacity_bytes": self.capacity_bytes,
            "available_bytes": self.available_bytes,
            "titles": [t.to_dict() for t in self.titles],
        }
