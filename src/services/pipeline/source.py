"""Unified source model + non-destructive detection.

Classifies a path/device into a SourceKind and gathers safe, read-only facts.
No mounting, no writes, no hardware polling — an optical device is reported as a
source without touching the drive. ISO support is declared honestly (inspect
only; mounting is not implemented here).
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".m2ts", ".ts", ".vob", ".wmv", ".webm", ".mpg", ".mpeg", ".m4v"}
_DRIVE_LETTER = re.compile(r"^[A-Za-z]:[\\/]?$")


class SourceKind(str, Enum):
    FILE = "file"
    DVD_FOLDER = "dvd_folder"
    BLURAY_FOLDER = "bluray_folder"
    ISO = "iso"
    OPTICAL_DISC = "optical_disc"
    UNKNOWN = "unknown"


@dataclass
class SourceMedia:
    kind: SourceKind = SourceKind.UNKNOWN
    path: str = ""                      # Datei/Ordner/ISO
    device: str = ""                    # optisches Laufwerk (Buchstabe / /dev/...)
    label: str = ""
    fingerprint: str = ""
    media_kind: str = ""                # video | disc | image | unknown
    size: int = 0
    read_only: bool = True
    available: bool = True
    discovered_at: Optional[float] = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = {k: (v.value if isinstance(v, Enum) else v) for k, v in self.__dict__.items()}
        return d


def iso_capabilities() -> dict:
    """Honest ISO capability report (no mounting implemented here)."""
    return {"inspect": True, "detect_type": True, "mount": False, "extract": False,
            "note": "ISO-Mounting/-Extraktion nicht implementiert; nur Erkennung/Inspektion."}


def _looks_like_device(value: str) -> bool:
    v = (value or "").strip()
    return bool(_DRIVE_LETTER.match(v) or v.startswith("/dev/"))


def _dir_size(root: Path, *, limit: int = 100000) -> int:
    total = 0
    count = 0
    for p in root.rglob("*"):
        try:
            if p.is_file():
                total += p.stat().st_size
                count += 1
                if count >= limit:
                    break
        except OSError:
            continue
    return total


class SourceDetectionService:
    def __init__(self, *, now=time.time):
        self._now = now

    def detect(self, target: str) -> SourceMedia:
        media = SourceMedia(discovered_at=self._now())
        raw = str(target or "").strip()
        if not raw:
            media.available = False
            media.warnings.append("Leerer Quellpfad.")
            return media

        # Optisches Laufwerk (kein Hardwarezugriff hier).
        if _looks_like_device(raw):
            media.kind = SourceKind.OPTICAL_DISC
            media.device = raw
            media.media_kind = "disc"
            media.available = True
            media.warnings.append("Optisches Laufwerk erkannt; Medienzustand nicht ohne Laufwerksabfrage bekannt.")
            return media

        path = Path(raw)
        try:
            resolved = path.resolve()           # Symlinks sicher auflösen
        except OSError:
            resolved = path
        media.path = str(resolved)

        if not resolved.exists():
            media.available = False
            media.warnings.append("Pfad existiert nicht.")
            return media
        if not os.access(str(resolved), os.R_OK):
            media.available = False
            media.warnings.append("Pfad nicht lesbar.")
            return media

        if resolved.is_dir():
            media.label = resolved.name
            if (resolved / "VIDEO_TS" / "VIDEO_TS.IFO").is_file() or \
               (resolved / "VIDEO_TS.IFO").is_file():
                media.kind, media.media_kind = SourceKind.DVD_FOLDER, "disc"
            elif (resolved / "BDMV" / "index.bdmv").is_file() or (resolved / "index.bdmv").is_file():
                media.kind, media.media_kind = SourceKind.BLURAY_FOLDER, "disc"
            else:
                media.kind, media.media_kind = SourceKind.UNKNOWN, "unknown"
                media.warnings.append("Verzeichnis ist weder VIDEO_TS noch BDMV.")
            media.size = _dir_size(resolved)
            return media

        # Datei
        media.label = resolved.name
        try:
            media.size = resolved.stat().st_size
        except OSError:
            media.size = 0
        suffix = resolved.suffix.lower()
        if suffix == ".iso":
            media.kind, media.media_kind = SourceKind.ISO, "image"
        elif suffix in VIDEO_EXTS:
            media.kind, media.media_kind = SourceKind.FILE, "video"
        else:
            media.kind, media.media_kind = SourceKind.UNKNOWN, "unknown"
            media.warnings.append(f"Unbekannter Dateityp: {suffix or '(kein Suffix)'}")
        return media
