"""Löst einen logischen DiscContent-Titel zu einer abspielbaren Dateiliste auf.

Nutzt ausschließlich die bereits vorhandenen Parser - ``dvd_ifo.parse_tt_srpt``
für DVD, ``bluray_mpls.parse_mpls`` für Blu-ray - dieselben, die
``DiscAnalyzer`` bereits für ``get_disc_content`` verwendet. Keine parallele
Disc-Analyse: ``DiscTitle`` (das an die UI ausgelieferte Modell) trägt bewusst
nur aggregierte Metadaten (Gesamtdauer, Gesamtgröße, Kapitel), keine
Datei-Segmentliste - das hier ist die fehlende Übersetzung "welcher Titel-
Index -> welche Dateien in welcher Reihenfolge", exakt mit derselben
Enumerationsreihenfolge und denselben Filterregeln wie
``DiscAnalyzer._dvd_titles``/``_bluray_titles``, damit ein in der UI aus
``get_disc_content`` gewählter Titel-Index hier auf denselben physischen
Titel trifft.

Absichtlich vereinfacht (dieselbe Grenze wie im übrigen Projekt bereits
dokumentiert, siehe ``disc_analyzer.py``/``ripper.py``):

* DVD: ein Titel wird als der komplette VOB-Satz seines Titelsatzes
  wiedergegeben (wie ``ripper.py::_dvd_title_files`` es für den Haupttitel
  bereits tut) - keine PGC-/Zell-genaue Auswahl. Teilt sich der Titelsatz
  mehrere Titel, wird das als Warnung ausgewiesen statt stillschweigend zu
  raten.
* Blu-ray: jeder von der Playlist referenzierte Clip wird komplett gespielt
  (IN_time=0, OUT_time=Clip-Ende) - keine Teil-Clip-Kürzung anhand der
  PlayItem-IN/OUT-Zeiten. Das deckt jede von RetroDiscs eigenem
  BDMV-Authoring erzeugte Disc exakt ab (siehe ``bluray_authoring.py``) und
  die overwiegende Mehrheit einfacher Discs; echte teilweise-getrimmte
  PlayItems (unüblich, aber möglich) werden als Ganzes statt gekürzt
  gespielt - eine Einschränkung, keine Falschangabe.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from src.models.media import DiscType
from src.services.bluray_mpls import MplsParseError, parse_mpls
from src.services.dvd_ifo import IfoParseError, parse_tt_srpt


class PlaybackSourceError(Exception):
    """Ein Titel konnte nicht zu einer abspielbaren Dateiliste aufgelöst werden."""


@dataclass
class PlaybackSource:
    disc_type: DiscType
    segments: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def resolve_dvd_title(video_ts: Path, title_index: int) -> PlaybackSource:
    """``title_index`` ist 0-basiert, identisch zu ``DiscTitle.index`` aus
    ``DiscAnalyzer._dvd_titles`` (dort: ``entry.global_title_nr - 1``)."""
    ifo_path = video_ts / "VIDEO_TS.IFO"
    if not ifo_path.is_file():
        raise PlaybackSourceError("VIDEO_TS.IFO nicht gefunden.")
    try:
        entries = parse_tt_srpt(ifo_path.read_bytes())
    except IfoParseError as exc:
        raise PlaybackSourceError(f"VIDEO_TS.IFO konnte nicht gelesen werden: {exc}") from exc

    entry = next((e for e in entries if e.global_title_nr - 1 == title_index), None)
    if entry is None:
        raise PlaybackSourceError(f"Titel {title_index} existiert nicht auf dieser DVD.")

    vts_counts = Counter(e.vts_number for e in entries)
    vobs = sorted(video_ts.glob(f"VTS_{entry.vts_number:02d}_[1-9].VOB"))
    if not vobs:
        raise PlaybackSourceError(
            f"Keine VOB-Dateien für Titelsatz {entry.vts_number} gefunden."
        )

    warnings: list[str] = []
    if vts_counts[entry.vts_number] > 1:
        warnings.append(
            "Dieser Titel teilt sich einen Titelsatz mit anderen Titeln; ohne "
            "PGC-/Zell-Analyse sind exakte Titelgrenzen nicht auflösbar - der "
            "gesamte Titelsatz wird wiedergegeben."
        )
    return PlaybackSource(disc_type=DiscType.DVD, segments=vobs, warnings=warnings)


def resolve_bluray_title(bdmv: Path, title_index: int) -> PlaybackSource:
    """``title_index`` ist 0-basiert, identisch zur Reihenfolge in
    ``DiscAnalyzer._bluray_titles`` (sortierte ``*.mpls``-Dateien, nur
    Playlists mit mindestens einem Clip zählen als Titel)."""
    playlist_dir = bdmv / "PLAYLIST"
    stream_dir = bdmv / "STREAM"
    if not playlist_dir.is_dir():
        raise PlaybackSourceError("BDMV/PLAYLIST nicht gefunden.")

    index = 0
    for mpls_path in sorted(playlist_dir.glob("*.mpls")):
        try:
            playlist = parse_mpls(mpls_path.read_bytes())
        except MplsParseError:
            continue
        if not playlist.clip_ids:
            continue
        if index == title_index:
            unique_clips = list(dict.fromkeys(playlist.clip_ids))
            segments = [stream_dir / f"{clip_id}.m2ts" for clip_id in unique_clips]
            missing = [s for s in segments if not s.is_file()]
            present = [s for s in segments if s.is_file()]
            if not present:
                raise PlaybackSourceError(
                    f"Kein referenzierter Clip für Titel {title_index} auf der Disc gefunden."
                )
            warnings = []
            if missing:
                warnings.append(
                    f"{len(missing)} von der Playlist referenzierte(r) Clip(s) fehlen auf "
                    "der Disc und werden übersprungen."
                )
            return PlaybackSource(disc_type=DiscType.BLURAY, segments=present, warnings=warnings)
        index += 1
    raise PlaybackSourceError(f"Titel {title_index} existiert nicht auf dieser Blu-ray.")


def resolve_title(root: Path, disc_type: DiscType, title_index: int) -> PlaybackSource:
    """Bequemer Einstieg, wenn der Disc-Typ (aus DiscContent) bereits bekannt ist."""
    if disc_type == DiscType.BLURAY:
        return resolve_bluray_title(root / "BDMV", title_index)
    if disc_type == DiscType.DVD:
        return resolve_dvd_title(root / "VIDEO_TS", title_index)
    raise PlaybackSourceError(f"Titelwiedergabe wird für Disc-Typ {disc_type.value!r} nicht unterstützt.")
