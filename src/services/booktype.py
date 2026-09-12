"""DVD book type / bitsetting: capability detection, args, result parsing.

Windows-only, no DRM. Book type (a.k.a. bitsetting) rewrites the *media
descriptor* of writable DVD+ media so standalone players treat it as DVD-ROM;
it is unrelated to any copy protection. Only offered when the media family and
the burner/backend actually support it — never assumed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal, Optional, Union

BookTypeSetting = Literal["automatic", "native", "dvd_rom"]


class BookType(Enum):
    """Zentrale Book-Type-Definition - keine frei verteilten String-Vergleiche.

    Werte identisch zu ``BookTypeSetting`` gehalten, damit bestehende
    Aufrufer/Tests, die rohe Strings ("automatic"/"native"/"dvd_rom")
    übergeben, unverändert weiterfunktionieren (siehe ``_as_book_type``).
    """
    AUTO = "automatic"
    NATIVE = "native"
    DVD_ROM = "dvd_rom"


def _as_book_type(value: Union["BookType", str, None]) -> "BookType":
    if isinstance(value, BookType):
        return value
    return BookType(value or "automatic")


# Media families that support bitsetting. The DVD- (dash) family does not.
BITSETTABLE = {"DVD+R", "DVD+RW", "DVD+R DL"}


def classify_media(profile: str) -> str:
    """Normalise a dvd+rw-mediainfo profile string to a known media family."""
    p = (profile or "").upper()
    checks = [
        ("DVD+R DL", ("DVD+R" in p and ("DL" in p or "DUAL" in p or "DOUBLE" in p))),
        ("DVD+RW", "DVD+RW" in p),
        ("DVD+R", "DVD+R" in p),
        ("DVD-ROM", "DVD-ROM" in p),      # vor der DVD-R-Familie: enthält "DVD-R"
        ("DVD-RW", "DVD-RW" in p),
        ("DVD-R DL", ("DVD-R" in p and ("DL" in p or "DUAL" in p))),
        ("DVD-R", "DVD-R" in p),
        ("BD-RE", "BD-RE" in p),
        ("BD-R", "BD-R" in p),
        ("BD-ROM", "BD-ROM" in p),
    ]
    for name, matched in checks:
        if matched:
            return name
    return "unknown"


def supports_bitsetting(media_type: str) -> bool:
    return media_type in BITSETTABLE


def bitsetting_available(media_type: str, tool_available: bool) -> bool:
    """Capability = passendes Medium UND vorhandenes Backend. Nie blind annehmen."""
    return bool(tool_available) and supports_bitsetting(media_type)


def booktype_options(media_type: str, tool_available: bool) -> list[BookTypeSetting]:
    """Which book-type choices to offer for this media/backend (else only automatic)."""
    if not bitsetting_available(media_type, tool_available):
        return ["automatic"]
    return ["automatic", "native", "dvd_rom"]


def booktype_command(tool: str, device: str, setting: Union[BookType, BookTypeSetting],
                     media_type: str) -> Optional[list[str]]:
    """Args to set the book type before/around burning, or None if nothing to do.

    ``NATIVE``/``AUTO`` ohne Bitsetting-Fähigkeit lassen den Medien-Deskriptor
    unverändert. Nur ``DVD_ROM`` (bzw. ``AUTO`` auf einem bitsettbaren Medium,
    siehe ``src/core/disc.py::DiscTools._apply_book_type``) auf einem
    bitsettbaren Medium ergibt einen echten Befehl.
    """
    if _as_book_type(setting) == BookType.DVD_ROM and supports_bitsetting(media_type):
        return [tool, "-dvd-rom-spec", "-media", device]
    return None


def parse_book_type(output: str) -> str:
    """Read the actual book type back from dvd+rw-booktype / mediainfo output."""
    if not output:
        return "unknown"
    match = re.search(r"(?:legacy\s+)?book\s*type\s*[:=]?\s*\"?([A-Za-z0-9+\-]+)", output, re.I)
    return match.group(1).strip() if match else "unknown"


def describe_media(disc_info: dict, tool_available: bool) -> dict:
    """Enrich a DiscTools.get_disc_info() dict with media family + book-type options.

    Pure: derives everything from the already-probed profile/flags, so it is
    testable without hardware and never claims unsupported capabilities.
    """
    info = dict(disc_info or {})
    media_type = classify_media(info.get("profile") or info.get("type") or "")
    info["media_type"] = media_type
    info["bitsetting_supported"] = supports_bitsetting(media_type)
    info["bitsetting_available"] = bitsetting_available(media_type, tool_available)
    info["book_type_options"] = booktype_options(media_type, tool_available)
    return info


@dataclass
class BurnResult:
    """Structured burn outcome; only fields with real values are filled."""
    media_type: str = "unknown"
    book_type_requested: BookTypeSetting = "automatic"
    book_type_actual: str = "unknown"
    burn_speed: Optional[str] = None
    written_size: Optional[int] = None
    verify_result: str = "NOT_AVAILABLE"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "media_type": self.media_type,
            "book_type_requested": self.book_type_requested,
            "book_type_actual": self.book_type_actual,
            "burn_speed": self.burn_speed,
            "written_size": self.written_size,
            "verify_result": self.verify_result,
            "warnings": list(self.warnings),
        }
