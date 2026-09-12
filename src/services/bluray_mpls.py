"""Minimaler Parser für BDMV-Playlist-Dateien (``BDMV/PLAYLIST/*.mpls``).

Liest ``PlayList()`` (welche Clips gehören in welcher Reihenfolge zu diesem
Titel, Gesamtlaufzeit) und ``PlayListMark()`` (echte Kapitelmarken) - die
beiden Strukturen, die einen Blu-ray-*Titel* tatsächlich definieren. Eine
einzelne ``*.m2ts``-Datei ist KEIN Titel: eine Playlist kann mehrere Clips
referenzieren (ein Titel aus mehreren Teilen), und derselbe Clip kann von
mehreren Playlists referenziert werden (z. B. Hauptfilm und ein Menü-
Trailer, die denselben Clip teilweise wiederverwenden) - beides wird hier
korrekt abgebildet, weil jede Playlist unabhängig geparst wird.

Bewusst NICHT geparst: die STN_table (Stream-Nummern-Tabelle je PlayItem,
die u. a. echte Sprachcodes für Audio-/Untertitelspuren enthält) und
Sub-Paths (alternative Winkel/Out-of-Mux-Audio). Audio-/Video-/Untertitel-
Spurdaten kommen deshalb weiterhin aus ffprobe auf den referenzierten Clip-
Dateien, nicht aus der Playlist selbst - siehe
P0_DISCCONTENT_IMPLEMENTATION.md, Abschnitt "Bekannte Einschränkungen".

Layout nach der öffentlich dokumentierten BD-ROM-BDMV-Struktur (u. a.
kompatibel zu libblurays ``mpls_parse.c``). In dieser Umgebung ohne
physisches Laufwerk NICHT gegen eine echte Blu-ray verifizierbar - Tests
verwenden handgebaute, strukturkonforme Byte-Fixtures, keine echten
Disc-Abbilder.
"""
from __future__ import annotations

from dataclasses import dataclass, field

_MAGIC = b"MPLS"
_KNOWN_VERSIONS = (b"0100", b"0200", b"0300")
_CLOCK_HZ = 45000.0
_ENTRY_MARK = 1


class MplsParseError(Exception):
    """Datei hat nicht die erwartete MPLS-Struktur."""


@dataclass
class MplsPlaylist:
    clip_ids: list[str] = field(default_factory=list)      # Wiedergabereihenfolge, Duplikate möglich
    duration_seconds: float = 0.0                           # Summe aller PlayItem-Dauern
    chapter_seconds: list[float] = field(default_factory=list)  # echte ENTRY_MARK-Startzeiten, sortiert


def parse_mpls(data: bytes) -> MplsPlaylist:
    if len(data) < 16 or data[0:4] != _MAGIC:
        raise MplsParseError("Kein MPLS-Header gefunden.")
    if data[4:8] not in _KNOWN_VERSIONS:
        raise MplsParseError(f"Unbekannte MPLS-Version: {data[4:8]!r}")

    playlist_start = int.from_bytes(data[8:12], "big")
    marks_start = int.from_bytes(data[12:16], "big")

    clip_ids, item_spans = _parse_playlist(data, playlist_start)
    duration_seconds = sum(out_t - in_t for _, in_t, out_t in item_spans) / _CLOCK_HZ
    chapter_seconds = _parse_marks(data, marks_start, item_spans)

    return MplsPlaylist(clip_ids=clip_ids, duration_seconds=duration_seconds,
                        chapter_seconds=chapter_seconds)


def _parse_playlist(data: bytes, offset: int) -> tuple[list[str], list[tuple[str, int, int]]]:
    # PlayList(): length(4) + reserved(2) + number_of_PlayItems(2) + number_of_SubPaths(2)
    if offset + 10 > len(data):
        raise MplsParseError("PlayList()-Header liegt außerhalb der Datei.")
    number_of_play_items = int.from_bytes(data[offset + 6:offset + 8], "big")

    pos = offset + 10
    clip_ids: list[str] = []
    spans: list[tuple[str, int, int]] = []
    for _ in range(number_of_play_items):
        if pos + 2 > len(data):
            raise MplsParseError("PlayItem() liegt außerhalb der Datei.")
        item_length = int.from_bytes(data[pos:pos + 2], "big")
        item_start = pos + 2
        # PlayItem(): Clip_Information_filename(5) + Clip_codec_identifier(4)
        #             + Flags(1) + STC_id(1) + IN_time(4) + OUT_time(4) = 19 Bytes
        if item_start + 19 > len(data):
            raise MplsParseError("PlayItem()-Kopf ist kürzer als erwartet.")
        clip_id = data[item_start:item_start + 5].decode("ascii", errors="replace")
        in_time = int.from_bytes(data[item_start + 11:item_start + 15], "big")
        out_time = int.from_bytes(data[item_start + 15:item_start + 19], "big")
        clip_ids.append(clip_id)
        spans.append((clip_id, in_time, out_time))
        pos += 2 + item_length
    return clip_ids, spans


def _parse_marks(data: bytes, offset: int, item_spans: list[tuple[str, int, int]]) -> list[float]:
    # PlayListMark(): length(4) + number_of_PlayListMarks(2), dann Einträge.
    if offset + 6 > len(data):
        return []
    number_of_marks = int.from_bytes(data[offset + 4:offset + 6], "big")
    pos = offset + 6
    timestamps: list[float] = []
    for _ in range(number_of_marks):
        # Mark(): reserved(1) + mark_type(1) + ref_to_PlayItem_id(2)
        #         + mark_time_stamp(4) + entry_ES_PID(2) + duration(4) = 14 Bytes
        if pos + 14 > len(data):
            break
        mark_type = data[pos + 1]
        ref_play_item_id = int.from_bytes(data[pos + 2:pos + 4], "big")
        mark_timestamp = int.from_bytes(data[pos + 4:pos + 8], "big")
        if mark_type == _ENTRY_MARK and 0 <= ref_play_item_id < len(item_spans):
            # mark_timestamp liegt auf der clip-eigenen Zeitachse des
            # referenzierten PlayItems. Umrechnung auf die Playlist-
            # Gesamtzeitachse: Summe der Dauern aller vorherigen PlayItems
            # plus Abstand des Marks von IN_time innerhalb seines PlayItems.
            preceding = sum(out_t - in_t for _, in_t, out_t in item_spans[:ref_play_item_id])
            _, in_time, _ = item_spans[ref_play_item_id]
            absolute_ticks = preceding + max(0, mark_timestamp - in_time)
            timestamps.append(absolute_ticks / _CLOCK_HZ)
        pos += 14
    return sorted(timestamps)
