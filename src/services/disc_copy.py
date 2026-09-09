"""Explicit, testable disc-copy state machine (image-based copy).

Pure control logic: no real drive I/O here, so it can be exhaustively unit
tested. It enforces the safety-critical guarantees of a copy:

* the source is never a write target,
* the target medium must be freshly, uniquely detected (no stale cache),
* re-inserting the source instead of a blank is rejected,
* wrong / non-writable / too-small media is rejected,
* cancel works in every non-terminal phase,
* failures always leave the machine in a defined terminal state.

Real burning/reading is done elsewhere (DiscTools); this machine sequences and
guards those steps and tracks the temporary image for cleanup.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from src.core.errors import DriveError, MediaError


class CopyState(Enum):
    SOURCE_DETECTED = "source_detected"
    SOURCE_ANALYSIS = "source_analysis"
    READING_SOURCE = "reading_source"
    IMAGE_CREATED = "image_created"
    EJECT_SOURCE = "eject_source"
    WAIT_FOR_TARGET = "wait_for_target"
    TARGET_DETECTED = "target_detected"
    TARGET_VALIDATION = "target_validation"
    READY_TO_BURN = "ready_to_burn"
    BURNING = "burning"
    VERIFYING = "verifying"
    DONE = "done"
    CANCELLED = "cancelled"
    FAILED = "failed"


TERMINAL = {CopyState.DONE, CopyState.CANCELLED, CopyState.FAILED}

# Allowed forward transitions of the happy path.
_ALLOWED: dict[CopyState, set[CopyState]] = {
    CopyState.SOURCE_DETECTED: {CopyState.SOURCE_ANALYSIS},
    CopyState.SOURCE_ANALYSIS: {CopyState.READING_SOURCE},
    CopyState.READING_SOURCE: {CopyState.IMAGE_CREATED},
    CopyState.IMAGE_CREATED: {CopyState.EJECT_SOURCE},
    CopyState.EJECT_SOURCE: {CopyState.WAIT_FOR_TARGET},
    CopyState.WAIT_FOR_TARGET: {CopyState.TARGET_DETECTED},
    CopyState.TARGET_DETECTED: {CopyState.TARGET_VALIDATION},
    CopyState.TARGET_VALIDATION: {CopyState.READY_TO_BURN},
    CopyState.READY_TO_BURN: {CopyState.BURNING},
    CopyState.BURNING: {CopyState.VERIFYING, CopyState.DONE},
    CopyState.VERIFYING: {CopyState.DONE},
}


@dataclass
class CopyContext:
    source: Optional[dict] = None
    source_device: str = ""
    source_ejected: bool = False
    image_path: Optional[str] = None
    image_size: int = 0
    target: Optional[dict] = None
    verify: bool = True
    temp_paths: list[str] = field(default_factory=list)
    error: Optional[dict] = None


class DiscCopyMachine:
    def __init__(self, source: dict, *, verify: bool = True):
        if not source or not source.get("present"):
            raise MediaError("Keine lesbare Quelldisc erkannt.")
        if not source.get("readable", True):
            raise MediaError("Die Quelldisc ist nicht lesbar.")
        self.state = CopyState.SOURCE_DETECTED
        self.ctx = CopyContext(source=source, source_device=source.get("device", ""),
                               verify=verify)

    # ── transition core ─────────────────────────────────────────────────
    def _to(self, target: CopyState):
        if self.state in TERMINAL:
            raise DriveError(f"Kopiervorgang bereits beendet ({self.state.value}).")
        if target not in _ALLOWED.get(self.state, set()):
            raise DriveError(f"Ungültiger Schritt {self.state.value} → {target.value}.")
        self.state = target
        return self

    # ── happy path steps ────────────────────────────────────────────────
    def analyze_source(self):
        return self._to(CopyState.SOURCE_ANALYSIS)

    def read_source(self):
        return self._to(CopyState.READING_SOURCE)

    def image_created(self, path: str, size_bytes: int):
        self._to(CopyState.IMAGE_CREATED)
        if size_bytes <= 0:
            error = MediaError("Erstelltes Abbild ist leer.")
            self.fail(error)
            raise error
        self.ctx.image_path = str(path)
        self.ctx.image_size = int(size_bytes)
        if str(path) not in self.ctx.temp_paths:
            self.ctx.temp_paths.append(str(path))
        return self

    def eject_source(self):
        self._to(CopyState.EJECT_SOURCE)
        self.ctx.source_ejected = True
        return self

    def wait_for_target(self):
        return self._to(CopyState.WAIT_FOR_TARGET)

    def detect_target(self, target: dict):
        """Fresh, explicit target detection. Rejects the re-inserted source."""
        self._to(CopyState.TARGET_DETECTED)
        if not target or not target.get("present"):
            self.state = CopyState.WAIT_FOR_TARGET   # bleib wartend, kein Fehlerzustand
            raise MediaError("Kein Medium im Ziel-Laufwerk erkannt.")
        # Same physical drive as the source is only allowed once the source was ejected.
        if target.get("device") == self.ctx.source_device and not self.ctx.source_ejected:
            self.state = CopyState.WAIT_FOR_TARGET
            raise MediaError("Bitte zuerst die Quelldisc entnehmen.")
        # Re-inserted source instead of a blank: readable, not blank, matches source.
        if self._looks_like_source(target):
            self.state = CopyState.WAIT_FOR_TARGET
            raise MediaError("Das ist die Quelldisc – bitte einen leeren Rohling einlegen.")
        self.ctx.target = target
        return self

    def validate_target(self):
        self._to(CopyState.TARGET_VALIDATION)
        target = self.ctx.target or {}
        if not target.get("writable", False):
            self._reject(MediaError("Das Zielmedium ist nicht beschreibbar."))
        if not (target.get("blank") or target.get("rewritable")):
            self._reject(MediaError("Das Zielmedium ist nicht leer und nicht wiederbeschreibbar."))
        capacity = int(target.get("capacity_bytes") or 0)
        if capacity and self.ctx.image_size and capacity < self.ctx.image_size:
            self._reject(MediaError(
                f"Das Zielmedium ist zu klein ({capacity} < {self.ctx.image_size} Bytes)."))
        return self

    def ready_to_burn(self):
        return self._to(CopyState.READY_TO_BURN)

    def burn(self):
        return self._to(CopyState.BURNING)

    def verifying(self):
        return self._to(CopyState.VERIFYING)

    def done(self):
        if self.state == CopyState.BURNING and self.ctx.verify:
            raise DriveError("Verifikation ist aktiviert – zuerst 'verifying'.")
        self._to(CopyState.DONE)
        return self

    # ── terminal from anywhere ──────────────────────────────────────────
    def cancel(self):
        """Cancel in every non-terminal phase; image stays in temp_paths for cleanup."""
        if self.state in TERMINAL:
            return self
        self.state = CopyState.CANCELLED
        return self

    def fail(self, error):
        if self.state in TERMINAL:
            return self
        self.state = CopyState.FAILED
        self.ctx.error = error.to_dict() if hasattr(error, "to_dict") else {"error": str(error)}
        return self

    # ── helpers ─────────────────────────────────────────────────────────
    def _reject(self, error: MediaError):
        # Validation failure returns to waiting for a suitable target, not FAILED:
        # the user can simply insert a correct blank. App stays in a valid state.
        self.state = CopyState.WAIT_FOR_TARGET
        self.ctx.target = None
        raise error

    def _looks_like_source(self, target: dict) -> bool:
        source = self.ctx.source or {}
        if target.get("blank"):
            return False
        if not target.get("readable", False):
            return False
        same_capacity = (source.get("capacity_bytes") and
                         source.get("capacity_bytes") == target.get("capacity_bytes"))
        same_label = source.get("label") and source.get("label") == target.get("label")
        same_profile = source.get("profile") and source.get("profile") == target.get("profile")
        return bool(same_capacity and (same_label or same_profile))

    @property
    def cleanup_paths(self) -> list[str]:
        return list(self.ctx.temp_paths)

    @property
    def finished(self) -> bool:
        return self.state in TERMINAL
