"""Tests für player_source.py - Titel-Index -> abspielbare Dateiliste.

Wiederverwendet dieselben Byte-Fixture-Bauer wie die bereits bestehenden
Parser-Tests (``tests/test_dvd_ifo.py``/``tests/test_bluray_mpls.py``), damit
hier keine parallele, abweichende Vorstellung von "gültiges IFO/MPLS"
entsteht.
"""
from __future__ import annotations

import pytest

from src.models.media import DiscType
from src.services.bluray_authoring import build_mpls
from src.services.player_source import (
    PlaybackSourceError,
    resolve_bluray_title,
    resolve_dvd_title,
    resolve_title,
)

_SECTOR_SIZE = 2048
_TT_SRPT_POINTER_OFFSET = 0xC4


def _build_video_ts_ifo(entries: list[tuple[int, int, int, int]], tt_srpt_sector: int = 1) -> bytes:
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


def _video_ts(tmp_path, entries):
    root = tmp_path / "VIDEO_TS"
    root.mkdir()
    (root / "VIDEO_TS.IFO").write_bytes(_build_video_ts_ifo(entries))
    return root


def _bdmv(tmp_path, playlists: dict[str, list[tuple[str, float]]]):
    """playlists: {"00000.mpls": [(clip_id, duration_s), ...], ...}"""
    root = tmp_path / "BDMV"
    (root / "PLAYLIST").mkdir(parents=True)
    (root / "STREAM").mkdir(parents=True)
    for name, clips in playlists.items():
        (root / "PLAYLIST" / name).write_bytes(build_mpls(clips))
        for clip_id, _ in clips:
            (root / "STREAM" / f"{clip_id}.m2ts").write_bytes(b"fake-clip-bytes")
    return root


# ─── DVD: einzelnes Segment ────────────────────────────────────────────────

def test_dvd_title_with_a_single_vob_segment(tmp_path):
    root = _video_ts(tmp_path, [(1, 1, 4, 1)])
    (root / "VTS_01_1.VOB").write_bytes(b"only-part")
    source = resolve_dvd_title(root, 0)
    assert source.disc_type == DiscType.DVD
    assert [p.name for p in source.segments] == ["VTS_01_1.VOB"]
    assert source.warnings == []


# ─── DVD: mehrere Segmente (mehrteiliger Titelsatz) ────────────────────────

def test_dvd_title_with_multiple_vob_segments_stays_one_title(tmp_path):
    root = _video_ts(tmp_path, [(1, 1, 8, 1)])
    (root / "VTS_01_1.VOB").write_bytes(b"part1")
    (root / "VTS_01_2.VOB").write_bytes(b"part2")
    (root / "VTS_01_3.VOB").write_bytes(b"part3")
    source = resolve_dvd_title(root, 0)
    assert [p.name for p in source.segments] == ["VTS_01_1.VOB", "VTS_01_2.VOB", "VTS_01_3.VOB"]


def test_dvd_title_selects_the_correct_title_by_index(tmp_path):
    root = _video_ts(tmp_path, [(1, 1, 3, 1), (2, 1, 5, 1)])
    (root / "VTS_01_1.VOB").write_bytes(b"t1")
    (root / "VTS_02_1.VOB").write_bytes(b"t2")
    assert [p.name for p in resolve_dvd_title(root, 0).segments] == ["VTS_01_1.VOB"]
    assert [p.name for p in resolve_dvd_title(root, 1).segments] == ["VTS_02_1.VOB"]


def test_dvd_title_sharing_a_vts_warns_instead_of_guessing(tmp_path):
    root = _video_ts(tmp_path, [(1, 1, 4, 1), (1, 2, 6, 1)])
    (root / "VTS_01_1.VOB").write_bytes(b"shared")
    source = resolve_dvd_title(root, 0)
    assert source.warnings
    assert "Titelsatz" in source.warnings[0]


def test_unknown_dvd_title_index_raises(tmp_path):
    root = _video_ts(tmp_path, [(1, 1, 4, 1)])
    (root / "VTS_01_1.VOB").write_bytes(b"x")
    with pytest.raises(PlaybackSourceError):
        resolve_dvd_title(root, 5)


def test_missing_video_ts_ifo_raises(tmp_path):
    root = tmp_path / "VIDEO_TS"
    root.mkdir()
    with pytest.raises(PlaybackSourceError, match="VIDEO_TS.IFO"):
        resolve_dvd_title(root, 0)


# ─── Blu-ray: eine Playlist mit einem Clip ─────────────────────────────────

def test_bluray_title_with_a_single_clip(tmp_path):
    root = _bdmv(tmp_path, {"00000.mpls": [("00000", 10.0)]})
    source = resolve_bluray_title(root, 0)
    assert source.disc_type == DiscType.BLURAY
    assert [p.name for p in source.segments] == ["00000.m2ts"]
    assert source.warnings == []


# ─── Blu-ray: eine Playlist mit mehreren Clips ──────────────────────────────

def test_bluray_title_with_multiple_clips_stays_one_title(tmp_path):
    root = _bdmv(tmp_path, {"00000.mpls": [("00000", 5.0), ("00001", 7.0), ("00002", 3.0)]})
    source = resolve_bluray_title(root, 0)
    assert [p.name for p in source.segments] == ["00000.m2ts", "00001.m2ts", "00002.m2ts"]


def test_bluray_multiple_playlists_selects_correct_title_by_index(tmp_path):
    root = _bdmv(tmp_path, {
        "00000.mpls": [("00000", 5.0)],
        "00001.mpls": [("00001", 20.0), ("00002", 20.0)],
    })
    assert [p.name for p in resolve_bluray_title(root, 0).segments] == ["00000.m2ts"]
    assert [p.name for p in resolve_bluray_title(root, 1).segments] == ["00001.m2ts", "00002.m2ts"]


def test_bluray_missing_referenced_clip_is_warned_and_skipped(tmp_path):
    root = _bdmv(tmp_path, {"00000.mpls": [("00000", 5.0)]})
    (root / "STREAM" / "00001.m2ts").unlink(missing_ok=True)   # ohnehin nie erzeugt
    # Playlist referenziert einen zweiten, tatsächlich fehlenden Clip:
    from src.services.bluray_authoring import build_mpls as _build
    (root / "PLAYLIST" / "00000.mpls").write_bytes(_build([("00000", 5.0), ("00099", 5.0)]))
    source = resolve_bluray_title(root, 0)
    assert [p.name for p in source.segments] == ["00000.m2ts"]
    assert source.warnings


def test_unknown_bluray_title_index_raises(tmp_path):
    root = _bdmv(tmp_path, {"00000.mpls": [("00000", 5.0)]})
    with pytest.raises(PlaybackSourceError):
        resolve_bluray_title(root, 3)


def test_missing_playlist_directory_raises(tmp_path):
    root = tmp_path / "BDMV"
    root.mkdir()
    with pytest.raises(PlaybackSourceError, match="PLAYLIST"):
        resolve_bluray_title(root, 0)


# ─── Generischer Einstieg (disc_type aus DiscContent bekannt) ──────────────

def test_resolve_title_dispatches_by_disc_type(tmp_path):
    dvd_root = tmp_path / "dvd"
    dvd_root.mkdir()
    video_ts = _video_ts(dvd_root, [(1, 1, 1, 1)])
    (video_ts / "VTS_01_1.VOB").write_bytes(b"x")
    assert resolve_title(dvd_root, DiscType.DVD, 0).disc_type == DiscType.DVD

    bd_root = tmp_path / "bd"
    bd_root.mkdir()
    _bdmv(bd_root, {"00000.mpls": [("00000", 1.0)]})
    assert resolve_title(bd_root, DiscType.BLURAY, 0).disc_type == DiscType.BLURAY


def test_resolve_title_rejects_unsupported_disc_type(tmp_path):
    from src.services.player_source import resolve_title
    with pytest.raises(PlaybackSourceError):
        resolve_title(tmp_path, DiscType.CD, 0)
