"""Resilient-read policy escalation and honest disc-health scoring."""
import pytest
from src.services.disc_health import (
    next_read_policy, health_score, health_status, DiscHealthReport, DiscHealthAccumulator,
    NORMAL, RETRY, REDUCED_SPEED, MULTIPLE_READ, SECTOR_COMPARE,
    CLEAN, RETRIED, UNSTABLE, FAILED,
    EXCELLENT, GOOD, FAIR, POOR, UNREADABLE, NOT_AVAILABLE,
)


def test_read_policy_escalates_and_clamps():
    assert next_read_policy(NORMAL) == RETRY
    assert next_read_policy(RETRY) == REDUCED_SPEED
    assert next_read_policy(REDUCED_SPEED) == MULTIPLE_READ
    assert next_read_policy(MULTIPLE_READ) == SECTOR_COMPARE
    assert next_read_policy(SECTOR_COMPARE) == SECTOR_COMPARE      # clamp
    assert next_read_policy(NORMAL, escalate=False) == NORMAL
    assert next_read_policy("weird") == NORMAL


def test_health_score_from_real_counts_only():
    assert health_score(100, 100, 0, 0, 0) == 100                 # alles sauber
    assert health_score(100, 0, 0, 0, 100) == 0                   # alles unlesbar
    assert health_score(0, 0, 0, 0, 0) is None                    # keine Daten -> nichts erfinden
    # gewichtet: 80 clean + 10 retried(0.8) + 10 unstable(0.5) = 80+8+5 = 93
    assert health_score(100, 80, 10, 10, 0) == 93


def test_health_status_bands():
    assert health_status(None) == NOT_AVAILABLE
    assert health_status(100) == EXCELLENT
    assert health_status(92) == GOOD
    assert health_status(75) == FAIR
    assert health_status(20) == POOR
    assert health_status(0) == UNREADABLE


def test_accumulator_sums_and_reports():
    acc = DiscHealthAccumulator()
    acc.record(500, CLEAN, policy=NORMAL)
    acc.record(50, RETRIED, policy=RETRY)
    acc.record(30, UNSTABLE, policy=MULTIPLE_READ)
    acc.record(20, FAILED, policy=SECTOR_COMPARE)
    r = acc.report()
    assert r.total_sectors == 600 and r.successful == 500 and r.failed == 20
    assert r.read_policies_used == [NORMAL, RETRY, MULTIPLE_READ, SECTOR_COMPARE]
    d = r.to_dict()
    assert d["health_score"] == health_score(600, 500, 50, 30, 20) and d["status"] in (GOOD, FAIR, EXCELLENT, POOR)


def test_accumulator_rejects_bad_outcome_and_ignores_empty():
    acc = DiscHealthAccumulator()
    acc.record(0, CLEAN)                                          # 0 Sektoren -> ignoriert
    assert acc.report().total_sectors == 0
    with pytest.raises(ValueError):
        acc.record(10, "melted")


def test_empty_report_is_not_available_not_zero():
    r = DiscHealthReport()
    assert r.score is None and r.status == NOT_AVAILABLE          # ehrlich: unbekannt, nicht 0
