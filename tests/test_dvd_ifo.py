"""Tests für den TT_SRPT-Parser (echte DVD-Titeltabelle aus VIDEO_TS.IFO)."""
from __future__ import annotations

import pytest

from src.services.dvd_ifo import IfoParseError, parse_tt_srpt

_SECTOR_SIZE = 2048
_TT_SRPT_POINTER_OFFSET = 0xC4


def _build_video_ts_ifo(entries: list[tuple[int, int, int, int]], tt_srpt_sector: int = 1) -> bytes:
    """entries: Liste von (vts_number, vts_title_number, chapter_count, angle_count)."""
    header = bytearray(_SECTOR_SIZE)
    header[0:12] = b"DVDVIDEO-VMG"
    header[_TT_SRPT_POINTER_OFFSET:_TT_SRPT_POINTER_OFFSET + 4] = tt_srpt_sector.to_bytes(4, "big")

    table = bytearray()
    table += len(entries).to_bytes(2, "big")   # nr_of_srpts
    table += b"\x00\x00"                        # reserved
    table += (0).to_bytes(4, "big")              # last_byte (ungenutzt vom Parser)
    for vts_number, vts_ttn, chapter_count, angle_count in entries:
        entry = bytearray(12)
        entry[0] = 0x03                          # title_type (ungenutzt vom Parser)
        entry[1] = angle_count
        entry[2:4] = chapter_count.to_bytes(2, "big")
        entry[4:6] = b"\x00\x00"                 # parental_id (ungenutzt)
        entry[6] = vts_number
        entry[7] = vts_ttn
        entry[8:12] = (0).to_bytes(4, "big")      # title_set_sector (ungenutzt vom Parser)
        table += entry

    data = bytes(header) + b"\x00" * (tt_srpt_sector * _SECTOR_SIZE - len(header)) + bytes(table)
    return data


def test_parses_single_title_single_vts():
    data = _build_video_ts_ifo([(1, 1, 8, 1)])
    entries = parse_tt_srpt(data)
    assert len(entries) == 1
    e = entries[0]
    assert e.global_title_nr == 1
    assert e.vts_number == 1
    assert e.vts_title_number == 1
    assert e.chapter_count == 8
    assert e.angle_count == 1


def test_parses_multiple_titles_across_different_vts():
    data = _build_video_ts_ifo([(1, 1, 3, 1), (2, 1, 12, 1), (3, 1, 1, 1)])
    entries = parse_tt_srpt(data)
    assert [e.global_title_nr for e in entries] == [1, 2, 3]
    assert [e.vts_number for e in entries] == [1, 2, 3]
    assert entries[1].chapter_count == 12


def test_parses_multiple_titles_sharing_one_vts():
    # Zwei Titel im selben Titelsatz, unterschieden durch vts_title_number.
    data = _build_video_ts_ifo([(1, 1, 4, 1), (1, 2, 6, 1)])
    entries = parse_tt_srpt(data)
    assert len(entries) == 2
    assert entries[0].vts_number == entries[1].vts_number == 1
    assert entries[0].vts_title_number == 1
    assert entries[1].vts_title_number == 2


def test_zero_titles_is_valid():
    data = _build_video_ts_ifo([])
    assert parse_tt_srpt(data) == []


def test_rejects_wrong_magic():
    data = bytearray(_build_video_ts_ifo([(1, 1, 1, 1)]))
    data[0:12] = b"NOT-A-VMG!!!"
    with pytest.raises(IfoParseError, match="VMGI"):
        parse_tt_srpt(bytes(data))


def test_rejects_truncated_file():
    with pytest.raises(IfoParseError):
        parse_tt_srpt(b"DVDVIDEO-VMG")


def test_rejects_tt_srpt_pointer_outside_file():
    header = bytearray(_SECTOR_SIZE)
    header[0:12] = b"DVDVIDEO-VMG"
    header[_TT_SRPT_POINTER_OFFSET:_TT_SRPT_POINTER_OFFSET + 4] = (9999).to_bytes(4, "big")
    with pytest.raises(IfoParseError, match="außerhalb"):
        parse_tt_srpt(bytes(header))
