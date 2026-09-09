"""Structured verification results for ISO creation and burning.

Pure aggregation logic: individual checks (size, hash, structure, book type)
are combined into one of four honest verdicts. No I/O here so it is fully unit
tested; the real byte/hash reading stays in DiscTools and feeds these checks.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

PASS = "PASS"
PASS_WITH_WARNINGS = "PASS_WITH_WARNINGS"
FAIL = "FAIL"
NOT_AVAILABLE = "NOT_AVAILABLE"


@dataclass
class Check:
    name: str
    ok: Optional[bool]                 # True/False, or None = konnte nicht geprüft werden
    detail: str = ""
    severity: str = "error"            # 'error' | 'warning' | 'info'

    def to_dict(self) -> dict:
        return {"name": self.name, "ok": self.ok, "detail": self.detail, "severity": self.severity}


@dataclass
class VerifyResult:
    status: str = NOT_AVAILABLE
    checks: list[Check] = field(default_factory=list)
    message: str = ""

    def to_dict(self) -> dict:
        return {"status": self.status, "message": self.message,
                "checks": [c.to_dict() for c in self.checks]}

    @classmethod
    def from_checks(cls, checks: list[Check], *, message: str = "") -> "VerifyResult":
        checks = [c for c in checks if c is not None]
        if not checks or all(c.ok is None for c in checks):
            return cls(NOT_AVAILABLE, checks, message or "Keine Prüfung möglich.")
        failed = [c for c in checks if c.ok is False and c.severity == "error"]
        warned = [c for c in checks if (c.ok is False and c.severity == "warning") or c.ok is None]
        if failed:
            status, text = FAIL, "; ".join(c.detail or c.name for c in failed)
        elif warned:
            status, text = PASS_WITH_WARNINGS, "; ".join(c.detail or c.name for c in warned)
        else:
            status, text = PASS, "Alle Prüfungen bestanden."
        return cls(status, checks, message or text)


# ── pure checks ──────────────────────────────────────────────────────────────
def size_check(expected: Optional[int], actual: Optional[int], *, tolerance: int = 0) -> Check:
    if not expected or actual is None:
        return Check("size", None, "Größe nicht vergleichbar.")
    if actual < expected:
        return Check("size", False, f"Ausgabe kürzer als Quelle ({actual} < {expected} Bytes).")
    if actual - expected > tolerance:
        return Check("size", False, f"Ausgabe größer als erwartet ({actual} > {expected} Bytes).",
                     severity="warning")
    return Check("size", True, f"{actual} Bytes wie erwartet.")


def hash_check(expected: Optional[str], actual: Optional[str]) -> Check:
    if not expected or not actual:
        return Check("hash", None, "Prüfsumme nicht verfügbar.")
    return (Check("hash", True, "Prüfsumme identisch.") if expected == actual
            else Check("hash", False, "Prüfsummen unterscheiden sich."))


def structure_check(expected_paths, actual_paths) -> Check:
    if not expected_paths and not actual_paths:
        return Check("structure", None, "Keine Struktur zum Vergleich.")
    expected, actual = set(expected_paths or []), set(actual_paths or [])
    missing, extra = expected - actual, actual - expected
    if missing:
        return Check("structure", False, f"{len(missing)} Datei(en) fehlen auf dem Ziel.")
    if extra:
        return Check("structure", False, f"{len(extra)} zusätzliche Datei(en) auf dem Ziel.",
                     severity="warning")
    return Check("structure", True, f"{len(expected)} Dateien vollständig.")


def booktype_check(requested: str, actual: str) -> Check:
    if not requested or requested == "automatic":
        return Check("book_type", None, "Kein Book Type angefordert.", severity="info")
    if not actual or actual == "unknown":
        return Check("book_type", None, "Book Type konnte nicht zurückgelesen werden.", severity="warning")
    target = "DVD-ROM" if requested == "dvd_rom" else requested
    return (Check("book_type", True, f"Book Type {actual} gesetzt.") if actual.upper() == target.upper()
            else Check("book_type", False, f"Book Type {actual} statt {target}.", severity="warning"))
