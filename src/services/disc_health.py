"""Resilient-read policy and honest disc-health reporting.

This is about salvaging *legitimately readable* data from old/scratched discs —
not about bypassing any copy protection. The health score is computed only from
real read outcomes; with no data it stays NOT_AVAILABLE (never invented).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# Read policies, escalated as sectors keep failing.
NORMAL = "normal"
RETRY = "retry"
REDUCED_SPEED = "reduced_speed"
MULTIPLE_READ = "multiple_read"
SECTOR_COMPARE = "sector_compare"

_ESCALATION = [NORMAL, RETRY, REDUCED_SPEED, MULTIPLE_READ, SECTOR_COMPARE]

# Sector read outcomes (mutually exclusive; sum == total sectors seen).
CLEAN = "clean"          # first-try success
RETRIED = "retried"      # succeeded after retries
UNSTABLE = "unstable"    # readable but inconsistent across reads
FAILED = "failed"        # unreadable

# Health bands (only when data exists).
EXCELLENT, GOOD, FAIR, POOR, UNREADABLE = "excellent", "good", "fair", "poor", "unreadable"
NOT_AVAILABLE = "NOT_AVAILABLE"


def next_read_policy(current: str, escalate: bool = True) -> str:
    """Escalate one step on continued failure; clamp at SECTOR_COMPARE."""
    if not escalate:
        return current
    try:
        index = _ESCALATION.index(current)
    except ValueError:
        return NORMAL
    return _ESCALATION[min(index + 1, len(_ESCALATION) - 1)]


def health_score(total: int, successful: int, retried: int, unstable: int, failed: int) -> Optional[int]:
    """0..100 from real counts, or None if nothing was read (no invented value).

    Weighting: clean=1.0, retried=0.8 (readable with effort), unstable=0.5
    (readable but risky), failed=0.0. Counts should sum to ``total``.
    """
    if total <= 0:
        return None
    weighted = successful + 0.8 * retried + 0.5 * unstable
    return max(0, min(100, round(100 * weighted / total)))


def health_status(score: Optional[int]) -> str:
    if score is None:
        return NOT_AVAILABLE
    if score >= 98:
        return EXCELLENT
    if score >= 90:
        return GOOD
    if score >= 70:
        return FAIR
    if score > 0:
        return POOR
    return UNREADABLE


@dataclass
class DiscHealthReport:
    total_sectors: int = 0
    successful: int = 0        # clean
    retried: int = 0
    unstable: int = 0
    failed: int = 0
    read_policies_used: list[str] = field(default_factory=list)

    @property
    def score(self) -> Optional[int]:
        return health_score(self.total_sectors, self.successful, self.retried,
                            self.unstable, self.failed)

    @property
    def status(self) -> str:
        return health_status(self.score)

    def to_dict(self) -> dict:
        return {"total_sectors": self.total_sectors, "successful": self.successful,
                "retried": self.retried, "unstable": self.unstable, "failed": self.failed,
                "read_policies_used": list(self.read_policies_used),
                "health_score": self.score, "status": self.status}


class DiscHealthAccumulator:
    """Records real read outcomes per sector range and produces a report."""

    def __init__(self):
        self._report = DiscHealthReport()

    def record(self, sectors: int, outcome: str, *, policy: str = NORMAL) -> None:
        if sectors <= 0:
            return
        if outcome not in (CLEAN, RETRIED, UNSTABLE, FAILED):
            raise ValueError(f"Unbekanntes Leseergebnis: {outcome}")
        self._report.total_sectors += sectors
        if outcome == CLEAN:
            self._report.successful += sectors
        elif outcome == RETRIED:
            self._report.retried += sectors
        elif outcome == UNSTABLE:
            self._report.unstable += sectors
        else:
            self._report.failed += sectors
        if policy not in self._report.read_policies_used:
            self._report.read_policies_used.append(policy)

    def report(self) -> DiscHealthReport:
        return self._report
