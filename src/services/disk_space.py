"""Free-space checks before large operations (Disc->ISO, transcode, creator).

Estimates the required output size, adds a safety reserve, and aborts early with
a clear message instead of filling the disk mid-operation. Pure evaluation is
separated from the filesystem call so it is fully unit tested.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.core.errors import StorageError

DEFAULT_RESERVE = 512 * 1024 * 1024      # 512 MB Sicherheitsreserve
DEFAULT_RESERVE_RATIO = 0.05             # oder 5 % der Zielgröße, was größer ist


@dataclass
class SpaceCheck:
    ok: bool
    free_bytes: int
    required_bytes: int
    reserve_bytes: int
    shortfall_bytes: int
    message: str

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def _reserve_for(required: int, reserve_bytes: Optional[int], reserve_ratio: float) -> int:
    if reserve_bytes is not None:
        return max(0, int(reserve_bytes))
    return max(DEFAULT_RESERVE, int(required * reserve_ratio))


def evaluate(free_bytes: int, required_bytes: int, *, reserve_bytes: Optional[int] = None,
             reserve_ratio: float = DEFAULT_RESERVE_RATIO) -> SpaceCheck:
    required = max(0, int(required_bytes))
    free = max(0, int(free_bytes))
    reserve = _reserve_for(required, reserve_bytes, reserve_ratio)
    need = required + reserve
    ok = free >= need
    shortfall = max(0, need - free)
    if ok:
        message = f"Genug Speicher: {free} frei, benötigt {need} (inkl. Reserve {reserve})."
    else:
        message = (f"Zu wenig Speicher: {shortfall} Bytes fehlen "
                   f"(frei {free}, benötigt {need} inkl. Reserve {reserve}).")
    return SpaceCheck(ok, free, required, reserve, shortfall, message)


def check_path(path, required_bytes: int, **kwargs) -> SpaceCheck:
    """Evaluate against the filesystem that holds ``path`` (its parent if a file)."""
    target = Path(path)
    probe = target if target.is_dir() else target.parent
    try:
        free = shutil.disk_usage(str(probe)).free
    except OSError as exc:
        raise StorageError(f"Freier Speicher konnte nicht ermittelt werden: {probe}",
                           detail=str(exc)) from exc
    return evaluate(free, required_bytes, **kwargs)


def ensure_space(path, required_bytes: int, **kwargs) -> SpaceCheck:
    """Raise StorageError early if there is not enough room; else return the check."""
    result = check_path(path, required_bytes, **kwargs)
    if not result.ok:
        raise StorageError(result.message)
    return result


# ── size estimators (heuristic, conservative) ────────────────────────────────
def directory_size(source_dir) -> int:
    """Sum of file sizes under a directory (skips unreadable entries)."""
    total = 0
    for path in Path(source_dir).rglob("*"):
        try:
            if path.is_file():
                total += path.stat().st_size
        except OSError:
            continue
    return total


def iso_estimate(source_dir) -> int:
    """ISO ~= payload size plus small filesystem overhead (~2 %, min 1 MB)."""
    payload = directory_size(source_dir)
    return payload + max(1024 * 1024, int(payload * 0.02))


def transcode_estimate(source_bytes: int, ratio: float = 1.0) -> int:
    """Rough transcoded-output size = source * ratio (ratio<1 shrinks, >1 grows)."""
    return max(0, int(source_bytes * max(0.0, ratio)))
