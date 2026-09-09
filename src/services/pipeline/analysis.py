"""MediaAnalysisOrchestrator: coordinate existing services into one result.

Reuses SourceDetection, fingerprint, MediaProbe, main_movie, MetadataService,
LibraryService and HardwareAcceleration. No analysis logic is reimplemented here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import structlog

from src.services import fingerprint as fingerprint_service
from src.services.main_movie import detect_main_movie
from src.services.pipeline.source import SourceDetectionService, SourceMedia, SourceKind, VIDEO_EXTS
from src.services.transcode.probe import MediaProbeService, SourceMediaInfo

log = structlog.get_logger()

_MAX_TITLE_FILES = 30


@dataclass
class MediaAnalysisResult:
    source: SourceMedia
    media_info: Optional[SourceMediaInfo] = None
    fingerprint: str = ""
    disc_kind: str = ""                 # dvd | bluray | image | file | unknown
    main_movie: Optional[dict] = None
    metadata: Optional[dict] = None
    library_entry: Optional[dict] = None
    hardware: Optional[dict] = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"source": self.source.to_dict(), "fingerprint": self.fingerprint,
                "disc_kind": self.disc_kind, "main_movie": self.main_movie,
                "metadata": self.metadata, "library_entry": self.library_entry,
                "hardware": self.hardware, "warnings": list(self.warnings),
                "errors": list(self.errors), "recommended_actions": list(self.recommended_actions),
                "media_info": {"duration": self.media_info.duration,
                               "video": len(self.media_info.video)} if self.media_info else None}


_DISC_KIND = {SourceKind.DVD_FOLDER: "dvd", SourceKind.BLURAY_FOLDER: "bluray",
              SourceKind.ISO: "image", SourceKind.FILE: "file", SourceKind.OPTICAL_DISC: "disc"}


class MediaAnalysisOrchestrator:
    def __init__(self, *, probe: MediaProbeService, detector: Optional[SourceDetectionService] = None,
                 metadata=None, library=None, hardware=None, capability_cache=None):
        self.probe = probe
        self.detector = detector or SourceDetectionService()
        self.metadata = metadata
        self.library = library
        self.hardware = hardware
        self.capability_cache = capability_cache

    def _fingerprint(self, source: SourceMedia) -> str:
        if source.kind in (SourceKind.DVD_FOLDER, SourceKind.BLURAY_FOLDER) and source.path:
            return fingerprint_service.fingerprint_path(source.path, label=source.label)
        if source.path:                    # Datei/ISO: Name+Größe als stabile Struktur
            return fingerprint_service.fingerprint(
                {"label": source.label, "files": [{"path": Path(source.path).name, "size": source.size}]})
        return ""

    def _media_files(self, folder: str) -> list[Path]:
        files = [p for p in Path(folder).rglob("*")
                 if p.is_file() and p.suffix.lower() in VIDEO_EXTS]
        files.sort(key=lambda p: p.stat().st_size if p.exists() else 0, reverse=True)
        return files[:_MAX_TITLE_FILES]

    async def analyze(self, target: str, *, allow_network: bool = False,
                      want_hardware: bool = False) -> MediaAnalysisResult:
        source = self.detector.detect(target)
        result = MediaAnalysisResult(source=source)
        result.warnings.extend(source.warnings)
        result.disc_kind = _DISC_KIND.get(source.kind, "unknown")
        if not source.available:
            result.errors.append("Quelle nicht verfügbar.")
            return result

        source.fingerprint = self._fingerprint(source)
        result.fingerprint = source.fingerprint

        # Probe + Titel für Hauptfilm-Heuristik.
        titles: list[dict] = []
        try:
            if source.kind == SourceKind.FILE:
                info = await self.probe.probe(source.path)
                result.media_info = info
                titles = [{"index": 0, "duration": info.duration, "size": source.size,
                           "chapters": 0}]
            elif source.kind in (SourceKind.DVD_FOLDER, SourceKind.BLURAY_FOLDER):
                for i, media_file in enumerate(self._media_files(source.path)):
                    info = await self.probe.probe(str(media_file))
                    if result.media_info is None or (info.primary_video and
                            (result.media_info.primary_video is None or
                             (info.primary_video.width or 0) >= (result.media_info.primary_video.width or 0))):
                        result.media_info = info
                    titles.append({"index": i, "duration": info.duration,
                                   "size": media_file.stat().st_size if media_file.exists() else 0,
                                   "chapters": 0})
                if not titles:
                    result.warnings.append("Keine Mediendateien im Disc-Ordner gefunden.")
            elif source.kind == SourceKind.ISO:
                result.warnings.append("ISO-Inhalt ohne Mounting nicht analysierbar (nur Erkennung).")
            elif source.kind == SourceKind.OPTICAL_DISC:
                result.warnings.append("Optisches Laufwerk: Analyse erfordert Laufwerkszugriff.")
        except Exception as exc:            # Probe-Fehler nie fatal für die Analyse
            result.warnings.append(f"Probe fehlgeschlagen: {exc}")
            log.warning("analysis: probe failed", target=target, error=str(exc))

        movie = detect_main_movie(titles) if titles else None
        result.main_movie = movie.to_dict() if movie else None

        if self.metadata is not None and source.fingerprint:
            try:
                from src.services.metadata import MetadataQuery
                v = result.media_info.primary_video if result.media_info else None
                query = MetadataQuery(fingerprint=source.fingerprint, title=source.label,
                                      disc_label=source.label,
                                      runtime=int(movie.duration) if movie else None)
                meta = await self.metadata.lookup(query, allow_network=allow_network)
                result.metadata = meta.to_dict() if meta else None
            except Exception as exc:
                result.warnings.append(f"Metadaten-Abfrage fehlgeschlagen: {exc}")

        if self.library is not None and source.fingerprint:
            entry = self.library.get(source.fingerprint)
            if entry is not None:
                import dataclasses
                result.library_entry = (entry.to_dict() if hasattr(entry, "to_dict")
                                        else dataclasses.asdict(entry) if dataclasses.is_dataclass(entry)
                                        else dict(entry))
                result.recommended_actions.append("already_in_library")

        if want_hardware and self.hardware is not None:
            try:
                caps = await self.hardware.detect(cache=self.capability_cache)
                result.hardware = {name: cap.status.value for name, cap in caps.items()}
            except Exception as exc:
                result.warnings.append(f"Hardware-Erkennung fehlgeschlagen: {exc}")

        if source.media_kind == "video":
            result.recommended_actions.append("transcode")
        elif source.media_kind == "disc" and source.kind != SourceKind.OPTICAL_DISC:
            result.recommended_actions.append("archive_or_transcode")
        elif source.kind == SourceKind.ISO:
            result.recommended_actions.append("iso_inspect_only")
        return result
