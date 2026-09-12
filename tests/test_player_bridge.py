"""Bridge-Tests für den Vorschau-/Preview-Player (player_open/-play/-pause/...).

Echte Ende-zu-Ende-Tests gegen das echte mpv-Binary (übersprungen ohne mpv)
UND echte VIDEO_TS-/BDMV-Teststrukturen - ausdrücklich als solche bezeichnet:
kein echtes optisches Laufwerk, aber echte, wirklich abspielbare MPEG-2/AC-3-
bzw. H.264/AC-3-Inhalte (kein Fake-Byte-Fixture wie in
tests/test_player_source.py, wo nur die Dateiauflösung geprüft wird, nicht
die tatsächliche Wiedergabe).
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
    pytest.mark.skipif(shutil.which("mkisofs") is None, reason="mkisofs ist in dieser Umgebung nicht installiert"),
]

_SECTOR_SIZE = 2048
_TT_SRPT_POINTER_OFFSET = 0xC4


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


def _real_vob(path, duration=1, size="352x288"):
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", f"testsrc=duration={duration}:size={size}:rate=25",
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
         "-c:v", "mpeg2video", "-c:a", "ac3", "-f", "vob", str(path)],
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    return path


def _build_video_ts_ifo(entries, tt_srpt_sector=1):
    header = bytearray(_SECTOR_SIZE)
    header[0:12] = b"DVDVIDEO-VMG"
    header[_TT_SRPT_POINTER_OFFSET:_TT_SRPT_POINTER_OFFSET + 4] = tt_srpt_sector.to_bytes(4, "big")
    table = bytearray()
    table += len(entries).to_bytes(2, "big")
    table += b"\x00\x00"
    table += (0).to_bytes(4, "big")
    for vts_number, vts_ttn, chapter_count, angle_count in entries:
        entry = bytearray(12)
        entry[0] = 0x03
        entry[1] = angle_count
        entry[2:4] = chapter_count.to_bytes(2, "big")
        entry[4:6] = b"\x00\x00"
        entry[6] = vts_number
        entry[7] = vts_ttn
        entry[8:12] = (0).to_bytes(4, "big")
        table += entry
    return bytes(header) + b"\x00" * (tt_srpt_sector * _SECTOR_SIZE - len(header)) + bytes(table)


def _real_video_ts(tmp_path, entries):
    root = tmp_path / "device" / "VIDEO_TS"
    root.mkdir(parents=True)
    (root / "VIDEO_TS.IFO").write_bytes(_build_video_ts_ifo(entries))
    return root.parent


async def _real_bdmv(tmp_path, clip_durations=(1,)):
    from src.core.ffmpeg import FFmpeg
    from src.services.bluray_authoring import author_bdmv
    ffmpeg = FFmpeg()
    inputs = []
    for i, dur in enumerate(clip_durations):
        src = tmp_path / f"src_{i}.mp4"
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
             "-f", "lavfi", "-i", f"testsrc=duration={dur}:size=320x240:rate=25",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=" + str(dur),
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(src)],
            capture_output=True,
        )
        assert result.returncode == 0, result.stderr
        inputs.append(src)
    # author_bdmv() liefert bereits die Wurzel, die BDMV/ direkt enthält
    # (output_dir / "BLURAY") - das IST das "device" für player_open.
    return await author_bdmv(ffmpeg, inputs, tmp_path / "device", video_bitrate_bps=2_000_000)


def _iso_from(content_dir, out_iso):
    result = subprocess.run(["mkisofs", "-V", "TESTDISC", "-o", str(out_iso), "-udf", str(content_dir)],
                            capture_output=True)
    assert result.returncode == 0, result.stderr
    return out_iso


# ─── normale Videodatei ─────────────────────────────────────────────────────

async def test_player_open_file_kind_plays_a_real_video(bridge, tmp_path):
    clip = _real_vob(tmp_path / "clip.mp4")
    result = json.loads(bridge.player_open(json.dumps({"kind": "file", "path": str(clip)})))
    assert result.get("error") is None, result
    assert result["loaded"] is True
    assert result["duration_seconds"] == pytest.approx(1.0, abs=0.3)


# ─── DVD-Titel (VIDEO_TS, ein Segment und mehrere Segmente) ────────────────

async def test_player_open_dvd_title_single_segment(bridge, tmp_path):
    device = _real_video_ts(tmp_path, [(1, 1, 2, 1)])
    _real_vob(device / "VIDEO_TS" / "VTS_01_1.VOB")
    result = json.loads(bridge.player_open(json.dumps(
        {"kind": "dvd_title", "device": str(device), "title_index": 0})))
    assert result.get("error") is None, result
    assert result["loaded"] is True


async def test_player_open_dvd_title_multiple_segments_is_one_continuous_title(bridge, tmp_path):
    device = _real_video_ts(tmp_path, [(1, 1, 4, 1)])
    _real_vob(device / "VIDEO_TS" / "VTS_01_1.VOB")
    _real_vob(device / "VIDEO_TS" / "VTS_01_2.VOB")
    result = json.loads(bridge.player_open(json.dumps(
        {"kind": "dvd_title", "device": str(device), "title_index": 0})))
    assert result.get("error") is None, result
    assert result["duration_seconds"] == pytest.approx(2.0, abs=0.4)


# ─── Blu-ray-Titel (BDMV/MPLS, ein Clip und mehrere Clips) ─────────────────

async def test_player_open_bluray_title_single_clip(bridge, tmp_path):
    device = await _real_bdmv(tmp_path, clip_durations=(1,))
    result = json.loads(bridge.player_open(json.dumps(
        {"kind": "bluray_title", "device": str(device), "title_index": 0})))
    assert result.get("error") is None, result
    assert result["loaded"] is True


async def test_player_open_bluray_title_multiple_clips_is_one_continuous_title(bridge, tmp_path):
    device = await _real_bdmv(tmp_path, clip_durations=(1, 1))
    result = json.loads(bridge.player_open(json.dumps(
        {"kind": "bluray_title", "device": str(device), "title_index": 0})))
    assert result.get("error") is None, result
    assert result["duration_seconds"] == pytest.approx(2.0, abs=0.4)


# ─── DVD-ISO / Blu-ray-ISO (Mount -> Wiedergabe -> Unmount) ────────────────

async def test_player_open_dvd_iso_mounts_plays_and_unmounts(bridge, tmp_path):
    device = _real_video_ts(tmp_path, [(1, 1, 2, 1)])
    _real_vob(device / "VIDEO_TS" / "VTS_01_1.VOB")
    iso_path = _iso_from(device, tmp_path / "dvd.iso")

    result = json.loads(bridge.player_open(json.dumps(
        {"kind": "dvd_iso", "path": str(iso_path), "title_index": 0})))
    assert result.get("error") is None, result
    assert result["loaded"] is True
    assert bridge._player_mount is not None
    mount_root = bridge._player_mount.root
    assert mount_root.is_dir()

    # bridge.player läuft auf dem dedizierten Bridge-Loop (eigener Thread) -
    # close() deshalb über dieselbe _async()-Brücke wie jede echte
    # Bridge-Methode aufrufen, nicht direkt aus dem pytest-asyncio-Loop.
    json.loads(bridge.player_close())
    assert not mount_root.exists()   # sauber ausgehängt, kein dauerhafter Mount


async def test_player_open_bluray_iso_mounts_plays_and_unmounts(bridge, tmp_path):
    device = await _real_bdmv(tmp_path, clip_durations=(1,))
    iso_path = _iso_from(device, tmp_path / "bd.iso")

    result = json.loads(bridge.player_open(json.dumps(
        {"kind": "bluray_iso", "path": str(iso_path), "title_index": 0})))
    assert result.get("error") is None, result
    assert result["loaded"] is True
    mount_root = bridge._player_mount.root

    json.loads(bridge.player_close())
    assert not mount_root.exists()


# ─── Titelwechsel ───────────────────────────────────────────────────────────

async def test_title_switch_opens_a_different_title(bridge, tmp_path):
    device = _real_video_ts(tmp_path, [(1, 1, 2, 1), (2, 1, 2, 1)])
    _real_vob(device / "VIDEO_TS" / "VTS_01_1.VOB", duration=1)
    _real_vob(device / "VIDEO_TS" / "VTS_02_1.VOB", duration=3)

    r0 = json.loads(bridge.player_open(json.dumps({"kind": "dvd_title", "device": str(device), "title_index": 0})))
    assert r0["duration_seconds"] == pytest.approx(1.0, abs=0.3)
    r1 = json.loads(bridge.player_open(json.dumps({"kind": "dvd_title", "device": str(device), "title_index": 1})))
    assert r1["duration_seconds"] == pytest.approx(3.0, abs=0.4)


# ─── Kapitelwechsel ─────────────────────────────────────────────────────────

async def test_chapter_switch_via_bridge_changes_position(bridge, tmp_path):
    meta = tmp_path / "chapters.txt"
    meta.write_text(
        ";FFMETADATA1\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=1000\ntitle=A\n"
        "[CHAPTER]\nTIMEBASE=1/1000\nSTART=1000\nEND=2000\ntitle=B\n"
    )
    clip = tmp_path / "chaptered.mp4"
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=25",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
         "-i", str(meta), "-map_metadata", "2",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(clip)],
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr

    opened = json.loads(bridge.player_open(json.dumps({"kind": "file", "path": str(clip)})))
    assert opened["chapter_count"] == 2
    r = json.loads(bridge.player_set_chapter(1))
    assert "error" not in r
    state = json.loads(bridge.player_get_state())
    assert state["chapter"] == 1


# ─── Audio-/Untertitel-Wechsel ──────────────────────────────────────────────

async def test_audio_track_switch_via_bridge(bridge, tmp_path):
    clip = _real_vob(tmp_path / "clip.mp4")
    opened = json.loads(bridge.player_open(json.dumps({"kind": "file", "path": str(clip)})))
    audio_tracks = [t for t in opened["tracks"] if t["type"] == "audio"]
    assert audio_tracks
    r = json.loads(bridge.player_set_audio_track(audio_tracks[0]["id"]))
    assert "error" not in r
    state = json.loads(bridge.player_get_state())
    assert state["audio_track"] == audio_tracks[0]["id"]


async def test_disable_subtitles_via_bridge(bridge, tmp_path):
    clip = _real_vob(tmp_path / "clip.mp4")
    json.loads(bridge.player_open(json.dumps({"kind": "file", "path": str(clip)})))
    r = json.loads(bridge.player_disable_subtitles())
    assert "error" not in r
    state = json.loads(bridge.player_get_state())
    assert state["subtitle_track"] is None


# ─── Play/Pause/Stop/Seek/Lautstärke/Vollbild ──────────────────────────────

async def test_transport_controls_via_bridge(bridge, tmp_path):
    clip = _real_vob(tmp_path / "clip.mp4", duration=3)
    json.loads(bridge.player_open(json.dumps({"kind": "file", "path": str(clip)})))

    assert "error" not in json.loads(bridge.player_pause())
    assert json.loads(bridge.player_get_state())["paused"] is True

    assert "error" not in json.loads(bridge.player_play())
    assert json.loads(bridge.player_get_state())["paused"] is False

    assert "error" not in json.loads(bridge.player_set_volume(33))
    assert json.loads(bridge.player_get_state())["volume"] == pytest.approx(33.0)

    # Pausiert seeken: sonst laeuft die Position zwischen dem Seek- und dem
    # nachfolgenden State-Abruf (zwei echte, sequenzielle IPC-Aufrufe) durch
    # reale Wiedergabezeit weiter. Toleranz bewusst weiter als beim H.264-Clip
    # in test_player_service.py: MPEG-2/VOB-Material (wie hier, real
    # gegengeprüft per manuellem IPC-Aufruf) landet selbst mit
    # "absolute+exact" auf dem nächsten GOP/PTS-Raster, nicht exakt auf der
    # angeforderten Sekunde - eine reale Eigenschaft dieses Streamtyps, kein
    # Fehler in PlayerService.seek().
    assert "error" not in json.loads(bridge.player_pause())
    assert "error" not in json.loads(bridge.player_seek(1.5, False))
    state = json.loads(bridge.player_get_state())
    assert state["position_seconds"] == pytest.approx(1.5, abs=0.6)

    assert "error" not in json.loads(bridge.player_set_fullscreen(True))
    assert json.loads(bridge.player_get_state())["fullscreen"] is True

    assert "error" not in json.loads(bridge.player_stop())


# ─── Main Movie (DiscContent.main_movie -> derselbe Titel im Player) ───────

async def test_main_movie_title_opens_the_disc_analyzer_identified_title(bridge, tmp_path, monkeypatch):
    device = _real_video_ts(tmp_path, [(1, 1, 1, 1), (2, 1, 1, 1)])
    _real_vob(device / "VIDEO_TS" / "VTS_01_1.VOB", duration=1)     # kurz - nicht der Hauptfilm
    _real_vob(device / "VIDEO_TS" / "VTS_02_1.VOB", duration=6)     # lang - erwartbar der Hauptfilm

    # get_disc_info()s "present"-Erkennung braucht auf macOS ein echtes
    # optisches Laufwerk/isoinfo-lesbares Abbild (siehe src/core/disc.py,
    # Windows hat einen Dateisystem-Fallback, macOS/Linux nicht) - hier reicht
    # ein einfaches Testverzeichnis nicht. Nur dieser eine Erkennungsschritt
    # wird gefakt; die eigentliche Titel-/Hauptfilm-Analyse (DiscAnalyzer auf
    # der echten VIDEO_TS-Struktur) läuft vollständig real.
    async def fake_get_disc_info(dev):
        return {"present": True, "label": "TESTDISC", "capacity_bytes": None, "blank": False}

    monkeypatch.setattr(bridge.disc, "get_disc_info", fake_get_disc_info)

    content = json.loads(bridge.get_disc_content(str(device)))
    assert "error" not in content, content
    main = next((t for t in content["titles"] if t["is_main_movie"]), None)
    assert main is not None, "DiscAnalyzer hat keinen Hauptfilm erkannt"

    result = json.loads(bridge.player_open(json.dumps(
        {"kind": "dvd_title", "device": str(device), "title_index": main["index"]})))
    assert result.get("error") is None, result
    assert result["duration_seconds"] == pytest.approx(main["duration_seconds"], abs=0.5)


# ─── Stop/Cleanup, ungültige Quelle, fehlendes Backend ─────────────────────

async def test_stop_then_close_is_clean(bridge, tmp_path):
    clip = _real_vob(tmp_path / "clip.mp4")
    json.loads(bridge.player_open(json.dumps({"kind": "file", "path": str(clip)})))
    assert "error" not in json.loads(bridge.player_stop())
    assert "error" not in json.loads(bridge.player_close())


async def test_invalid_source_kind_returns_a_json_error_not_an_exception(bridge):
    result = json.loads(bridge.player_open(json.dumps({"kind": "not-a-real-kind"})))
    assert "error" in result


async def test_missing_file_source_returns_a_json_error(bridge, tmp_path):
    result = json.loads(bridge.player_open(json.dumps(
        {"kind": "file", "path": str(tmp_path / "does-not-exist.mp4")})))
    assert "error" in result


async def test_missing_backend_returns_a_json_error_not_an_exception(bridge, tmp_path):
    bridge.player.mpv_path = "/definitely/not/a/real/mpv"
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"irrelevant")
    result = json.loads(bridge.player_open(json.dumps({"kind": "file", "path": str(clip)})))
    assert "error" in result
    assert "mpv" in result["error"]


async def test_unresolvable_title_after_a_successful_iso_mount_still_unmounts(bridge, tmp_path):
    """Regressionsschutz: ein ungültiger Titel-Index NACH erfolgreichem
    ISO-Mount darf keinen dauerhaften Mount hinterlassen."""
    device = _real_video_ts(tmp_path, [(1, 1, 2, 1)])
    _real_vob(device / "VIDEO_TS" / "VTS_01_1.VOB")
    iso_path = _iso_from(device, tmp_path / "dvd.iso")

    result = json.loads(bridge.player_open(json.dumps(
        {"kind": "dvd_iso", "path": str(iso_path), "title_index": 99})))
    assert "error" in result
    assert bridge._player_mount is None
