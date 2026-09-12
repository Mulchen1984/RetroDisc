"""Strukturiertes Ergebnis des kanonischen Brennpfads (``DiscTools.burn_iso``).

Trennt bewusst drei unabhängige Erfolgs-/Fehlerachsen, die vorher vermischt
oder gar nicht sichtbar waren: Brennen, Book Type, Verifikation. Eine
erfolgreiche Brennung behauptet nie automatisch, dass eine angeforderte
Book-Type-Änderung ebenfalls erfolgreich war - siehe
P0_BURN_PIPELINE_BOOKTYPE.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from src.services.verify import VerifyResult


class BookTypeStatus(Enum):
    NOT_REQUESTED = "not_requested"      # NATIVE: keine Änderung gewünscht
    NOT_APPLICABLE = "not_applicable"     # Medium/Disc-Typ unterstützt Bitsetting grundsätzlich nicht (falsche Familie oder Blu-ray)
    NOT_SUPPORTED = "not_supported"        # Medium wäre geeignet, aber Backend/Werkzeug fehlt
    APPLIED = "applied"                     # erfolgreich gesetzt
    FAILED = "failed"                        # Versuch unternommen, Werkzeug-Aufruf schlug fehl


@dataclass
class BurnOutcome:
    """Ergebnis von ``DiscTools.burn_iso`` - dem einen kanonischen Brennpfad."""
    burn_success: bool = False
    error: Optional[str] = None
    device: str = ""
    disc_type: str = ""
    media_type: str = "unknown"
    book_type_requested: str = "automatic"
    book_type_status: BookTypeStatus = BookTypeStatus.NOT_REQUESTED
    book_type_actual: Optional[str] = None
    book_type_warning: Optional[str] = None
    verify: VerifyResult = field(default_factory=VerifyResult)
    written_size: Optional[int] = None
    burn_speed: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "burn_success": self.burn_success,
            "error": self.error,
            "device": self.device,
            "disc_type": self.disc_type,
            "media_type": self.media_type,
            "book_type_requested": self.book_type_requested,
            "book_type_status": self.book_type_status.value,
            "book_type_actual": self.book_type_actual,
            "book_type_warning": self.book_type_warning,
            "verify": self.verify.to_dict(),
            "written_size": self.written_size,
            "burn_speed": self.burn_speed,
        }
