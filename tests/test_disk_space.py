"""Disk-space evaluation, estimators and the create_iso pre-check."""
import pytest
from src.core.errors import StorageError
from src.services.disk_space import (
    evaluate, check_path, ensure_space, directory_size, iso_estimate,
    transcode_estimate, DEFAULT_RESERVE,
)


def test_evaluate_ok_when_free_covers_required_plus_reserve():
    r = evaluate(free_bytes=10_000_000_000, required_bytes=4_000_000_000, reserve_bytes=500_000_000)
    assert r.ok and r.shortfall_bytes == 0 and r.reserve_bytes == 500_000_000


def test_evaluate_fails_and_reports_shortfall():
    r = evaluate(free_bytes=1_000_000_000, required_bytes=4_000_000_000, reserve_bytes=100_000_000)
    assert not r.ok and r.shortfall_bytes == (4_000_000_000 + 100_000_000) - 1_000_000_000
    assert "Zu wenig Speicher" in r.message


def test_default_reserve_is_max_of_absolute_and_ratio():
    small = evaluate(10**12, 1_000_000)                 # 5% von 1MB < 512MB -> 512MB
    assert small.reserve_bytes == DEFAULT_RESERVE
    big = evaluate(10**12, 40_000_000_000)              # 5% von 40GB = 2GB > 512MB
    assert big.reserve_bytes == int(40_000_000_000 * 0.05)


def test_estimators():
    assert transcode_estimate(1000, 0.5) == 500
    assert transcode_estimate(1000, 2.0) == 2000
    assert transcode_estimate(1000, -1) == 0


def test_directory_and_iso_estimate(tmp_path):
    (tmp_path / "a").write_bytes(b"0" * 1000)
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b").write_bytes(b"0" * 2000)
    assert directory_size(tmp_path) == 3000
    est = iso_estimate(tmp_path)
    assert est >= 3000 and est == 3000 + max(1024 * 1024, int(3000 * 0.02))


def test_check_path_uses_real_free_space(tmp_path, monkeypatch):
    import shutil as _sh
    from collections import namedtuple
    Usage = namedtuple("Usage", "total used free")
    monkeypatch.setattr("src.services.disk_space.shutil.disk_usage", lambda p: Usage(0, 0, 5_000))
    assert check_path(tmp_path, 1_000, reserve_bytes=0).ok
    assert not check_path(tmp_path, 10_000, reserve_bytes=0).ok


def test_ensure_space_raises_storage_error(tmp_path, monkeypatch):
    from collections import namedtuple
    Usage = namedtuple("Usage", "total used free")
    monkeypatch.setattr("src.services.disk_space.shutil.disk_usage", lambda p: Usage(0, 0, 100))
    with pytest.raises(StorageError):
        ensure_space(tmp_path, 1_000_000, reserve_bytes=0)
    assert ensure_space(tmp_path, 50, reserve_bytes=0).ok


@pytest.mark.asyncio
async def test_create_iso_aborts_early_when_no_space(tmp_path, monkeypatch):
    from src.core.disc import DiscTools
    src = tmp_path / "VIDEO_TS"; src.mkdir(); (src / "big.vob").write_bytes(b"0" * 100_000)
    tools = object.__new__(DiscTools); tools.mkisofs = "mkisofs"
    from collections import namedtuple
    Usage = namedtuple("Usage", "total used free")
    monkeypatch.setattr("src.services.disk_space.shutil.disk_usage", lambda p: Usage(0, 0, 1_000))

    async def fail_if_reached(*a, **k):
        raise AssertionError("mkisofs darf bei zu wenig Platz nicht starten")
    monkeypatch.setattr("src.core.disc.create_hidden_subprocess", fail_if_reached)
    with pytest.raises(StorageError):
        await tools.create_iso(src, tmp_path / "out.iso")
