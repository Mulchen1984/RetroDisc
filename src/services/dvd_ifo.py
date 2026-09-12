"""Minimaler Parser für den Title Search Pointer Table (TT_SRPT) aus
VIDEO_TS.IFO (DVD-Video Video Manager Information).

Liest ausschliesslich die Tabelle, die die *echten* logischen DVD-Titel
auflistet (nicht Dateien): pro Titel die Titelsatz-Zuordnung (VTS-Nummer,
VTS-interne Titelnummer), die echte Kapitelanzahl (``nr_of_ptts`` - "Parts
of Title") und die Winkelanzahl. Ein ``VTS_XX_Y.VOB`` ist damit ausdrücklich
KEIN eigenständiger Titel; die Zuordnung Titel -> Titelsatz kommt aus dieser
Tabelle, nicht aus einer Dateisystem-Gruppierung.

Absichtlich NICHT geparst: die VTS_PGCITI-/Zell-Tabellen in den einzelnen
``VTS_XX_0.IFO``-Dateien (echte Kapitel-Zeitstempel, Audio-/Subpicture-
Attributtabellen mit Sprachcodes). Das wäre ein deutlich größerer, in
diesem Block nicht beauftragter Arbeitsschritt - siehe
P0_DISCCONTENT_IMPLEMENTATION.md, Abschnitt "Bekannte Einschränkungen".

Layout nach der öffentlich dokumentierten DVD-Video-IFO-Struktur (u. a.
kompatibel zu libdvdreads ``ifo_types.h``: ``vmgi_mat_t``/``tt_srpt_t``/
``title_info_t``). In dieser Umgebung ohne physisches Laufwerk NICHT gegen
eine echte DVD verifizierbar - Tests verwenden handgebaute, strukturkonforme
Byte-Fixtures, keine echten Disc-Abbilder.
"""
from __future__ import annotations

from dataclasses import dataclass


class IfoParseError(Exception):
    """VIDEO_TS.IFO hat nicht die erwartete VMGI-Struktur."""


_VMG_IDENTIFIER = b"DVDVIDEO-VMG"
_TT_SRPT_POINTER_OFFSET = 0xC4  # 4-Byte-Sektorzeiger auf TT_SRPT, big-endian
_SECTOR_SIZE = 2048
_TT_SRPT_HEADER_SIZE = 8   # nr_of_srpts(2) + reserved(2) + last_byte(4)
_TITLE_INFO_SIZE = 12


@dataclass
class DvdTitleEntry:
    global_title_nr: int      # 1-basierte Position in TT_SRPT = globale Titelnummer
    vts_number: int           # Titelsatz (VTS_XX), 1-basiert
    vts_title_number: int     # Titelnummer innerhalb des Titelsatzes, 1-basiert
    chapter_count: int        # nr_of_ptts - echte Anzahl Kapitel/"Parts of Title"
    angle_count: int          # nr_of_angles


def parse_tt_srpt(data: bytes) -> list[DvdTitleEntry]:
    """Liest die Titeltabelle aus dem Inhalt einer VIDEO_TS.IFO-Datei."""
    if len(data) < _TT_SRPT_POINTER_OFFSET + 4:
        raise IfoParseError("Datei zu kurz für eine VIDEO_TS.IFO-Kopfstruktur.")
    if data[:12] != _VMG_IDENTIFIER:
        raise IfoParseError("Kein VMGI-Header ('DVDVIDEO-VMG') gefunden.")

    sector = int.from_bytes(data[_TT_SRPT_POINTER_OFFSET:_TT_SRPT_POINTER_OFFSET + 4], "big")
    table_offset = sector * _SECTOR_SIZE
    if table_offset + _TT_SRPT_HEADER_SIZE > len(data):
        raise IfoParseError("TT_SRPT-Zeiger verweist außerhalb der Datei.")

    nr_of_srpts = int.from_bytes(data[table_offset:table_offset + 2], "big")
    entries_offset = table_offset + _TT_SRPT_HEADER_SIZE
    needed = entries_offset + nr_of_srpts * _TITLE_INFO_SIZE
    if needed > len(data):
        raise IfoParseError("TT_SRPT-Tabelle reicht über das Dateiende hinaus.")

    entries: list[DvdTitleEntry] = []
    for i in range(nr_of_srpts):
        off = entries_offset + i * _TITLE_INFO_SIZE
        nr_of_angles = data[off + 1]
        nr_of_ptts = int.from_bytes(data[off + 2:off + 4], "big")
        vts_number = data[off + 6]
        vts_title_number = data[off + 7]
        entries.append(DvdTitleEntry(
            global_title_nr=i + 1, vts_number=vts_number, vts_title_number=vts_title_number,
            chapter_count=nr_of_ptts, angle_count=nr_of_angles,
        ))
    return entries
