"""Bridge-Tests für die Blu-ray-Erweiterungen (create_bluray, burn_existing_iso,
check_target_medium, list_target_media.authoring_available, copy_disc-Fix).

Verteidigung in der Tiefe: ``create_bluray``/``burn_existing_iso`` prüfen die
Laufwerksfähigkeit VOR dem Einreihen selbst - nicht nur die UI. Diese Tests
bestätigen genau das, ohne echte Hardware oder einen echten Pipeline-Worker
zu brauchen (dieselbe ``queued_bridge``-Bauweise wie in
tests/test_job_submission.py: ``pipeline._is_running`` wird auf True gesetzt,
sodass eingereihte Jobs liegen bleiben und inspizierbar sind).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import retrodisc_launcher as launcher
from retrodisc_launcher import RetroDiscBridge
from src.config.settings import AppSettings
from src.services.drive_inspector import DriveCapabilities


@pytest.fixture
def bridge(tmp_path, monkeypatch):
    config_path = tmp_path / "settings.json"
    monkeypatch.setattr(AppSettings, "_default_config_path", staticmethod(lambda: config_path))
    AppSettings(directories={
        "output_dir": tmp_path / "output", "download_dir": tmp_path / "downloads",
        "temp_dir": tmp_path / "temp",
    }, library_db_path=tmp_path / ".retrodisc" / "library.db").save()
    monkeypatch.setattr(launcher, "check_tools", lambda: {})
    monkeypatch.setattr("src.services.library.MediaLibrary.open", lambda self: None)

    b = RetroDiscBridge()
    b.pipeline._is_running = True
    try:
        yield b
    finally:
        b._loop.call_soon_threadsafe(b._loop.stop)
        b._thread.join(timeout=5)


def _clip(tmp_path: Path) -> Path:
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"placeholder")
    return path


def _iso(tmp_path: Path) -> Path:
    path = tmp_path / "existing.iso"
    path.write_bytes(b"placeholder-iso")
    return path


async def _fake_inspect_drive(caps: DriveCapabilities):
    return caps


# ─── create_bluray: Laufwerksfähigkeit wird VOR dem Einreihen geprüft ─────

def test_create_bluray_refuses_to_queue_when_drive_cannot_write_bluray(bridge, tmp_path, monkeypatch):
    monkeypatch.setattr(bridge.disc, "inspect_drive",
                        lambda device: _fake_inspect_drive(DriveCapabilities(bd_r=False, bd_re=False)))
    paths = json.dumps([str(_clip(tmp_path))])

    result = json.loads(bridge.create_bluray(paths, "Test", "bd25", True, "E:"))

    assert "error" in result
    assert "Blu-ray-Rohlinge" in result["error"]
    assert bridge.pipeline.queue_size == 0


def test_create_bluray_refuses_bdxl_target_when_drive_lacks_bdxl(bridge, tmp_path, monkeypatch):
    monkeypatch.setattr(bridge.disc, "inspect_drive",
                        lambda device: _fake_inspect_drive(DriveCapabilities(bd_r=True, bd_re=True, bd_xl=False)))
    paths = json.dumps([str(_clip(tmp_path))])

    result = json.loads(bridge.create_bluray(paths, "Test", "bd128", True, "E:"))

    assert "error" in result
    assert "BDXL" in result["error"]
    assert bridge.pipeline.queue_size == 0


def test_create_bluray_queues_when_drive_is_fully_capable(bridge, tmp_path, monkeypatch):
    monkeypatch.setattr(bridge.disc, "inspect_drive",
                        lambda device: _fake_inspect_drive(DriveCapabilities(bd_r=True, bd_re=True, bd_xl=True)))
    paths = json.dumps([str(_clip(tmp_path))])

    result = json.loads(bridge.create_bluray(paths, "Test", "bd128", True, "E:"))

    assert "error" not in result
    job = bridge.pipeline.get_job(result["job_id"])
    assert job is not None
    assert job.params["target_medium_id"] == "bd128"


def test_create_bluray_iso_only_never_checks_drive_capability(bridge, tmp_path, monkeypatch):
    """Ohne Brennabsicht (nur ISO) gibt es keine Laufwerksanforderung zu prüfen."""
    called = []
    monkeypatch.setattr(bridge.disc, "inspect_drive",
                        lambda device: called.append(device) or _fake_inspect_drive(DriveCapabilities()))
    paths = json.dumps([str(_clip(tmp_path))])

    result = json.loads(bridge.create_bluray(paths, "Test", "bd25", False, ""))

    assert "error" not in result
    assert called == []


def test_create_bluray_rejects_unknown_target_medium_id(bridge, tmp_path):
    paths = json.dumps([str(_clip(tmp_path))])
    result = json.loads(bridge.create_bluray(paths, "Test", "bd999"))
    assert "error" in result
    assert bridge.pipeline.queue_size == 0


# ─── burn_existing_iso: bestehendes ISO ohne erneutes Encoding ────────────

def test_burn_existing_iso_queues_a_bluray_job_without_encoding(bridge, tmp_path):
    result = json.loads(bridge.burn_existing_iso(str(_iso(tmp_path)), "E:"))
    assert "error" not in result
    job = bridge.pipeline.get_job(result["job_id"])
    assert job.job_type.value == "burn_bluray"
    assert job.output_path == _iso(tmp_path)


def test_burn_existing_iso_rejects_a_missing_file(bridge, tmp_path):
    result = json.loads(bridge.burn_existing_iso(str(tmp_path / "missing.iso"), "E:"))
    assert "error" in result
    assert bridge.pipeline.queue_size == 0


def test_burn_existing_iso_rejects_an_unknown_disc_type(bridge, tmp_path):
    result = json.loads(bridge.burn_existing_iso(str(_iso(tmp_path)), "E:", disc_type="laserdisc"))
    assert "error" in result


def test_burn_existing_iso_checks_capability_when_target_medium_given(bridge, tmp_path, monkeypatch):
    monkeypatch.setattr(bridge.disc, "inspect_drive",
                        lambda device: _fake_inspect_drive(DriveCapabilities(bd_r=False, bd_re=False)))
    result = json.loads(bridge.burn_existing_iso(str(_iso(tmp_path)), "E:", target_medium_id="bd25"))
    assert "error" in result
    assert bridge.pipeline.queue_size == 0


def test_burn_existing_iso_dvd_disc_type_queues_a_dvd_job(bridge, tmp_path):
    result = json.loads(bridge.burn_existing_iso(str(_iso(tmp_path)), "E:", disc_type="dvd"))
    assert "error" not in result
    job = bridge.pipeline.get_job(result["job_id"])
    assert job.job_type.value == "burn_dvd"


# ─── check_target_medium: dieselbe Prüfung, nur als reine Leseabfrage ─────

def test_check_target_medium_reports_available_true_for_a_capable_drive(bridge, monkeypatch):
    monkeypatch.setattr(bridge.disc, "inspect_drive",
                        lambda device: _fake_inspect_drive(DriveCapabilities(bd_r=True, bd_re=True, bd_xl=True)))
    result = json.loads(bridge.check_target_medium("E:", "bd128"))
    assert result == {"available": True, "reason": None}


def test_check_target_medium_reports_available_false_with_a_reason(bridge, monkeypatch):
    monkeypatch.setattr(bridge.disc, "inspect_drive",
                        lambda device: _fake_inspect_drive(DriveCapabilities(bd_r=False, bd_re=False)))
    result = json.loads(bridge.check_target_medium("E:", "bd25"))
    assert result["available"] is False
    assert "Blu-ray-Rohlinge" in result["reason"]


def test_check_target_medium_without_device_only_flags_bdxl_uncertainty(bridge):
    result = json.loads(bridge.check_target_medium("", "bd25"))
    assert result == {"available": True, "reason": None}


# ─── list_target_media: authoring_available spiegelt echte Backend-Lage ──

def test_list_target_media_marks_bdmv_targets_available_when_ffmpeg_present(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/ffmpeg" if name == "ffmpeg" else None)
    result = json.loads(RetroDiscBridge.list_target_media(None))
    by_id = {m["id"]: m for m in result}
    assert by_id["bd25"]["authoring_available"] is True
    assert by_id["dvd5"]["authoring_available"] is True


def test_list_target_media_marks_bdmv_targets_unavailable_without_ffmpeg(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    result = json.loads(RetroDiscBridge.list_target_media(None))
    by_id = {m["id"]: m for m in result}
    assert by_id["bd25"]["authoring_available"] is False
    assert by_id["bd128"]["authoring_available"] is False
    # DVD_VIDEO-Authoring (dvdauthor) hängt nicht an FFmpeg-Verfügbarkeit.
    assert by_id["dvd5"]["authoring_available"] is True


# ─── copy_disc: Blu-ray-Quelle erhält disc_type=BLURAY statt DVD-Default ──

@pytest.mark.asyncio
async def test_copy_disc_detects_bluray_source_and_passes_bluray_disc_type(bridge, tmp_path, monkeypatch):
    from src.models.media import DiscType
    from src.services.burn_outcome import BurnOutcome
    from src.services.ripper import DiscRipper

    source_root = tmp_path / "srcdrive"
    (source_root / "BDMV").mkdir(parents=True)

    captured = {}

    async def fake_rip(self, source, output, fmt, job=None):
        Path(output).write_bytes(b"copied filesystem")
        return Path(output)

    async def fake_burn_iso(image_path, device=None, job=None, **kwargs):
        captured["disc_type"] = kwargs.get("disc_type")
        return BurnOutcome(burn_success=True)

    monkeypatch.setattr(DiscRipper, "rip", fake_rip)
    monkeypatch.setattr(bridge.disc, "burn_iso", fake_burn_iso)
    monkeypatch.setattr(DiscRipper, "_root", staticmethod(lambda device: source_root))

    submitted = []
    monkeypatch.setattr(bridge, "_submit_job",
                        lambda job, handler: submitted.append((job, handler)) or '{"job_id":"x"}')

    bridge.copy_disc(str(source_root), "F:")
    job, handler = submitted[-1]
    await handler(job)

    assert captured["disc_type"] == DiscType.BLURAY


@pytest.mark.asyncio
async def test_copy_disc_dvd_source_still_gets_dvd_disc_type(bridge, tmp_path, monkeypatch):
    from src.models.media import DiscType
    from src.services.burn_outcome import BurnOutcome
    from src.services.ripper import DiscRipper

    source_root = tmp_path / "srcdrive"
    (source_root / "VIDEO_TS").mkdir(parents=True)

    captured = {}

    async def fake_rip(self, source, output, fmt, job=None):
        Path(output).write_bytes(b"copied filesystem")
        return Path(output)

    async def fake_burn_iso(image_path, device=None, job=None, **kwargs):
        captured["disc_type"] = kwargs.get("disc_type")
        return BurnOutcome(burn_success=True)

    monkeypatch.setattr(DiscRipper, "rip", fake_rip)
    monkeypatch.setattr(bridge.disc, "burn_iso", fake_burn_iso)
    monkeypatch.setattr(DiscRipper, "_root", staticmethod(lambda device: source_root))

    submitted = []
    monkeypatch.setattr(bridge, "_submit_job",
                        lambda job, handler: submitted.append((job, handler)) or '{"job_id":"x"}')

    bridge.copy_disc(str(source_root), "F:")
    job, handler = submitted[-1]
    await handler(job)

    assert captured["disc_type"] == DiscType.DVD
