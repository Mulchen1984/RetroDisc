"""Tests für FFmpeg.to_bluray_stream und BlurayWorkflow (BD-25/50/BDXL-100/128).

FFmpeg.to_bluray_stream selbst wurde vor der Integration real gegen dieses
Projekts FFmpeg getestet (Sync-Byte 0x47 an Offset 4 jedes 192-Byte-Pakets,
Video-PID 0x1011 / Audio-PID 0x1100 per ffprobe bestätigt) - hier wird nur
noch die Kommandozeilen-*Konstruktion* geprüft (schnell, ohne echten Encode).
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.core.ffmpeg import FFmpeg
from src.core.disc import DiscError
from src.models.media import DiscType
from src.services.booktype import BookType
from src.services.burn_outcome import BookTypeStatus, BurnOutcome
from src.services.bluray_workflow import BlurayProject, BlurayWorkflow
from src.services.verify import FAIL, PASS, VerifyResult


# ─── FFmpeg.to_bluray_stream: Kommandozeile ────────────────────────────────

@pytest.mark.asyncio
async def test_to_bluray_stream_sets_the_fixed_bd_rom_pids(monkeypatch, tmp_path):
    ffmpeg = FFmpeg(ffmpeg_path="ffmpeg", ffprobe_path="ffprobe")
    captured = {}

    async def fake_convert(**kwargs):
        captured.update(kwargs)
        return Path(kwargs["output_path"])

    monkeypatch.setattr(ffmpeg, "convert", fake_convert)
    await ffmpeg.to_bluray_stream(tmp_path / "in.mp4", tmp_path / "out.m2ts")

    extra = captured["extra_args"]
    assert "-streamid" in extra
    assert f"0:0x{FFmpeg.BLURAY_VIDEO_PID:x}" in extra
    assert f"1:0x{FFmpeg.BLURAY_AUDIO_PID:x}" in extra
    assert "-mpegts_m2ts_mode" in extra and "1" in extra
    assert "-f" in extra and "mpegts" in extra
    assert captured["video_codec"] == "libx264"
    assert captured["audio_codec"] == "ac3"


@pytest.mark.asyncio
async def test_to_bluray_stream_uses_high_profile_level_4_1(monkeypatch, tmp_path):
    ffmpeg = FFmpeg(ffmpeg_path="ffmpeg", ffprobe_path="ffprobe")
    captured = {}

    async def fake_convert(**kwargs):
        captured.update(kwargs)
        return Path(kwargs["output_path"])

    monkeypatch.setattr(ffmpeg, "convert", fake_convert)
    await ffmpeg.to_bluray_stream(tmp_path / "in.mp4", tmp_path / "out.m2ts")

    extra = captured["extra_args"]
    idx = extra.index("-profile:v")
    assert extra[idx + 1] == "high"
    idx = extra.index("-level:v")
    assert extra[idx + 1] == "4.1"


@pytest.mark.asyncio
async def test_to_bluray_stream_default_bitrate_is_conservative_when_unspecified(monkeypatch, tmp_path):
    ffmpeg = FFmpeg(ffmpeg_path="ffmpeg", ffprobe_path="ffprobe")
    captured = {}

    async def fake_convert(**kwargs):
        captured.update(kwargs)
        return Path(kwargs["output_path"])

    monkeypatch.setattr(ffmpeg, "convert", fake_convert)
    await ffmpeg.to_bluray_stream(tmp_path / "in.mp4", tmp_path / "out.m2ts")
    assert int(captured["video_bitrate"]) == 15_000_000


@pytest.mark.asyncio
async def test_to_bluray_stream_honors_a_capacity_planner_derived_bitrate(monkeypatch, tmp_path):
    ffmpeg = FFmpeg(ffmpeg_path="ffmpeg", ffprobe_path="ffprobe")
    captured = {}

    async def fake_convert(**kwargs):
        captured.update(kwargs)
        return Path(kwargs["output_path"])

    monkeypatch.setattr(ffmpeg, "convert", fake_convert)
    await ffmpeg.to_bluray_stream(tmp_path / "in.mp4", tmp_path / "out.m2ts", video_bitrate_bps=6_000_000)
    assert int(captured["video_bitrate"]) == 6_000_000


# ─── BlurayWorkflow: Orchestrierung (gefakte disc/author-Schicht) ─────────

def _fake_disc(*, verify_result=None):
    async def fake_create_iso(**kwargs):
        iso_path = kwargs["output_path"]
        iso_path.write_bytes(b"iso-bytes")
        return iso_path

    calls = {}

    async def fake_burn_iso(iso_path, device, speed=None, verify=True, disc_type=DiscType.DVD,
                            job=None, book_type=None, media_type=None):
        calls["disc_type"] = disc_type
        calls["book_type"] = book_type
        calls["device"] = device
        return BurnOutcome(
            burn_success=True,
            book_type_status=BookTypeStatus.NOT_APPLICABLE,
            verify=verify_result or VerifyResult(status=PASS, message="ok"),
        )

    return SimpleNamespace(create_iso=fake_create_iso, burn_iso=fake_burn_iso), calls


@pytest.fixture
def source(tmp_path):
    f = tmp_path / "movie.mp4"
    f.write_bytes(b"source")
    return f


@pytest.mark.asyncio
@pytest.mark.parametrize("target_medium_id", ["bd25", "bd50", "bd100", "bd128"])
async def test_bluray_workflow_produces_an_iso_for_every_physical_bd_target(monkeypatch, tmp_path, source, target_medium_id):
    async def fake_author_bdmv(ffmpeg, input_files, output_dir, video_bitrate_bps=None, job=None):
        return output_dir / "BLURAY"

    monkeypatch.setattr("src.services.bluray_workflow.author_bdmv", fake_author_bdmv)
    disc, calls = _fake_disc()
    workflow = BlurayWorkflow(ffmpeg=SimpleNamespace(), disc_tools=disc, temp_dir=tmp_path)

    project = BlurayProject(title="Test", input_files=[source], output_dir=tmp_path,
                            target_medium_id=target_medium_id, only_iso=True)
    iso_path = await workflow.run(project)

    assert iso_path.is_file()


@pytest.mark.asyncio
async def test_bluray_workflow_burn_step_always_uses_native_book_type(monkeypatch, tmp_path, source):
    """Book Type ist für Blu-ray nicht anwendbar - BlurayWorkflow fragt es
    erst gar nicht als AUTO/DVD_ROM an (DiscTools._apply_book_type würde es
    ohnehin auf NOT_APPLICABLE setzen, aber der Aufrufer soll keine für
    Blu-ray sinnlose Anfrage überhaupt stellen)."""
    async def fake_author_bdmv(ffmpeg, input_files, output_dir, video_bitrate_bps=None, job=None):
        return output_dir / "BLURAY"

    monkeypatch.setattr("src.services.bluray_workflow.author_bdmv", fake_author_bdmv)
    disc, calls = _fake_disc()
    workflow = BlurayWorkflow(ffmpeg=SimpleNamespace(), disc_tools=disc, temp_dir=tmp_path)

    project = BlurayProject(title="Test", input_files=[source], output_dir=tmp_path,
                            target_medium_id="bd50", burn_to_disc=True, disc_device="E:")
    await workflow.run(project)

    assert calls["book_type"] == BookType.NATIVE
    assert calls["disc_type"] == DiscType.BLURAY
    assert calls["device"] == "E:"


@pytest.mark.asyncio
async def test_bluray_workflow_raises_when_verify_fails_even_though_burn_succeeded(monkeypatch, tmp_path, source):
    async def fake_author_bdmv(ffmpeg, input_files, output_dir, video_bitrate_bps=None, job=None):
        return output_dir / "BLURAY"

    monkeypatch.setattr("src.services.bluray_workflow.author_bdmv", fake_author_bdmv)
    disc, _ = _fake_disc(verify_result=VerifyResult(status=FAIL, message="Prüfsummen unterscheiden sich."))
    workflow = BlurayWorkflow(ffmpeg=SimpleNamespace(), disc_tools=disc, temp_dir=tmp_path)

    project = BlurayProject(title="Test", input_files=[source], output_dir=tmp_path,
                            target_medium_id="bd25", burn_to_disc=True, disc_device="E:")
    with pytest.raises(DiscError, match="Verifikation fehlgeschlagen"):
        await workflow.run(project)


@pytest.mark.asyncio
async def test_bluray_workflow_only_iso_never_calls_burn_iso(monkeypatch, tmp_path, source):
    async def fake_author_bdmv(ffmpeg, input_files, output_dir, video_bitrate_bps=None, job=None):
        return output_dir / "BLURAY"

    monkeypatch.setattr("src.services.bluray_workflow.author_bdmv", fake_author_bdmv)

    async def fake_create_iso(**kwargs):
        iso_path = kwargs["output_path"]
        iso_path.write_bytes(b"iso-bytes")
        return iso_path

    async def fail_burn_iso(*args, **kwargs):
        raise AssertionError("burn_iso darf bei only_iso=True nicht aufgerufen werden")

    disc = SimpleNamespace(create_iso=fake_create_iso, burn_iso=fail_burn_iso)
    workflow = BlurayWorkflow(ffmpeg=SimpleNamespace(), disc_tools=disc, temp_dir=tmp_path)

    project = BlurayProject(title="Test", input_files=[source], output_dir=tmp_path,
                            target_medium_id="bd25", burn_to_disc=True, only_iso=True)
    await workflow.run(project)
