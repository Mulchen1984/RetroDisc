"""Regression tests for optical-disc and DVD workflow wiring."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from retrodisc_launcher import RetroDiscBridge
from src.core.disc import DiscError, DiscTools
from src.core.ffmpeg import FFmpeg
from src.services.dvd_workflow import _safe_windows_name
from src.services.ripper import DiscRipper
from src.services.watch_folder import WatchFolder, WatchRule

ROOT = Path(__file__).resolve().parents[1]
UI_FILE = ROOT / "src" / "ui" / "app.html"


@pytest.mark.asyncio
async def test_dvd_standard_is_normalized_for_ffmpeg(monkeypatch, tmp_path):
    ffmpeg = FFmpeg(ffmpeg_path="ffmpeg", ffprobe_path="ffprobe")
    captured = {}

    async def fake_convert(**kwargs):
        captured.update(kwargs)
        return Path(kwargs["output_path"])

    monkeypatch.setattr(ffmpeg, "convert", fake_convert)
    result = await ffmpeg.to_dvd_mpeg(
        tmp_path / "in.mp4", tmp_path / "out.mpg", standard="PAL"
    )
    assert result == tmp_path / "out.mpg"
    assert captured["extra_args"][0:2] == ["-target", "pal-dvd"]


@pytest.mark.asyncio
async def test_invalid_dvd_standard_is_rejected(tmp_path):
    ffmpeg = FFmpeg(ffmpeg_path="ffmpeg", ffprobe_path="ffprobe")
    with pytest.raises(ValueError, match="DVD-Standard"):
        await ffmpeg.to_dvd_mpeg(
            tmp_path / "in.mp4", tmp_path / "out.mpg", standard="SECAM"
        )


def test_windows_safe_dvd_names():
    assert _safe_windows_name('Bad:Title <2026>?') == "Bad_Title_2026"
    assert _safe_windows_name(" . ") == "RetroDisc_DVD"


def test_ripper_selects_largest_dvd_title_set(tmp_path):
    video_ts = tmp_path / "VIDEO_TS"
    video_ts.mkdir()
    for name, size in {
        "VTS_01_0.VOB": 100,
        "VTS_01_1.VOB": 300,
        "VTS_01_2.VOB": 300,
        "VTS_02_1.VOB": 900,
        "VTS_02_2.VOB": 900,
    }.items():
        (video_ts / name).write_bytes(b"x" * size)
    selected = DiscRipper._dvd_title_files(tmp_path)
    assert [p.name for p in selected] == ["VTS_02_1.VOB", "VTS_02_2.VOB"]


def test_disc_ui_uses_real_backend_contracts():
    html = UI_FILE.read_text(encoding="utf-8")
    assert "a.create_dvd(paths,t,standard,aspect,true,device,speed,verify,eject)" in html
    assert "a.rip_disc(device, fmt)" in html
    assert "a.get_disc_info(device)" in html
    assert "a.convert_file('D:" not in html
    assert 'id="burnerSelect"' in html
    assert 'id="ripDriveSelect"' in html
    assert 'id="burnSpeed"' in html
    assert 'id="dvdStandard"' in html


@pytest.mark.asyncio
async def test_disc_verification_compares_only_iso_length(tmp_path):
    iso = tmp_path / "image.iso"
    medium = tmp_path / "medium.bin"
    iso.write_bytes(b"retrodisc" * 1000)
    medium.write_bytes(iso.read_bytes() + b"trailing sectors")
    assert await DiscTools().verify_iso(iso, str(medium)) is True


@pytest.mark.asyncio
async def test_disc_verification_detects_corruption(tmp_path):
    iso = tmp_path / "image.iso"
    medium = tmp_path / "medium.bin"
    iso.write_bytes(b"correct image")
    medium.write_bytes(b"broken image!")
    with pytest.raises(DiscError, match="Prüfsummen"):
        await DiscTools().verify_iso(iso, str(medium))


def test_batch_accepts_directory_and_filters_media(tmp_path):
    (tmp_path / "a.mp4").write_bytes(b"x")
    (tmp_path / "b.txt").write_text("skip", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "c.wav").write_bytes(b"x")

    bridge = RetroDiscBridge.__new__(RetroDiscBridge)
    captured = []
    bridge.convert_file = lambda path, preset, output, overwrite: (
        captured.append(Path(path).name)
        or json.dumps({"job_id": Path(path).stem})
    )
    result = json.loads(bridge.convert_batch(str(tmp_path), "mp4_h264_1080p"))
    assert result["count"] == 2
    assert captured == ["a.mp4", "c.wav"]


@pytest.mark.asyncio
async def test_watch_folder_uses_real_submission_callback(monkeypatch, tmp_path):
    media = tmp_path / "incoming.mp4"
    media.write_bytes(b"media")
    submitted = []

    async def submit(path, rule):
        submitted.append((path, rule.action, rule.preset))

    watch = WatchFolder(
        tmp_path,
        [WatchRule("MP4", [".mp4"], "convert", "mp4_h264_1080p")],
        submit_callback=submit,
    )

    async def stable(_path):
        return True

    async def no_delay(_seconds):
        return None

    monkeypatch.setattr(watch, "_is_file_stable", stable)
    monkeypatch.setattr("src.services.watch_folder.asyncio.sleep", no_delay)
    await watch._process_file(media)
    assert submitted == [(media, "convert", "mp4_h264_1080p")]
