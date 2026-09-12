"""Regressionstests für die MediaLibrary-/ConversionQueue-Pfadisolation.

Vorher: ``MediaLibrary.__init__`` setzte ``db_path`` IMMER auf das echte
``Path.home() / ".retrodisc" / "library.db"``, unabhängig von jeder
Testkonfiguration - und ``ConversionQueue`` leitet ihren eigenen
SQLite-Pfad direkt aus ``library.db_path.parent / 'pipeline.db'`` ab. Das
in den Bridge-Test-Fixtures übliche
``monkeypatch.setattr(MediaLibrary.open, no-op)``-Muster verhinderte nur
den ``library.db``-Connect, NICHT das Schreiben in die echte
``pipeline.db``: jeder Testlauf, der ``convert_file()`` aufrief, hat
dadurch reale Fake-Job-Zeilen in der echten Datenbank des Nutzers
hinterlassen (siehe RELEASE_AUDIT_STATUS.md, Testisolationsblock -
Diagnose ergab ca. 55 solcher Fake-Zeilen in der bereits vorhandenen
echten ``~/.retrodisc/pipeline.db``, dort bewusst NICHT bereinigt).

Diese Datei beweist die Isolation direkt: ``AppSettings.library_db_path``
steuert ``MediaLibrary.db_path`` (und damit transitiv den
``ConversionQueue``-Pfad), Produktion ohne diese Einstellung bleibt
unverändert bei ``~/.retrodisc/``, und ein echter ``convert_file()``-Lauf
über die Bridge fasst die reale ``~/.retrodisc/pipeline.db`` nachweislich
nicht an.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import retrodisc_launcher as launcher
from retrodisc_launcher import RetroDiscBridge
from src.config.settings import AppSettings
from src.services.library import MediaLibrary


def test_app_settings_library_db_path_defaults_to_none():
    assert AppSettings().library_db_path is None


def test_media_library_still_defaults_to_the_real_home_directory_when_unset():
    """Production behaviour must not change: no explicit path (and no
    AppSettings override) still means the long-standing
    ~/.retrodisc/library.db default."""
    lib = MediaLibrary(ffmpeg=object())
    assert lib.db_path == Path.home() / ".retrodisc" / "library.db"


def test_media_library_honours_an_explicit_db_path():
    custom = Path("/some/isolated/place/library.db")
    lib = MediaLibrary(db_path=custom, ffmpeg=object())
    assert lib.db_path == custom
    assert lib.thumb_dir == custom.parent / "thumbnails"


@pytest.fixture
def isolated_bridge(tmp_path, monkeypatch):
    config_path = tmp_path / "settings.json"
    monkeypatch.setattr(AppSettings, "_default_config_path", staticmethod(lambda: config_path))
    AppSettings(directories={
        "output_dir": tmp_path / "output",
        "download_dir": tmp_path / "downloads",
        "temp_dir": tmp_path / "temp",
    }, library_db_path=tmp_path / ".retrodisc" / "library.db").save()
    monkeypatch.setattr(launcher, "check_tools", lambda: {})
    monkeypatch.setattr("src.services.library.MediaLibrary.open", lambda self: None)

    bridge = RetroDiscBridge()
    bridge.pipeline._is_running = True
    try:
        yield bridge
    finally:
        bridge._loop.call_soon_threadsafe(bridge._loop.stop)
        bridge._thread.join(timeout=5)


def test_bridge_wires_the_configured_library_db_path_through(isolated_bridge, tmp_path):
    assert isolated_bridge.library.db_path == tmp_path / ".retrodisc" / "library.db"


def test_bridge_conversion_queue_pipeline_db_lives_under_the_configured_path(
    isolated_bridge, tmp_path,
):
    """The concrete mechanism: ConversionQueue derives its own SQLite path
    from library.db_path, so fixing the library path fixes this
    transitively - ConversionQueue itself needed no change."""
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"placeholder")

    answer = json.loads(isolated_bridge.convert_file(str(clip), "mp4_h264_1080p"))
    assert "error" not in answer, answer

    assert isolated_bridge.conversion_queue.queue.db_path == tmp_path / ".retrodisc" / "pipeline.db"
    assert isolated_bridge.conversion_queue.queue.db_path.is_file()


def test_a_real_convert_file_run_never_touches_the_users_actual_retrodisc_directory(
    isolated_bridge, tmp_path,
):
    """The regression that matters: run the exact flow that used to leak into
    the real ~/.retrodisc/pipeline.db, and prove the real file is
    untouched. Deliberately read-only towards the real file - it is known
    to already contain fake rows from before this fix (see
    RELEASE_AUDIT_STATUS.md) and must neither be modified nor deleted by
    this or any other test."""
    real_pipeline_db = Path.home() / ".retrodisc" / "pipeline.db"
    before = real_pipeline_db.stat().st_mtime if real_pipeline_db.is_file() else None

    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"placeholder")
    json.loads(isolated_bridge.convert_file(str(clip), "mp4_h264_1080p"))

    after = real_pipeline_db.stat().st_mtime if real_pipeline_db.is_file() else None
    assert after == before, (
        "convert_file() modified the real ~/.retrodisc/pipeline.db - "
        "the path-isolation regression is back"
    )
