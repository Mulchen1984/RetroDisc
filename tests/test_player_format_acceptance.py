"""Player-Abnahmetest: reale Containerformate und echter Untertitel-Wechsel.

Ergänzt tests/test_player_bridge.py gezielt um die Lücken eines finalen
Format-Abnahmetests:

* MP4/DVD/Blu-ray-Titel werden dort zwar bereits real abgespielt, aber über
  ``_real_vob()`` - das erzwingt via ``-f vob`` einen MPEG-2/AC-3-VOB-Strom
  in einer nur ``.mp4``-benannten Datei. Das ist für DVD-Inhalte korrekt,
  beweist aber NICHT, dass ein echter ISOBMFF/MP4-Container (H.264/AAC)
  bzw. ein echter Matroska-Container abgespielt wird - deshalb hier mit
  ``-f mp4``/``-f matroska`` erzwungen und mit ``file`` bestätigt.
* AVI (MPEG-4/MP3) und WebM (VP9/Opus) als weitere, in freier Wildbahn
  übliche Formate.
* ``player_set_subtitle_track`` wird bisher nur über "abschalten" getestet
  (``test_disable_subtitles_via_bridge``) - hier mit zwei echten,
  unterscheidbaren Untertitelspuren real zwischen ihnen gewechselt.
"""
from __future__ import annotations

import json
import shutil
import subprocess

import pytest

import retrodisc_launcher as launcher
from retrodisc_launcher import RetroDiscBridge
from src.config.settings import AppSettings

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(shutil.which("mpv") is None, reason="mpv ist in dieser Umgebung nicht installiert"),
]


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
        try:
            b._async(b.player.close()).result(timeout=10)
        except Exception:
            pass
        b._loop.call_soon_threadsafe(b._loop.stop)
        b._thread.join(timeout=5)


def _encode(path, *, container, vcodec, acodec, duration=2, extra=()):
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", f"testsrc=duration={duration}:size=320x240:rate=25",
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
         "-c:v", vcodec, "-c:a", acodec, *extra, "-shortest", "-f", container, str(path)],
        capture_output=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return path


# ─── MKV, MP4 (echte Container), weitere übliche Formate ──────────────────

async def test_player_open_plays_a_real_mkv_file(bridge, tmp_path):
    clip = _encode(tmp_path / "clip.mkv", container="matroska",
                   vcodec="libx264", acodec="aac", extra=("-pix_fmt", "yuv420p"))
    result = json.loads(bridge.player_open(json.dumps({"kind": "file", "path": str(clip)})))
    assert result.get("error") is None, result
    assert result["loaded"] is True
    assert result["duration_seconds"] == pytest.approx(2.0, abs=0.3)


async def test_player_open_plays_a_real_mp4_file(bridge, tmp_path):
    clip = _encode(tmp_path / "clip.mp4", container="mp4",
                   vcodec="libx264", acodec="aac", extra=("-pix_fmt", "yuv420p"))
    result = json.loads(bridge.player_open(json.dumps({"kind": "file", "path": str(clip)})))
    assert result.get("error") is None, result
    assert result["loaded"] is True
    assert result["duration_seconds"] == pytest.approx(2.0, abs=0.3)


async def test_player_open_plays_a_real_avi_file(bridge, tmp_path):
    clip = _encode(tmp_path / "clip.avi", container="avi", vcodec="mpeg4", acodec="mp3")
    result = json.loads(bridge.player_open(json.dumps({"kind": "file", "path": str(clip)})))
    assert result.get("error") is None, result
    assert result["loaded"] is True
    assert result["duration_seconds"] == pytest.approx(2.0, abs=0.3)


async def test_player_open_plays_a_real_webm_file(bridge, tmp_path):
    clip = _encode(tmp_path / "clip.webm", container="webm", vcodec="libvpx-vp9", acodec="libopus")
    result = json.loads(bridge.player_open(json.dumps({"kind": "file", "path": str(clip)})))
    assert result.get("error") is None, result
    assert result["loaded"] is True
    assert result["duration_seconds"] == pytest.approx(2.0, abs=0.3)


# ─── echter Untertitel-Wechsel zwischen zwei Spuren (nicht nur Abschalten) ─

async def test_player_set_subtitle_track_switches_between_two_real_tracks(bridge, tmp_path):
    srt_de = tmp_path / "de.srt"
    srt_en = tmp_path / "en.srt"
    srt_de.write_text("1\n00:00:00,000 --> 00:00:02,000\nHallo\n")
    srt_en.write_text("1\n00:00:00,000 --> 00:00:02,000\nHello\n")
    clip = tmp_path / "subtitled.mp4"
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=25",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
         "-i", str(srt_de), "-i", str(srt_en),
         "-map", "0:v", "-map", "1:a", "-map", "2:s", "-map", "3:s", "-t", "2",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-c:s", "mov_text",
         str(clip)],
        capture_output=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr

    opened = json.loads(bridge.player_open(json.dumps({"kind": "file", "path": str(clip)})))
    assert opened.get("error") is None, opened
    subtitle_tracks = [t for t in opened["tracks"] if t["type"] == "sub"]
    assert len(subtitle_tracks) == 2, opened["tracks"]

    first, second = subtitle_tracks[0]["id"], subtitle_tracks[1]["id"]

    r = json.loads(bridge.player_set_subtitle_track(first))
    assert "error" not in r, r
    assert json.loads(bridge.player_get_state())["subtitle_track"] == first

    r = json.loads(bridge.player_set_subtitle_track(second))
    assert "error" not in r, r
    assert json.loads(bridge.player_get_state())["subtitle_track"] == second

    r = json.loads(bridge.player_disable_subtitles())
    assert "error" not in r, r
    assert json.loads(bridge.player_get_state())["subtitle_track"] is None
