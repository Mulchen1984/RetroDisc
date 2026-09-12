"""Tests für den MPLS-Playlist-Parser (echte Blu-ray-Titelstruktur)."""
from __future__ import annotations

import pytest

from src.services.bluray_mpls import MplsParseError, parse_mpls

_ENTRY_MARK = 1
_LINK_POINT = 2


def _play_item(clip_id: str, in_time: int, out_time: int) -> bytes:
    body = bytearray()
    body += clip_id.encode("ascii").ljust(5, b"0")
    body += b"M2TS"
    body += b"\x00"          # flags
    body += b"\x00"          # STC_id
    body += in_time.to_bytes(4, "big")
    body += out_time.to_bytes(4, "big")
    assert len(body) == 19
    return len(body).to_bytes(2, "big") + bytes(body)


def _mark(mark_type: int, ref_play_item_id: int, mark_timestamp: int) -> bytes:
    entry = bytearray()
    entry += b"\x00"                                    # reserved
    entry += mark_type.to_bytes(1, "big")
    entry += ref_play_item_id.to_bytes(2, "big")
    entry += mark_timestamp.to_bytes(4, "big")
    entry += b"\x00\x00"                                 # entry_ES_PID (ungenutzt)
    entry += (0xFFFFFFFF).to_bytes(4, "big")              # duration (ungenutzt)
    assert len(entry) == 14
    return bytes(entry)


def _build_mpls(items: list[tuple[str, int, int]], marks: list[tuple[int, int, int]] = ()) -> bytes:
    """items: (clip_id, in_time, out_time). marks: (mark_type, ref_play_item_id, timestamp)."""
    playlist_start = 40
    playlist_body = bytearray()
    playlist_body += (0).to_bytes(4, "big")                       # length (ungenutzt vom Parser)
    playlist_body += b"\x00\x00"                                   # reserved
    playlist_body += len(items).to_bytes(2, "big")                 # number_of_PlayItems
    playlist_body += (0).to_bytes(2, "big")                        # number_of_SubPaths
    for clip_id, in_time, out_time in items:
        playlist_body += _play_item(clip_id, in_time, out_time)

    marks_start = playlist_start + len(playlist_body)
    marks_body = bytearray()
    marks_body += (0).to_bytes(4, "big")                           # length (ungenutzt vom Parser)
    marks_body += len(marks).to_bytes(2, "big")                    # number_of_PlayListMarks
    for mark_type, ref_id, ts in marks:
        marks_body += _mark(mark_type, ref_id, ts)

    header = bytearray(playlist_start)
    header[0:4] = b"MPLS"
    header[4:8] = b"0200"
    header[8:12] = playlist_start.to_bytes(4, "big")
    header[12:16] = marks_start.to_bytes(4, "big")
    header[16:20] = (0).to_bytes(4, "big")

    return bytes(header) + bytes(playlist_body) + bytes(marks_body)


# ─── PlayList(): Clips und Laufzeit ──────────────────────────────────────

def test_single_clip_playlist():
    data = _build_mpls([("00001", 0, 45000 * 10)])   # 10 Sekunden
    playlist = parse_mpls(data)
    assert playlist.clip_ids == ["00001"]
    assert playlist.duration_seconds == pytest.approx(10.0)
    assert playlist.chapter_seconds == []


def test_multi_clip_playlist_sums_durations_in_order():
    data = _build_mpls([
        ("00001", 0, 45000 * 5),
        ("00002", 0, 45000 * 7),
        ("00003", 45000 * 2, 45000 * 9),   # 7 Sekunden Nettodauer trotz IN_time != 0
    ])
    playlist = parse_mpls(data)
    assert playlist.clip_ids == ["00001", "00002", "00003"]
    assert playlist.duration_seconds == pytest.approx(5.0 + 7.0 + 7.0)


def test_same_clip_referenced_twice_within_one_playlist_keeps_order():
    data = _build_mpls([("00001", 0, 45000 * 3), ("00001", 0, 45000 * 3)])
    playlist = parse_mpls(data)
    assert playlist.clip_ids == ["00001", "00001"]
    assert playlist.duration_seconds == pytest.approx(6.0)


# ─── PlayListMark(): echte Kapitel ───────────────────────────────────────

def test_entry_marks_become_chapters_with_absolute_timeline():
    data = _build_mpls(
        items=[("00001", 0, 45000 * 10), ("00002", 0, 45000 * 10)],
        marks=[
            (_ENTRY_MARK, 0, 0),                 # Kapitel bei 0s (erster Clip)
            (_ENTRY_MARK, 0, 45000 * 4),          # Kapitel bei 4s (noch im ersten Clip)
            (_ENTRY_MARK, 1, 45000 * 2),          # Kapitel bei 10s+2s=12s (zweiter Clip)
        ],
    )
    playlist = parse_mpls(data)
    assert playlist.chapter_seconds == pytest.approx([0.0, 4.0, 12.0])


def test_non_entry_marks_are_ignored():
    data = _build_mpls(
        items=[("00001", 0, 45000 * 10)],
        marks=[(_LINK_POINT, 0, 45000 * 5), (_ENTRY_MARK, 0, 45000 * 1)],
    )
    playlist = parse_mpls(data)
    assert playlist.chapter_seconds == pytest.approx([1.0])


def test_no_marks_section_yields_no_chapters_not_a_fabricated_placeholder():
    data = _build_mpls(items=[("00001", 0, 45000 * 10)], marks=[])
    playlist = parse_mpls(data)
    assert playlist.chapter_seconds == []


# ─── Fehlerfälle ─────────────────────────────────────────────────────────

def test_rejects_wrong_magic():
    data = bytearray(_build_mpls([("00001", 0, 45000)]))
    data[0:4] = b"XXXX"
    with pytest.raises(MplsParseError, match="MPLS-Header"):
        parse_mpls(bytes(data))


def test_rejects_unknown_version():
    data = bytearray(_build_mpls([("00001", 0, 45000)]))
    data[4:8] = b"9999"
    with pytest.raises(MplsParseError, match="Version"):
        parse_mpls(bytes(data))
