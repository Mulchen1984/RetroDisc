"""Tests für player.py (PlayerService, mpv per JSON-IPC).

Echte Integrationstests gegen das echte mpv-Binary (übersprungen, wenn mpv
nicht installiert ist - z. B. auf einem CI-Runner ohne vendortes mpv, siehe
Abschlussbericht "VERBLEIBENDE EINSCHRÄNKUNGEN"). Erzeugt seine Test-Clips
selbst per ``ffmpeg -f lavfi`` - genau das bereits in
tests/test_pipeline_workflow.py / tests/test_waveform.py etablierte Muster,
keine neuen Binär-Fixtures im Repo. "Fehlendes Wiedergabe-Backend" ist die
einzige Ausnahme: dafür braucht es kein echtes mpv, im Gegenteil - der Test
prüft genau den Fall, dass keins gefunden wird.
"""
from __future__ import annotations

import shutil
import subprocess

import pytest

from src.services.player import PlayerBackendError, PlayerError, PlayerService

pytestmark = pytest.mark.asyncio

_HAS_MPV = shutil.which("mpv") is not None
_needs_mpv = pytest.mark.skipif(not _HAS_MPV, reason="mpv ist in dieser Umgebung nicht installiert")


def _make_clip(path, duration=2, size="320x240", freq=440, chapters_file=None):
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
          "-f", "lavfi", "-i", f"testsrc=duration={duration}:size={size}:rate=25",
          "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={duration}"]
    if chapters_file:
        cmd += ["-i", str(chapters_file), "-map_metadata", "2"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)]
    result = subprocess.run(cmd, capture_output=True)
    assert result.returncode == 0, result.stderr
    return path


@pytest.fixture
def clip(tmp_path):
    return _make_clip(tmp_path / "clip.mp4")


@pytest.fixture
def chaptered_clip(tmp_path):
    meta = tmp_path / "chapters.txt"
    meta.write_text(
        ";FFMETADATA1\n"
        "[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=1000\ntitle=Chapter One\n"
        "[CHAPTER]\nTIMEBASE=1/1000\nSTART=1000\nEND=2000\ntitle=Chapter Two\n"
    )
    return _make_clip(tmp_path / "chaptered.mp4", duration=2, chapters_file=meta)


# ─── normale Videodatei ─────────────────────────────────────────────────────

@_needs_mpv
async def test_plays_a_plain_video_file_with_real_position_and_duration(clip):
    svc = PlayerService()
    try:
        state = await svc.open([clip], label="Testclip")
        assert state.loaded is True
        assert state.duration_seconds == pytest.approx(2.0, abs=0.2)
        assert state.label == "Testclip"
    finally:
        await svc.close()


@_needs_mpv
async def test_play_pause_seek_volume_control_a_real_instance(clip):
    svc = PlayerService()
    try:
        await svc.open([clip])
        await svc.pause()
        state = await svc.get_state()
        assert state.paused is True

        await svc.play()
        state = await svc.get_state()
        assert state.paused is False

        await svc.set_volume(42)
        state = await svc.get_state()
        assert state.volume == pytest.approx(42.0)

        await svc.seek(1.0, relative=False)
        state = await svc.get_state()
        assert state.position_seconds == pytest.approx(1.0, abs=0.3)

        await svc.set_fullscreen(True)
        state = await svc.get_state()
        assert state.fullscreen is True
    finally:
        await svc.close()


# ─── mehrsegmentige Titel (DVD-Titel aus mehreren Segmenten /
#     Blu-ray-MPLS mit mehreren Clips) ──────────────────────────────────────

@_needs_mpv
async def test_multi_segment_title_plays_as_one_continuous_timeline(tmp_path):
    seg_a = _make_clip(tmp_path / "a.mp4", duration=1)
    seg_b = _make_clip(tmp_path / "b.mp4", duration=1)
    svc = PlayerService()
    try:
        state = await svc.open([seg_a, seg_b], label="Mehrsegment-Titel")
        assert state.duration_seconds == pytest.approx(2.0, abs=0.3)
    finally:
        await svc.close()


# ─── Kapitel ────────────────────────────────────────────────────────────────

@_needs_mpv
async def test_chapter_switch_moves_playback_position(chaptered_clip):
    svc = PlayerService()
    try:
        state = await svc.open([chaptered_clip])
        assert state.chapter_count == 2
        await svc.set_chapter(1)
        state = await svc.get_state()
        assert state.chapter == 1
        assert state.position_seconds >= 0.9
    finally:
        await svc.close()


# ─── Audio-/Untertitel-Track-Auswahl (Abfrage der real erkannten Tracks) ────

@_needs_mpv
async def test_audio_track_is_reported_and_selectable(clip):
    svc = PlayerService()
    try:
        state = await svc.open([clip])
        audio_tracks = [t for t in state.tracks if t.type == "audio"]
        assert len(audio_tracks) == 1
        await svc.set_audio_track(audio_tracks[0].id)
        state = await svc.get_state()
        assert state.audio_track == audio_tracks[0].id
    finally:
        await svc.close()


@_needs_mpv
async def test_disable_subtitles_clears_subtitle_track(clip):
    svc = PlayerService()
    try:
        await svc.open([clip])
        await svc.disable_subtitles()
        state = await svc.get_state()
        assert state.subtitle_track is None
    finally:
        await svc.close()


# ─── Stop/Cleanup ───────────────────────────────────────────────────────────

@_needs_mpv
async def test_stop_calls_on_unload_and_keeps_mpv_reusable(clip):
    svc = PlayerService()
    unloaded = []

    async def on_unload():
        unloaded.append(True)

    try:
        await svc.open([clip], on_unload=on_unload)
        await svc.stop()
        assert unloaded == [True]
        # mpv bleibt im Idle-Modus - eine neue Quelle laesst sich weiterhin oeffnen.
        state = await svc.open([clip])
        assert state.loaded is True
    finally:
        await svc.close()


@_needs_mpv
async def test_close_terminates_the_subprocess_and_is_idempotent(clip):
    svc = PlayerService()
    await svc.open([clip])
    assert svc.is_running is True
    await svc.close()
    assert svc.is_running is False
    await svc.close()   # darf nicht erneut fehlschlagen


# ─── ungültige Quelle / nicht unterstützter Codec ──────────────────────────

@_needs_mpv
async def test_missing_file_is_rejected_before_touching_mpv(tmp_path):
    svc = PlayerService()
    try:
        with pytest.raises(PlayerError, match="nicht gefunden"):
            await svc.open([tmp_path / "does-not-exist.mp4"])
    finally:
        await svc.close()


@_needs_mpv
async def test_unsupported_or_corrupt_source_raises_a_clear_player_error(tmp_path):
    garbage = tmp_path / "garbage.mp4"
    garbage.write_bytes(b"this is not a real media container, just bytes")
    svc = PlayerService()
    try:
        with pytest.raises(PlayerError, match="nicht unterstützter Codec|ungültige Quelle"):
            await svc.open([garbage])
    finally:
        await svc.close()


# ─── fehlendes Wiedergabe-Backend ───────────────────────────────────────────

async def test_missing_mpv_backend_raises_a_clear_error(tmp_path):
    fake_video = tmp_path / "clip.mp4"
    fake_video.write_bytes(b"irrelevant - backend check happens first")
    svc = PlayerService(mpv_path="/definitely/not/a/real/mpv/binary")
    with pytest.raises(PlayerBackendError, match="mpv"):
        await svc.open([fake_video])


async def test_no_mpv_path_resolves_to_shutil_which(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    svc = PlayerService()
    assert svc.mpv_path is None
    with pytest.raises(PlayerBackendError):
        await svc.start()
