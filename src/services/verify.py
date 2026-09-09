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


# ── real disc-structure comparison (VIDEO_TS / BDMV) ─────────────────────────
# Required files mark a valid layout; recommended files only warn if absent.
DVD_REQUIRED = ("VIDEO_TS/VIDEO_TS.IFO",)
DVD_RECOMMENDED = ("VIDEO_TS/VIDEO_TS.BUP",)
BD_REQUIRED = ("BDMV/index.bdmv", "BDMV/MovieObject.bdmv")
BD_RECOMMENDED = ("BDMV/PLAYLIST", "BDMV/STREAM")


def scan_tree(root, *, small_file_bytes: int = 1_048_576) -> dict:
    """Map relative POSIX path -> {'size', 'sha'?} for every file under root."""
    from src.services.fingerprint import build_structure
    tree = {}
    for entry in build_structure(root, small_file_bytes=small_file_bytes).get("files", []):
        tree[entry["path"]] = {"size": entry.get("size", 0), "sha": entry.get("sha")}
    return tree


def detect_disc_kind(tree: dict) -> str:
    lowered = {p.lower() for p in tree}
    if "video_ts/video_ts.ifo" in lowered:
        return "dvd"
    if "bdmv/index.bdmv" in lowered:
        return "bd"
    return "unknown"


def _present(tree: dict, rel: str) -> bool:
    rel = rel.lower()
    # A directory is "present" if any file lives under it.
    return any(p.lower() == rel or p.lower().startswith(rel + "/") for p in tree)


def layout_checks(tree: dict, kind: str) -> list[Check]:
    required, recommended = {
        "dvd": (DVD_REQUIRED, DVD_RECOMMENDED),
        "bd": (BD_REQUIRED, BD_RECOMMENDED),
    }.get(kind, ((), ()))
    checks: list[Check] = []
    for rel in required:
        checks.append(Check(f"layout:{rel}", _present(tree, rel),
                            "" if _present(tree, rel) else f"Pflichtdatei fehlt: {rel}"))
    for rel in recommended:
        ok = _present(tree, rel)
        checks.append(Check(f"layout:{rel}", ok if ok else False,
                            "" if ok else f"Empfohlene Struktur fehlt: {rel}",
                            severity="info" if ok else "warning"))
    return checks


def compare_trees(expected: dict, actual: dict, *, compare_hash: bool = False) -> list[Check]:
    """Compare two scanned trees: missing (error), extra (warning), size/hash mismatch."""
    checks: list[Check] = []
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    checks.append(Check("files_missing", not missing,
                        "" if not missing else f"{len(missing)} Datei(en) fehlen: {', '.join(missing[:5])}"))
    checks.append(Check("files_extra", not extra,
                        "" if not extra else f"{len(extra)} zusätzliche Datei(en): {', '.join(extra[:5])}",
                        severity="warning" if extra else "info"))
    size_mismatch = [p for p in sorted(set(expected) & set(actual))
                     if expected[p]["size"] != actual[p]["size"]]
    checks.append(Check("file_sizes", not size_mismatch,
                        "" if not size_mismatch else
                        f"{len(size_mismatch)} Datei(en) mit abweichender Größe: {', '.join(size_mismatch[:5])}"))
    if compare_hash:
        both = [p for p in sorted(set(expected) & set(actual))
                if expected[p].get("sha") and actual[p].get("sha")]
        hash_mismatch = [p for p in both if expected[p]["sha"] != actual[p]["sha"]]
        checks.append(Check("file_hashes", None if not both else not hash_mismatch,
                            "Keine Hashes vergleichbar." if not both else
                            ("" if not hash_mismatch else
                             f"{len(hash_mismatch)} Datei(en) mit abweichendem Inhalt: {', '.join(hash_mismatch[:5])}")))
    return checks


def verify_disc_structure(reference_root, target_root, *, kind: str = "auto",
                          compare_hash: bool = False) -> VerifyResult:
    """Structured VIDEO_TS/BDMV comparison of a target against a reference tree."""
    reference = scan_tree(reference_root)
    actual = scan_tree(target_root)
    resolved_kind = kind if kind != "auto" else detect_disc_kind(reference) or detect_disc_kind(actual)
    checks = layout_checks(actual, resolved_kind) + compare_trees(reference, actual, compare_hash=compare_hash)
    return VerifyResult.from_checks(checks, message=f"Strukturvergleich ({resolved_kind}).")


def booktype_check(requested: str, actual: str) -> Check:
    if not requested or requested == "automatic":
        return Check("book_type", None, "Kein Book Type angefordert.", severity="info")
    if not actual or actual == "unknown":
        return Check("book_type", None, "Book Type konnte nicht zurückgelesen werden.", severity="warning")
    target = "DVD-ROM" if requested == "dvd_rom" else requested
    return (Check("book_type", True, f"Book Type {actual} gesetzt.") if actual.upper() == target.upper()
            else Check("book_type", False, f"Book Type {actual} statt {target}.", severity="warning"))
