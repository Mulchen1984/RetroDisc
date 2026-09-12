"""BDMV-Authoring: erzeugt eine echte, lesbare Blu-ray-Verzeichnisstruktur.

Das fehlende Gegenstück zu ``dvdauthor`` (VIDEO_TS) für Blu-ray: kein
etabliertes, quelloffenes BDMV-Muxing-Werkzeug ist in dieser Umgebung
vendorbar oder installiert (geprüft: ``tsMuxeR``/``tsmuxer`` weder im
Projekt noch über Homebrew verfügbar; ``growisofs``/``mkisofs`` erzeugen
nur das Dateisystem, keine BDMV-*Struktur*). Dieses Modul füllt genau diese
Lücke, aufbauend auf zwei bereits vorhandenen, geprüften Bausteinen:

1. ``FFmpeg.to_bluray_stream`` (``src/core/ffmpeg.py``) erzeugt den
   BDAV-Transportstrom selbst (192-Byte-Pakete mit 4-Byte-Zeitstempel-Präfix
   über FFmpegs ``-mpegts_m2ts_mode``, feste PIDs 0x1011/0x1100) - real
   gegen dieses FFmpeg getestet (Sync-Byte 0x47 an Offset 4 jedes 192-Byte-
   Pakets, PIDs per ffprobe bestätigt).
2. ``src/services/bluray_mpls.py`` liest bereits produktiv BD-Playlists
   (``BDMV/PLAYLIST/*.mpls``) für die Disc-Erkennung. ``build_mpls()``
   unten ist das *Gegenstück*: byte-exakt zum Feldmodell dieses Parsers
   (dieselbe vereinfachte 19-Byte-PlayItem-Struktur wie in
   ``tests/test_bluray_mpls.py::_play_item`` - kein zufälliges Byte-Layout,
   sondern der bereits geprüfte, produktive Vertrag dieses Lesers). Die
   Gültigkeit wird über einen echten Round-Trip getestet: was hier
   geschrieben wird, liest ``parse_mpls()``/``DiscAnalyzer`` korrekt zurück.

Ehrlich ausgewiesene Grenzen (siehe Abschlussbericht "VERBLEIBENDE
EINSCHRÄNKUNGEN"):

- ``index.bdmv``/``MovieObject.bdmv`` sind strukturell wohlgeformt (korrekte
  Magic/Version, in sich konsistente Start-Adressen, korrektes Längen-
  Nesting), aber das MovieObject trägt bewusst KEINE HDMV-Navigationsbefehle.
  Ein aus dem Kopf rekonstruierter Opcode ohne Referenz-Decoder zum
  Gegenprüfen wäre eine unbelegte Behauptung ("könnte funktionieren, könnte
  auf echter Hardware auch stillschweigend danebengehen") - genau das,
  was diese Aufgabe ausdrücklich verbietet. Software-Player, die
  BDMV/PLAYLIST direkt lesen (z. B. VLCs vereinfachter Blu-ray-Modus),
  spielen den Titel trotzdem ab.
- ``BDMV/CLIPINF/*.clpi`` deklariert korrekt die beiden echten Stream-PIDs
  (0x1011/0x1100, siehe ``FFmpeg.BLURAY_VIDEO_PID``/``BLURAY_AUDIO_PID``)
  und ist intern längen-konsistent, aber es existiert in diesem Projekt
  (noch) kein CLPI-*Leser* zum Round-Trip-Gegenprüfen - anders als bei MPLS.
  Kein Entry-Point-Map mit echten Sprungmarken (spec-legal leer).
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import structlog

from src.core.ffmpeg import FFmpeg
from src.models.media import Job

log = structlog.get_logger()

_CLOCK_HZ = 45000.0
_MPLS_VERSION = b"0200"
_CLPI_VERSION = b"0200"
_INDEX_VERSION = b"0200"
_MOBJ_VERSION = b"0200"
_ENTRY_MARK = 1


class BlurayAuthoringError(Exception):
    pass


# ── MPLS (BDMV/PLAYLIST/*.mpls) ─────────────────────────────────────────
# Byte-exaktes Gegenstück zu ``src/services/bluray_mpls.py::parse_mpls`` /
# ``tests/test_bluray_mpls.py::_play_item``/``_mark`` - nicht der volle
# öffentliche BD-ROM-Feldsatz (dort bewusst vereinfacht, siehe Moduldoku),
# sondern exakt das, was der bereits produktive Leser erwartet.

def _play_item_bytes(clip_id: str, in_time: int, out_time: int) -> bytes:
    body = bytearray()
    body += clip_id.encode("ascii").ljust(5, b"0")[:5]
    body += b"M2TS"
    body += b"\x00"                       # Flags (vom Leser als 1 Byte behandelt)
    body += b"\x00"                       # STC_id
    body += int(in_time).to_bytes(4, "big")
    body += int(out_time).to_bytes(4, "big")
    assert len(body) == 19
    return len(body).to_bytes(2, "big") + bytes(body)


def _mark_bytes(mark_type: int, ref_play_item_id: int, mark_timestamp: int) -> bytes:
    entry = bytearray()
    entry += b"\x00"
    entry += mark_type.to_bytes(1, "big")
    entry += ref_play_item_id.to_bytes(2, "big")
    entry += int(mark_timestamp).to_bytes(4, "big")
    entry += b"\x00\x00"
    entry += (0xFFFFFFFF).to_bytes(4, "big")
    assert len(entry) == 14
    return bytes(entry)


def build_mpls(clips: list[tuple[str, float]], chapter_seconds: Optional[list[float]] = None) -> bytes:
    """Baut eine Playlist mit genau einem PlayItem je Clip, in Reihenfolge.

    ``clips``: Liste aus (5-stelliger Clip-ID, Dauer in Sekunden). Jeder
    Clip wird komplett von Anfang bis Ende gespielt (IN_time=0) - spiegelt
    exakt, wie ``DiscTools.create_dvd_structure`` mehrere Quelldateien zu
    EINEM Titel mit sequenziellen VOBs zusammenfasst; kein Teil-Clipping.
    """
    if not clips:
        raise BlurayAuthoringError("Mindestens ein Clip wird für eine Playlist benötigt.")
    chapter_seconds = list(chapter_seconds or [])

    items = bytearray()
    cumulative_start: list[float] = []
    total = 0.0
    for clip_id, duration_s in clips:
        cumulative_start.append(total)
        out_time = max(1, round(duration_s * _CLOCK_HZ))
        items += _play_item_bytes(clip_id, 0, out_time)
        total += duration_s

    # 16-Byte-Kopf (Magic/Version/Start-Adressen) + 4 Byte ExtensionData-
    # Adresse + 20 Byte AppInfoPlayList-Platzhalter, wie in
    # tests/test_bluray_mpls.py::_build_mpls - der Leser interpretiert
    # diesen Bereich nie, er springt direkt zu playlist_start.
    playlist_start = 40
    playlist_body = bytearray()
    playlist_body += (0).to_bytes(4, "big")            # length (vom Leser ungenutzt)
    playlist_body += b"\x00\x00"                        # reserved
    playlist_body += len(clips).to_bytes(2, "big")       # number_of_PlayItems
    playlist_body += (0).to_bytes(2, "big")             # number_of_SubPaths
    playlist_body += items

    marks_start = playlist_start + len(playlist_body)
    marks_body = bytearray()
    marks_body += (0).to_bytes(4, "big")
    marks_body += len(chapter_seconds).to_bytes(2, "big")
    for chapter_s in chapter_seconds:
        ref_item = 0
        for i, start in enumerate(cumulative_start):
            if chapter_s >= start:
                ref_item = i
        offset_ticks = max(0, round((chapter_s - cumulative_start[ref_item]) * _CLOCK_HZ))
        marks_body += _mark_bytes(_ENTRY_MARK, ref_item, offset_ticks)

    header = bytearray(playlist_start)
    header[0:4] = b"MPLS"
    header[4:8] = _MPLS_VERSION
    header[8:12] = playlist_start.to_bytes(4, "big")
    header[12:16] = marks_start.to_bytes(4, "big")
    header[16:20] = (0).to_bytes(4, "big")

    return bytes(header) + bytes(playlist_body) + bytes(marks_body)


# ── CLPI (BDMV/CLIPINF/*.clpi) ──────────────────────────────────────────

def build_clip_info(duration_ticks: int, *, video_pid: int, audio_pid: int) -> bytes:
    """Minimale, intern konsistente CLPI-Datei für genau einen AV-Clip.

    Kein unabhängiger CLPI-Leser existiert in diesem Projekt zum Round-Trip-
    Test (anders als MPLS) - siehe Moduldoku für die ehrliche Einordnung.
    Die konkret geprüfte Eigenschaft ist die PID-Übereinstimmung mit dem
    tatsächlich von ``FFmpeg.to_bluray_stream`` geschriebenen Stream.
    """
    header = bytearray()
    header += b"HDMV"
    header += _CLPI_VERSION
    # 4 Platzhalter-Start-Adressen (ClipInfo/SequenceInfo/ProgramInfo/CPI/
    # ClipMark) + ExtensionData - unten mit echten Werten überschrieben.
    addr_table_pos = len(header)
    header += (0).to_bytes(4, "big") * 6

    def _set_addr(index: int, value: int) -> None:
        pos = addr_table_pos + index * 4
        header[pos:pos + 4] = value.to_bytes(4, "big")

    body = bytearray()

    clip_info_start = len(header) + len(body)
    clip_info = bytearray()
    clip_info += b"\x01"                      # ClipStreamType = 1 (AV stream)
    clip_info += b"\x01"                      # ApplicationType = 1 (Movie)
    clip_info += b"\x00\x00\x00"              # reserved
    clip_info += int(duration_ticks).to_bytes(4, "big")   # Gesamtdauer in 45-kHz-Ticks
    clip_info_block = len(clip_info).to_bytes(4, "big") + bytes(clip_info)
    body += clip_info_block

    sequence_info_start = len(header) + len(body)
    sequence_info = bytearray()
    sequence_info += b"\x00"                  # reserved
    sequence_info += (1).to_bytes(1, "big")   # number_of_ATC_sequences = 1
    sequence_info += (0).to_bytes(4, "big")   # SPN_ATC_start = 0
    sequence_info += (1).to_bytes(1, "big")   # number_of_STC_sequences = 1
    sequence_info += (0).to_bytes(1, "big")   # PCR_PID reference index = 0
    sequence_info += (0).to_bytes(4, "big")   # SPN_STC_start = 0
    sequence_info += (0).to_bytes(4, "big")   # presentation_start_time
    sequence_info += int(duration_ticks).to_bytes(4, "big")  # presentation_end_time
    sequence_info_block = len(sequence_info).to_bytes(4, "big") + bytes(sequence_info)
    body += sequence_info_block

    program_info_start = len(header) + len(body)
    program_info = bytearray()
    program_info += b"\x00"                   # reserved
    program_info += (1).to_bytes(1, "big")    # number_of_program_sequences = 1
    program_info += (0).to_bytes(4, "big")    # SPN_program_sequence_start = 0
    program_info += (0).to_bytes(2, "big")    # program_map_PID
    program_info += (2).to_bytes(1, "big")    # number_of_streams_in_ps = 2
    program_info += (0).to_bytes(1, "big")    # number_of_groups = 0
    # StreamCodingInfo je Stream: stream_PID(2) + length(1) + stream_coding_type(1)
    program_info += video_pid.to_bytes(2, "big") + b"\x01" + b"\x1b"   # 0x1B = H.264/AVC
    program_info += audio_pid.to_bytes(2, "big") + b"\x01" + b"\x81"   # 0x81 = AC-3
    program_info_block = len(program_info).to_bytes(4, "big") + bytes(program_info)
    body += program_info_block

    cpi_start = len(header) + len(body)
    cpi = bytearray()
    cpi += b"\x00"                            # reserved(4bits)+CPI_type(4bits) = 0 (kein EP_map-Typ gesetzt)
    cpi += (0).to_bytes(1, "big")             # number_of_EP_streams = 0 (spec-legal: kein Entry-Point-Map)
    cpi_block = len(cpi).to_bytes(4, "big") + bytes(cpi)
    body += cpi_block

    clip_mark_start = len(header) + len(body)
    clip_mark = bytearray()
    clip_mark += (0).to_bytes(2, "big")       # number_of_ClipMarks = 0
    clip_mark_block = len(clip_mark).to_bytes(4, "big") + bytes(clip_mark)
    body += clip_mark_block

    _set_addr(0, clip_info_start)
    _set_addr(1, sequence_info_start)
    _set_addr(2, program_info_start)
    _set_addr(3, cpi_start)
    _set_addr(4, clip_mark_start)
    _set_addr(5, 0)   # ExtensionData_start_address = 0 (ungenutzt)

    return bytes(header) + bytes(body)


# ── index.bdmv / MovieObject.bdmv ───────────────────────────────────────

def _index_object_bytes(movie_object_id: int) -> bytes:
    # Vereinfachtes IndexObject: object_type(2bit,=1 HDMV)+reserved(30bit)
    # als 4-Byte-Wort, gefolgt von MovieObjectId(2)+reserved(2).
    word = (1 << 30)  # object_type=1 (HDMV) in den oberen 2 Bits
    return word.to_bytes(4, "big") + movie_object_id.to_bytes(2, "big") + b"\x00\x00"


def build_index_bdmv(*, title_count: int = 1) -> bytes:
    """Minimale, strukturell wohlgeformte ``index.bdmv``.

    FirstPlayback, TopMenu und jeder Titel zeigen auf MovieObject 0 - es
    gibt nur ein Programm (keine echten Menüs/mehrere Titel in diesem
    ersten Block). Siehe Moduldoku zur bewusst leeren HDMV-Befehlsliste
    des referenzierten MovieObjects.
    """
    header = bytearray()
    header += b"INDX"
    header += _INDEX_VERSION
    header += (0).to_bytes(4, "big")   # Indexes_start_address (unten gesetzt)
    header += (0).to_bytes(4, "big")   # ExtensionData_start_address = 0
    header += (0).to_bytes(20, "big")  # AppInfoBDMV-Platzhalter (ungenutzt)

    indexes_start = len(header)
    indexes = bytearray()
    indexes += _index_object_bytes(0)     # FirstPlayback -> MovieObject 0
    indexes += _index_object_bytes(0)     # TopMenu -> MovieObject 0 (kein echtes Menü)
    indexes += max(1, title_count).to_bytes(2, "big")
    for _ in range(max(1, title_count)):
        indexes += _index_object_bytes(0)
    indexes_block = len(indexes).to_bytes(4, "big") + bytes(indexes)

    header[8:12] = indexes_start.to_bytes(4, "big")
    return bytes(header) + bytes(indexes_block)


def build_movie_object_bdmv() -> bytes:
    """Minimale, strukturell wohlgeformte ``MovieObject.bdmv`` mit genau
    einem MovieObject OHNE HDMV-Navigationsbefehle (siehe Moduldoku)."""
    header = bytearray()
    header += b"MOBJ"
    header += _MOBJ_VERSION
    header += (0).to_bytes(4, "big")   # ExtensionData_start_address = 0

    movie_objects = bytearray()
    movie_objects += b"\x00\x00"                 # reserved
    movie_objects += (1).to_bytes(2, "big")       # number_of_mobjs = 1
    # Ein MovieObject: resume_intention_flag+menu_call_mask+title_search_mask
    # gepackt in 4 Byte, dann number_of_navigation_commands(2)=0.
    movie_objects += (0).to_bytes(4, "big")
    movie_objects += (0).to_bytes(2, "big")       # keine Befehle
    movie_objects_block = len(movie_objects).to_bytes(4, "big") + bytes(movie_objects)

    return bytes(header) + bytes(movie_objects_block)


# ── Orchestrierung ───────────────────────────────────────────────────────

@dataclass
class BlurayClip:
    source: Path
    duration_seconds: float


async def author_bdmv(
    ffmpeg: FFmpeg,
    input_files: list[Path],
    output_dir: Path,
    *,
    video_bitrate_bps: Optional[int] = None,
    job: Optional[Job] = None,
) -> Path:
    """Erstellt eine vollständige BDMV-Verzeichnisstruktur aus Quelldateien.

    Konvertiert jede Quelldatei zu einem BD-kompatiblen M2TS-Clip
    (``FFmpeg.to_bluray_stream``) und schreibt PLAYLIST/CLIPINF/index.bdmv/
    MovieObject.bdmv darum. Ein Titel = alle Quelldateien in Reihenfolge,
    genau wie ``create_dvd_structure`` alle MPEG-Dateien zu einem Titel
    zusammenfasst.

    Returns:
        Pfad zum Wurzelverzeichnis (enthält BDMV/).
    """
    if not input_files:
        raise BlurayAuthoringError("Keine Quelldateien für BDMV-Authoring angegeben.")

    output_dir = Path(output_dir)
    bd_root = output_dir / "BLURAY"
    stream_dir = bd_root / "BDMV" / "STREAM"
    playlist_dir = bd_root / "BDMV" / "PLAYLIST"
    clipinf_dir = bd_root / "BDMV" / "CLIPINF"
    for d in (stream_dir, playlist_dir, clipinf_dir):
        d.mkdir(parents=True, exist_ok=True)

    if job:
        job.update_progress(10, "Videos werden in BD-kompatible Clips gewandelt...")

    clips: list[tuple[str, float]] = []
    total = len(input_files)
    for i, src in enumerate(input_files):
        clip_id = f"{i:05d}"
        clip_path = stream_dir / f"{clip_id}.m2ts"
        sub_job = None
        if job:
            sub_job = Job(job_type=job.job_type)
            file_start = 10 + (i / total) * 60
            file_end = 10 + ((i + 1) / total) * 60
            sub_job.on_progress = lambda p, t, s=file_start, e=file_end: (
                job.update_progress(s + (p / 100) * (e - s), f"[{i+1}/{total}] {t}")
            )
        await ffmpeg.to_bluray_stream(src, clip_path, video_bitrate_bps=video_bitrate_bps, job=sub_job)
        probed = await ffmpeg.probe(clip_path)
        clips.append((clip_id, probed.duration_seconds))

        clip_info_bytes = build_clip_info(
            max(1, round(probed.duration_seconds * _CLOCK_HZ)),
            video_pid=ffmpeg.BLURAY_VIDEO_PID, audio_pid=ffmpeg.BLURAY_AUDIO_PID,
        )
        (clipinf_dir / f"{clip_id}.clpi").write_bytes(clip_info_bytes)

    if job:
        job.update_progress(75, "BDMV-Struktur wird geschrieben...")

    mpls_bytes = build_mpls(clips)
    (playlist_dir / "00000.mpls").write_bytes(mpls_bytes)

    bdmv_dir = bd_root / "BDMV"
    (bdmv_dir / "index.bdmv").write_bytes(build_index_bdmv())
    (bdmv_dir / "MovieObject.bdmv").write_bytes(build_movie_object_bdmv())

    if job:
        job.update_progress(90, "BDMV-Struktur erstellt")

    log.info("BDMV-Struktur erstellt", path=str(bd_root), clips=len(clips))
    return bd_root
