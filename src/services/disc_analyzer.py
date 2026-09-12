"""DiscAnalyzer - baut ein DiscContent-Modell aus einer eingelegten Disc.

Ermittelt echte logische Disc-Titel, keine Dateien:

- DVD: die Titeltabelle (TT_SRPT) aus ``VIDEO_TS.IFO`` (echte Titel-,
  Titelsatz- und Kapitelanzahl-Zuordnung), siehe ``src/services/dvd_ifo.py``.
  Ein ``VTS_XX_Y.VOB`` ist dabei ausdrücklich kein Titel, sondern höchstens
  ein Teil des Video-Objekt-Satzes, den ein oder mehrere Titel referenzieren.
- Blu-ray: die Playlist-Dateien (``BDMV/PLAYLIST/*.mpls``), siehe
  ``src/services/bluray_mpls.py``. Eine einzelne ``*.m2ts``-Datei ist
  ausdrücklich kein Titel, sondern höchstens ein von einer oder mehreren
  Playlists referenzierter Clip.
- Disc-Ebene (Label/Kapazität/Medientyp): ``DiscTools.get_disc_info``,
  unverändert wiederverwendet.
- Video-/Audio-/Untertitel-Spurlayout: ``MediaProbeService`` (ffprobe -of
  json, bereits produktiv in ``src/services/transcode/probe.py``) auf den
  von Titel/Playlist referenzierten Dateien - siehe "Bekannte
  Einschränkungen" in P0_DISCCONTENT_IMPLEMENTATION.md für das, was ffprobe
  auf Elementarstrom-Ebene NICHT liefern kann (insbesondere DVD-Sprachcodes).
- Main-Movie-Kennzeichnung: die vorhandene, getestete Heuristik aus
  ``src/services/main_movie.py`` (unverändert, keine neue Heuristik),
  angewendet auf die echten Titel/Playlists statt auf einzelne Dateien.

Wo eine zuverlässige Zuordnung nicht möglich ist (z. B. mehrere DVD-Titel
teilen sich denselben Titelsatz, oder eine Playlist referenziert einen
fehlenden Clip), bleiben die betroffenen Felder ``None`` statt geschätzt
oder gleichmäßig verteilt zu werden - siehe P0_DISCCONTENT_IMPLEMENTATION.md.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Optional

from src.core.disc import DiscTools
from src.models.disc_content import (
    DiscAudioTrack,
    DiscChapter,
    DiscContent,
    DiscContentError,
    DiscSubtitleTrack,
    DiscTitle,
    DiscVideoInfo,
)
from src.models.media import DiscType
from src.services.bluray_mpls import MplsParseError, MplsPlaylist, parse_mpls
from src.services.dvd_ifo import DvdTitleEntry, IfoParseError, parse_tt_srpt
from src.services.main_movie import detect_main_movie
from src.services.transcode.probe import MediaProbeService, SourceMediaInfo

import structlog

log = structlog.get_logger()


class DiscAnalyzer:
    def __init__(self, disc_tools: DiscTools, probe: MediaProbeService):
        self.disc = disc_tools
        self.probe = probe

    # ── Dateisystem ──────────────────────────────────────────────────

    @staticmethod
    def _root(device: str) -> Optional[Path]:
        value = device.strip()
        if len(value) == 2 and value[1] == ":":
            value += "/"
        root = Path(value)
        return root if root.is_dir() else None

    # ── Probe-Ergebnis -> Disc-Modell ────────────────────────────────

    @staticmethod
    def _video_info(probed: SourceMediaInfo) -> Optional[DiscVideoInfo]:
        v = probed.primary_video
        if not v:
            return None
        return DiscVideoInfo(codec=v.codec, width=v.width, height=v.height, fps=v.fps)

    @staticmethod
    def _audio_tracks(probed: SourceMediaInfo) -> list[DiscAudioTrack]:
        return [
            DiscAudioTrack(index=a.index, codec=a.codec, language=a.language or None,
                           channels=a.channels, bitrate=None, default=a.default)
            for a in probed.audio
        ]

    @staticmethod
    def _subtitle_tracks(probed: SourceMediaInfo) -> list[DiscSubtitleTrack]:
        return [
            DiscSubtitleTrack(index=s.index, language=s.language or None, format=s.codec,
                              forced=s.forced, default=s.default)
            for s in probed.subtitles
        ]

    # ── DVD: echte Titel aus TT_SRPT (VIDEO_TS.IFO) ───────────────────

    async def _dvd_title_from_entry(self, entry: DvdTitleEntry, video_ts: Path, shared_vts: bool) -> DiscTitle:
        vobs = sorted(video_ts.glob(f"VTS_{entry.vts_number:02d}_[1-9].VOB"))
        duration: Optional[float] = None
        size: Optional[int] = None
        stream_layout = SourceMediaInfo()

        if vobs and not shared_vts:
            # Der Titelsatz gehört eindeutig zu genau einem Titel: Größe
            # und Laufzeit der VOBs können ihm direkt zugerechnet werden.
            size = sum(p.stat().st_size for p in vobs)
            duration = 0.0
            for vob in vobs:
                probed = await self.probe.probe(str(vob))
                duration += probed.duration
                if not (stream_layout.audio or stream_layout.video or stream_layout.subtitles) and (
                        probed.audio or probed.video or probed.subtitles):
                    stream_layout = probed
        # Mehrere Titel teilen sich denselben Titelsatz: ohne Zell-/PGC-
        # Parsing (VTS_PGCITI) ist nicht bekannt, welcher Abschnitt der VOBs
        # zu diesem Titel gehört. Größe/Laufzeit bleiben dann bewusst
        # unbekannt statt geraten (siehe Moduldoku).

        # nr_of_ptts ist die echte Kapitelanzahl aus der IFO-Titeltabelle;
        # ihre Zeitposition ist ohne VTS_PGCITI-Parsing nicht bekannt.
        chapters = [DiscChapter(index=i) for i in range(entry.chapter_count)]

        return DiscTitle(
            index=entry.global_title_nr - 1, name=None, duration_seconds=duration, size_bytes=size,
            chapters=chapters,
            video=self._video_info(stream_layout),
            audio_tracks=self._audio_tracks(stream_layout),
            subtitle_tracks=self._subtitle_tracks(stream_layout),
        )

    async def _dvd_titles(self, video_ts: Path) -> list[DiscTitle]:
        ifo_path = video_ts / "VIDEO_TS.IFO"
        if not ifo_path.is_file():
            raise DiscContentError(
                "VIDEO_TS.IFO nicht gefunden: DVD-Titel können ohne echte "
                "IFO-Struktur nicht zuverlässig ermittelt werden."
            )
        try:
            entries = parse_tt_srpt(ifo_path.read_bytes())
        except IfoParseError as exc:
            raise DiscContentError(f"VIDEO_TS.IFO konnte nicht gelesen werden: {exc}") from exc

        vts_counts = Counter(e.vts_number for e in entries)
        titles = []
        for entry in entries:
            titles.append(await self._dvd_title_from_entry(entry, video_ts, vts_counts[entry.vts_number] > 1))
        return titles

    # ── Blu-ray: echte Titel aus Playlists (BDMV/PLAYLIST/*.mpls) ─────

    async def _bluray_title_from_playlist(self, index: int, playlist: MplsPlaylist, stream_dir: Path) -> DiscTitle:
        # Reihenfolge erhalten, aber jeden Clip nur einmal für Größe/
        # Stream-Layout heranziehen (eine Playlist kann denselben Clip
        # mehrfach referenzieren, z. B. bei einer Schleife).
        unique_clips = list(dict.fromkeys(playlist.clip_ids))
        size: Optional[int] = 0
        stream_layout = SourceMediaInfo()
        for clip_id in unique_clips:
            clip_path = stream_dir / f"{clip_id}.m2ts"
            if not clip_path.is_file():
                size = None  # referenzierter Clip fehlt: Gesamtgröße nicht verlässlich
                continue
            if size is not None:
                size += clip_path.stat().st_size
            if not (stream_layout.audio or stream_layout.video or stream_layout.subtitles):
                probed = await self.probe.probe(str(clip_path))
                if probed.audio or probed.video or probed.subtitles:
                    stream_layout = probed

        # Echte Kapitelmarken (ENTRY_MARKs) aus der Playlist, falls vorhanden.
        # Keine Marken gefunden -> leere Liste, kein erfundenes Platzhalter-Kapitel.
        chapters = []
        marks = playlist.chapter_seconds
        for i, start in enumerate(marks):
            end = marks[i + 1] if i + 1 < len(marks) else playlist.duration_seconds
            chapters.append(DiscChapter(index=i, start_seconds=start, duration_seconds=max(0.0, end - start)))

        return DiscTitle(
            index=index, name=None, duration_seconds=playlist.duration_seconds, size_bytes=size,
            chapters=chapters,
            video=self._video_info(stream_layout),
            audio_tracks=self._audio_tracks(stream_layout),
            subtitle_tracks=self._subtitle_tracks(stream_layout),
        )

    async def _bluray_titles(self, bdmv: Path) -> list[DiscTitle]:
        playlist_dir = bdmv / "PLAYLIST"
        stream_dir = bdmv / "STREAM"
        if not playlist_dir.is_dir():
            log.debug("Keine BDMV/PLAYLIST gefunden - keine Titel ermittelbar", path=str(bdmv))
            return []

        titles = []
        for mpls_path in sorted(playlist_dir.glob("*.mpls")):
            try:
                playlist = parse_mpls(mpls_path.read_bytes())
            except MplsParseError as exc:
                log.debug("Playlist nicht lesbar, wird übersprungen", file=str(mpls_path), error=str(exc))
                continue
            if not playlist.clip_ids:
                continue
            titles.append(await self._bluray_title_from_playlist(len(titles), playlist, stream_dir))
        return titles

    # ── Main-Movie ────────────────────────────────────────────────────

    @staticmethod
    def _apply_main_movie(titles: list[DiscTitle]) -> None:
        if not titles:
            return
        candidates = [
            {"index": t.index, "duration": t.duration_seconds,
             "chapters": len(t.chapters), "size": t.size_bytes}
            for t in titles
        ]
        result = detect_main_movie(candidates)
        if result is None:
            return
        for t in titles:
            if t.index == result.candidate:
                t.is_main_movie = True
                t.main_movie_confidence = result.confidence
                break

    # ── Einstieg ─────────────────────────────────────────────────────

    async def analyze(self, device: str) -> DiscContent:
        info = await self.disc.get_disc_info(device)
        if not info.get("present"):
            raise DiscContentError(
                f"Kein lesbares Medium in Laufwerk {device}: "
                f"{info.get('error') or 'kein Medium erkannt'}."
            )

        root = self._root(device)
        disc_type = DiscType.DVD
        titles: list[DiscTitle] = []

        if root is not None and (root / "BDMV").is_dir():
            disc_type = DiscType.BLURAY
            titles = await self._bluray_titles(root / "BDMV")
        elif root is not None and (root / "VIDEO_TS").is_dir():
            disc_type = DiscType.DVD
            titles = await self._dvd_titles(root / "VIDEO_TS")
        elif root is not None:
            # Lesbares Medium ohne VIDEO_TS/BDMV: Audio-CD oder Datenträger.
            disc_type = DiscType.CD
        elif "blu" in str(info.get("type", "")).lower():
            # Kein Dateisystemzugriff auf das Laufwerk möglich (z. B.
            # Entwicklungsrechner ohne echtes Laufwerk), aber das Werkzeug
            # hat den Medientyp bereits gemeldet.
            disc_type = DiscType.BLURAY

        self._apply_main_movie(titles)

        return DiscContent(
            disc_type=disc_type,
            label=info.get("label") or "",
            device=device,
            capacity_bytes=info.get("capacity_bytes"),
            available_bytes=info.get("capacity_bytes") if info.get("blank") else None,
            titles=titles,
        )
