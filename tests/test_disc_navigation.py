"""Tests für die Disc-Menü-Navigationsfähigkeit (src/services/disc_navigation.py)
und PlayerService.discnav()/player_discnav.

Deckt DVD-Menü, DVD-Titelmenü, DVD-Menünavigation, DVD-ISO-Menü, Blu-ray-
HDMV und BD-J ab - real geprüft, wo möglich (BD-J-Laufzeitcheck via
``otool``), sonst über den echten, im mpv-0.41.0-Quellcode belegten Befund
(DVD-Menü-Entfernung, fehlende Blu-ray-HDMV-Eingabeschnittstelle).
"""
from __future__ import annotations

import json
import shutil

import pytest

from src.services.disc_navigation import (
    NavigationCapability,
    bluray_bdj_supported,
    bluray_hdmv_menu_navigation_supported,
    describe_disc_navigation_support,
    dvd_menu_navigation_supported,
)


# ─── Kapazitätsprüfung: DVD-Menü, Blu-ray-HDMV, BD-J ───────────────────────

def test_dvd_menu_navigation_is_reported_as_unsupported_with_a_source_citation():
    capability = dvd_menu_navigation_supported()
    assert isinstance(capability, NavigationCapability)
    assert capability.supported is False
    assert "stream_dvdnav.c" in capability.reason
    assert "removed" in capability.reason.lower() or "entfernt" in capability.reason.lower()


def test_bluray_hdmv_menu_navigation_is_reported_as_unsupported_with_a_source_citation():
    capability = bluray_hdmv_menu_navigation_supported()
    assert capability.supported is False
    assert "stream_bluray.c" in capability.reason


@pytest.mark.asyncio
@pytest.mark.skipif(shutil.which("otool") is None or shutil.which("mpv") is None,
                    reason="Realer BD-J-Laufzeitcheck braucht otool (macOS) und ein installiertes mpv")
async def test_bdj_runtime_check_is_real_and_currently_reports_unsupported():
    """Kein hartcodiertes False - echte otool-Prüfung (über den versteckten
    Subprozess-Helfer, wie jeder andere externe Werkzeugaufruf im Projekt)
    gegen die tatsächlich von mpv verlinkte libbluray (siehe Moduldoku:
    keine JVM verlinkt)."""
    capability = await bluray_bdj_supported()
    assert capability.supported is False
    assert "libbluray" in capability.reason


@pytest.mark.asyncio
async def test_bdj_check_never_claims_support_without_otool(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    capability = await bluray_bdj_supported()
    assert capability.supported is False
    assert "otool" in capability.reason


class _FakeProc:
    def __init__(self, stdout: bytes):
        self._stdout = stdout

    async def communicate(self):
        return self._stdout, b""


@pytest.mark.asyncio
async def test_bdj_check_reports_true_if_a_jvm_dependency_is_actually_found(monkeypatch):
    """Kein Hartcodieren auf 'immer False' - der Check ist ein echter,
    umkehrbarer Test der otool-Ausgabe."""
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/otool")

    async def fake_subprocess(tool, *args, **kwargs):
        if "mpv" in args[-1]:
            return _FakeProc(b"\t/opt/homebrew/lib/libbluray.dylib (compat 1.0.0)\n")
        return _FakeProc(b"\t/usr/lib/libjvm.dylib (compat 1.0.0)\n")

    monkeypatch.setattr("src.services.disc_navigation.create_hidden_subprocess", fake_subprocess)
    capability = await bluray_bdj_supported("/opt/homebrew/bin/mpv")
    assert capability.supported is True


@pytest.mark.asyncio
async def test_describe_disc_navigation_support_returns_all_three_keys():
    result = await describe_disc_navigation_support()
    assert set(result) == {"dvd_menu", "bluray_hdmv_menu", "bluray_bdj"}
    for entry in result.values():
        assert "supported" in entry and "reason" in entry


# ─── PlayerService.discnav(): DVD-Menü, DVD-Titelmenü, Pfeiltasten, OK,
#     Zurück - alle ehrlich abgewiesen statt vorgetäuscht ──────────────────

pytestmark_mpv = pytest.mark.skipif(shutil.which("mpv") is None, reason="mpv ist in dieser Umgebung nicht installiert")


@pytestmark_mpv
@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["menu", "title-menu", "back", "up", "down", "left", "right", "select"])
async def test_discnav_refuses_every_action_honestly(action, tmp_path):
    import subprocess
    from src.services.player import PlayerError, PlayerService

    clip = tmp_path / "clip.mp4"
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=25",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(clip)],
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr

    svc = PlayerService()
    try:
        await svc.open([clip])
        with pytest.raises(PlayerError, match="Disc-Menü-Navigation wird nicht unterstützt"):
            await svc.discnav(action)
    finally:
        await svc.close()


@pytestmark_mpv
@pytest.mark.asyncio
async def test_discnav_rejects_unknown_action(tmp_path):
    from src.services.player import PlayerError, PlayerService
    svc = PlayerService()
    with pytest.raises(PlayerError, match="Unbekannte Navigationsaktion"):
        await svc.discnav("teleport")
    await svc.close()


# ─── Wechsel Menü→Film→Menü / Audio-Untertitel danach weiterhin
#     funktionsfähig: ein abgelehnter discnav()-Aufruf darf den Player-
#     Zustand nicht beschädigen - normale Bedienung bleibt danach intakt ───

@pytestmark_mpv
@pytest.mark.asyncio
async def test_audio_and_subtitle_control_still_work_after_a_rejected_discnav_call(tmp_path):
    import subprocess
    from src.services.player import PlayerError, PlayerService

    clip = tmp_path / "clip.mp4"
    srt = tmp_path / "subs.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nHallo\n")
    # "-t 2" statt "-shortest": real reproduziert hängt ffmpeg unbegrenzt,
    # wenn ein SRT-Eingang gemeinsam mit "-shortest" gemappt wird (die
    # Kürzeste-Spur-Erkennung berücksichtigt die Untertitelspur offenbar
    # nicht als terminierend) - eine explizite Dauer umgeht das zuverlässig.
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "testsrc2=duration=2:size=320x240:rate=25",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-i", str(srt),
         "-map", "0:v", "-map", "1:a", "-map", "2:s", "-t", "2",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-c:s", "mov_text",
         str(clip)],
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr

    svc = PlayerService()
    try:
        state = await svc.open([clip])
        with pytest.raises(PlayerError):
            await svc.discnav("menu")
        with pytest.raises(PlayerError):
            await svc.discnav("up")

        audio_tracks = [t for t in state.tracks if t.type == "audio"]
        assert audio_tracks
        await svc.set_audio_track(audio_tracks[0].id)
        await svc.disable_subtitles()
        final_state = await svc.get_state()
        assert final_state.audio_track == audio_tracks[0].id
        assert final_state.subtitle_track is None
        assert final_state.loaded is True
    finally:
        await svc.close()


# ─── Bridge-Ebene: player_check_engine()/player_discnav() ─────────────────

@pytestmark_mpv
def test_bridge_player_check_engine_reports_navigation_capability(tmp_path, monkeypatch):
    import retrodisc_launcher as launcher
    from retrodisc_launcher import RetroDiscBridge
    from src.config.settings import AppSettings

    config_path = tmp_path / "settings.json"
    monkeypatch.setattr(AppSettings, "_default_config_path", staticmethod(lambda: config_path))
    AppSettings(directories={
        "output_dir": tmp_path / "output", "download_dir": tmp_path / "downloads",
        "temp_dir": tmp_path / "temp",
    }).save()
    monkeypatch.setattr(launcher, "check_tools", lambda: {})
    monkeypatch.setattr("src.services.library.MediaLibrary.open", lambda self: None)

    bridge = RetroDiscBridge()
    try:
        info = json.loads(bridge.player_check_engine())
        assert info["navigation"]["dvd_menu"]["supported"] is False
        assert info["navigation"]["bluray_hdmv_menu"]["supported"] is False
        assert "bluray_bdj" in info["navigation"]
    finally:
        bridge._loop.call_soon_threadsafe(bridge._loop.stop)
        bridge._thread.join(timeout=5)


@pytestmark_mpv
def test_bridge_player_discnav_returns_a_json_error_not_an_exception(tmp_path, monkeypatch):
    import subprocess
    import retrodisc_launcher as launcher
    from retrodisc_launcher import RetroDiscBridge
    from src.config.settings import AppSettings

    config_path = tmp_path / "settings.json"
    monkeypatch.setattr(AppSettings, "_default_config_path", staticmethod(lambda: config_path))
    AppSettings(directories={
        "output_dir": tmp_path / "output", "download_dir": tmp_path / "downloads",
        "temp_dir": tmp_path / "temp",
    }).save()
    monkeypatch.setattr(launcher, "check_tools", lambda: {})
    monkeypatch.setattr("src.services.library.MediaLibrary.open", lambda self: None)

    bridge = RetroDiscBridge()
    try:
        clip = tmp_path / "clip.mp4"
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
             "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=25",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(clip)],
            capture_output=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        opened = json.loads(bridge.player_open(json.dumps({"kind": "file", "path": str(clip)})))
        assert opened.get("error") is None, opened

        r = json.loads(bridge.player_discnav("menu"))
        assert "error" in r
        assert "Disc-Menü-Navigation" in r["error"]
    finally:
        try:
            bridge._async(bridge.player.close()).result(timeout=10)
        except Exception:
            pass
        bridge._loop.call_soon_threadsafe(bridge._loop.stop)
        bridge._thread.join(timeout=5)


# ─── DVD-ISO-Menü: dieselbe ehrliche Ablehnung, auch über einen gemounteten
#     ISO-Pfad statt eines direkten Laufwerks/einer Datei ──────────────────

_SECTOR_SIZE = 2048
_TT_SRPT_POINTER_OFFSET = 0xC4


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
        entry[6] = vts_number
        entry[7] = vts_ttn
        table += entry
    return bytes(header) + b"\x00" * (tt_srpt_sector * _SECTOR_SIZE - len(header)) + bytes(table)


@pytestmark_mpv
@pytest.mark.skipif(shutil.which("mkisofs") is None, reason="mkisofs ist in dieser Umgebung nicht installiert")
def test_dvd_iso_menu_navigation_is_rejected_and_iso_stays_cleanly_unmountable(tmp_path, monkeypatch):
    import subprocess
    import retrodisc_launcher as launcher
    from retrodisc_launcher import RetroDiscBridge
    from src.config.settings import AppSettings

    config_path = tmp_path / "settings.json"
    monkeypatch.setattr(AppSettings, "_default_config_path", staticmethod(lambda: config_path))
    AppSettings(directories={
        "output_dir": tmp_path / "output", "download_dir": tmp_path / "downloads",
        "temp_dir": tmp_path / "temp",
    }).save()
    monkeypatch.setattr(launcher, "check_tools", lambda: {})
    monkeypatch.setattr("src.services.library.MediaLibrary.open", lambda self: None)

    device = tmp_path / "device"
    (device / "VIDEO_TS").mkdir(parents=True)
    (device / "VIDEO_TS" / "VIDEO_TS.IFO").write_bytes(_build_video_ts_ifo([(1, 1, 2, 1)]))
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "testsrc=duration=1:size=352x288:rate=25",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
         "-c:v", "mpeg2video", "-c:a", "ac3", "-f", "vob",
         str(device / "VIDEO_TS" / "VTS_01_1.VOB")],
        capture_output=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    iso_path = tmp_path / "dvd.iso"
    result = subprocess.run(["mkisofs", "-V", "TESTDISC", "-o", str(iso_path), "-udf", str(device)],
                            capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr

    bridge = RetroDiscBridge()
    try:
        opened = json.loads(bridge.player_open(json.dumps(
            {"kind": "dvd_iso", "path": str(iso_path), "title_index": 0})))
        assert opened.get("error") is None, opened
        mount_root = bridge._player_mount.root

        r = json.loads(bridge.player_discnav("menu"))
        assert "error" in r
        assert "Disc-Menü-Navigation" in r["error"]

        json.loads(bridge.player_close())
        assert not mount_root.exists(), "ISO blieb nach einem abgelehnten Menü-Versuch gemountet"
    finally:
        bridge._loop.call_soon_threadsafe(bridge._loop.stop)
        bridge._thread.join(timeout=5)
