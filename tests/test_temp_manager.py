"""TempManager: per-job isolation, cleanup, crash recovery, path safety."""
import os
import time
import pytest
from src.core.errors import StorageError
from src.services.temp_manager import TempManager


def test_default_root_is_under_system_temp():
    import tempfile
    from pathlib import Path
    tm = TempManager()
    assert Path(tempfile.gettempdir()) in tm.root.parents or tm.root.parent == Path(tempfile.gettempdir())


def test_ensure_space_precheck(tmp_path, monkeypatch):
    from collections import namedtuple
    Usage = namedtuple("Usage", "total used free")
    tm = TempManager(tmp_path)
    monkeypatch.setattr("src.services.disk_space.shutil.disk_usage", lambda p: Usage(0, 0, 100))
    with pytest.raises(StorageError):
        tm.ensure_space(1_000_000, reserve_bytes=0)
    assert tm.ensure_space(50, reserve_bytes=0).ok


def test_session_space_precheck_blocks_before_creating(tmp_path, monkeypatch):
    from collections import namedtuple
    Usage = namedtuple("Usage", "total used free")
    tm = TempManager(tmp_path)
    monkeypatch.setattr("src.services.disk_space.shutil.disk_usage", lambda p: Usage(0, 0, 10))
    with pytest.raises(StorageError):
        with tm.session("big", required_bytes=1_000_000):
            pass
    assert not tm.job_dir("big", create=False).exists()      # nichts angelegt


def test_safe_rmtree_refuses_paths_outside_own_area(tmp_path):
    tm = TempManager(tmp_path / "root")
    outside = tmp_path / "keep_me"; outside.mkdir(); (outside / "f").write_bytes(b"x")
    assert tm._safe_rmtree(outside) is False and outside.exists()     # außerhalb -> abgelehnt
    wrong = tm.root / "not-a-job"; wrong.mkdir(parents=True); (wrong / "f").write_bytes(b"x")
    assert tm._safe_rmtree(wrong) is False and wrong.exists()         # falsches Präfix -> abgelehnt


def test_jobs_get_isolated_directories(tmp_path):
    tm = TempManager(tmp_path)
    a, b = tm.job_dir("job-1"), tm.job_dir("job-2")
    assert a.is_dir() and b.is_dir() and a != b        # kein Überschreiben fremder Jobs


def test_allocate_stays_inside_job_dir(tmp_path):
    tm = TempManager(tmp_path)
    p = tm.allocate("j1", "image.iso")
    assert p.parent == tm.job_dir("j1") and p.name == "image.iso"
    # Pfad-Ausbruch wird entschärft
    assert tm.allocate("j1", "../../etc/passwd").name == "passwd"


def test_unsafe_job_id_cannot_escape_root(tmp_path):
    tm = TempManager(tmp_path)
    d = tm.job_dir("../../evil")
    assert tmp_path in d.parents and d.is_dir()         # bleibt unter root


def test_cleanup_removes_job_dir(tmp_path):
    tm = TempManager(tmp_path)
    d = tm.job_dir("j"); (d / "f").write_bytes(b"x")
    assert tm.cleanup("j") is True and not d.exists()
    assert tm.cleanup("j") is False                     # schon weg


def test_session_removes_on_success(tmp_path):
    tm = TempManager(tmp_path)
    with tm.session("ok") as d:
        (d / "tmp.bin").write_bytes(b"x")
        assert d.is_dir()
    assert not d.exists()


def test_session_error_removes_by_default_but_can_keep(tmp_path):
    tm = TempManager(tmp_path)
    with pytest.raises(RuntimeError):
        with tm.session("boom") as d:
            (d / "x").write_bytes(b"x")
            raise RuntimeError("fail")
    assert not d.exists()                               # kein Leak großer Images

    with pytest.raises(RuntimeError):
        with tm.session("diag", keep_on_error=True) as d2:
            (d2 / "log").write_bytes(b"x")
            raise RuntimeError("fail")
    assert d2.is_dir()                                  # Diagnoseartefakte behalten


def test_cleanup_stale_removes_old_keeps_fresh(tmp_path):
    tm = TempManager(tmp_path)
    old = tm.job_dir("old"); fresh = tm.job_dir("fresh")
    past = time.time() - 2 * 86400
    os.utime(old, (past, past))
    removed = tm.cleanup_stale(max_age_seconds=86400)
    assert "retrodisc-job-old" in removed and not old.exists()
    assert fresh.is_dir()                               # frischer Job bleibt


def test_cleanup_stale_on_missing_root_is_safe(tmp_path):
    assert TempManager(tmp_path / "nope").cleanup_stale() == []
