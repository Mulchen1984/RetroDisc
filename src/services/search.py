"""RetroDisc Search — Integrierte Mediensuche über YouTube & Mediatheken."""

from __future__ import annotations

import asyncio
import structlog
from typing import Optional

from src.core.downloader import Downloader
from src.models.media import SearchResult

log = structlog.get_logger()


class MediaSearch:
    """
    Eine Suchleiste — alle Quellen.

    Durchsucht gleichzeitig YouTube und alle ÖR-Mediatheken,
    kombiniert die Ergebnisse und präsentiert sie einheitlich.

    Beispiel:
        search = MediaSearch()
        results = await search.search("Tatort München")
        # → Ergebnisse aus ARD, ZDF, YouTube gemischt
    """

    # Alle unterstützten Mediathek-Sender
    MEDIATHEK_CHANNELS = [
        "ard", "zdf", "arte", "3sat", "phoenix",
        "br", "ndr", "wdr", "hr", "mdr", "swr", "rbb", "sr", "kika",
    ]

    def __init__(self, downloader: Optional[Downloader] = None):
        self.downloader = downloader or Downloader()

    async def search(
        self,
        query: str,
        sources: Optional[list[str]] = None,
        max_results: int = 20,
        min_duration: Optional[float] = None,
        max_duration: Optional[float] = None,
        quality_filter: Optional[str] = None,
    ) -> list[SearchResult]:
        """
        Durchsucht alle konfigurierten Quellen.

        Args:
            query: Suchbegriff
            sources: Quellen-Filter (z.B. ["youtube", "ard", "zdf"])
                     None = alle Quellen
            max_results: Max Ergebnisse gesamt
            min_duration: Mindestdauer in Sekunden
            max_duration: Maximaldauer in Sekunden
            quality_filter: "HD", "4K", oder None

        Returns:
            Kombinierte, gefilterte Ergebnisliste
        """
        include_youtube = True
        include_mediathek = True
        mediathek_sources = None

        if sources:
            sources_lower = [s.lower() for s in sources]
            include_youtube = "youtube" in sources_lower
            mediathek_channels = [s for s in sources_lower if s in self.MEDIATHEK_CHANNELS]
            include_mediathek = bool(mediathek_channels) or "mediathek" in sources_lower
            if mediathek_channels:
                mediathek_sources = mediathek_channels

        # Parallel suchen
        results = await self.downloader.search_all(
            query=query,
            include_youtube=include_youtube,
            include_mediathek=include_mediathek,
            mediathek_sources=mediathek_sources,
            max_results_per_source=max_results,
        )

        # Filtern
        filtered = results

        if min_duration is not None:
            filtered = [
                r for r in filtered
                if r.duration_seconds is None or r.duration_seconds >= min_duration
            ]

        if max_duration is not None:
            filtered = [
                r for r in filtered
                if r.duration_seconds is None or r.duration_seconds <= max_duration
            ]

        if quality_filter:
            filtered = [
                r for r in filtered
                if r.quality and quality_filter.upper() in r.quality.upper()
            ]

        # Auf max_results begrenzen
        return filtered[:max_results]

    async def search_and_preview(
        self,
        query: str,
        **kwargs,
    ) -> list[dict]:
        """
        Sucht und gibt erweiterte Ergebnisse mit Preview-Info zurück.

        Returns:
            Liste von Dicts mit allen SearchResult-Feldern + Extras
        """
        results = await self.search(query, **kwargs)

        enriched = []
        for r in results:
            entry = {
                "title": r.title,
                "url": r.url,
                "source": r.source,
                "source_display": self._source_display_name(r.source),
                "duration": r.duration_seconds,
                "duration_formatted": self._format_duration(r.duration_seconds),
                "thumbnail": r.thumbnail_url,
                "description": r.description,
                "published": r.published_at,
                "quality": r.quality,
                "channel": r.channel,
                "downloadable": True,
                "burnable": True,
            }
            enriched.append(entry)

        return enriched

    @staticmethod
    def _source_display_name(source: str) -> str:
        """Gibt den Anzeigenamen einer Quelle zurück."""
        names = {
            "youtube": "YouTube",
            "ard": "ARD Mediathek",
            "zdf": "ZDF Mediathek",
            "arte": "ARTE",
            "3sat": "3sat",
            "phoenix": "Phoenix",
            "br": "BR Mediathek",
            "ndr": "NDR Mediathek",
            "wdr": "WDR Mediathek",
            "hr": "HR Mediathek",
            "mdr": "MDR Mediathek",
            "swr": "SWR Mediathek",
            "rbb": "RBB Mediathek",
            "sr": "SR Mediathek",
            "kika": "KiKA",
        }
        return names.get(source.lower(), source.upper())

    @staticmethod
    def _format_duration(seconds: Optional[float]) -> str:
        if seconds is None:
            return ""
        total = int(seconds)
        h, remainder = divmod(total, 3600)
        m, s = divmod(remainder, 60)
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"
