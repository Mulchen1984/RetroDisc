"""Optical-disc ripping for unprotected DVD/Blu-ray/data media."""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional

import structlog

from src.core.disc import DiscError, DiscTools
from src.core.ffmpeg import FFmpeg
from src.models.media import DiscType, Job

log = structlog.get_logger()


class RipError(Exception):
    pass


class DiscRipper:
    """Rips mounted, unencrypted optical media on Windows.

    Encrypted commercial DVD/Blu-ray media require an external decryption
    backend (for example MakeMKV) and fail with an explicit message.
    """

    FORMATS = {"mp4_h264", "mkv_h265", "mkv_copy", "iso"}

    def __init__(self, ffmpeg: FFmpeg, disc_tools: DiscTools):
        self.ffmpeg = ffmpeg
        self.disc = disc_tools

    @staticmethod
    def _root(device: str) -> Path:
        value = device.strip()
        if len(value) == 2 and value[1] == ":":
            value += "/"
        root = Path(value)
        if not root.exists() or not root.is_dir():
            raise RipError(f"Disc-Laufwerk ist nicht verfügbar: {device}")
        return root

    @staticmethod
    def _dvd_title_files(root: Path) -> list[Path]:
        video_ts = root / "VIDEO_TS"
        if not video_ts.is_dir():
            return []
        groups: dict[str, list[Path]] = {}
        for path in video_ts.glob("VTS_*_[1-9].VOB"):
            parts = path.stem.split("_")
            if len(parts) >= 3:
                groups.setdefault(parts[1], []).append(path)
        if not groups:
            return []
        # Main title = title set with the largest total VOB payload.
        best = max(groups.values(), key=lambda files: sum(p.stat().st_size for p in files))
        return sorted(best)

    @staticmethod
    def _bluray_streams(root: Path) -> list[Path]:
        stream_dir = root / "BDMV" / "STREAM"
        if not stream_dir.is_dir():
            return []
        streams = list(stream_dir.glob("*.m2ts"))
        return [max(streams, key=lambda p: p.stat().st_size)] if streams else []

    async def rip(
        self,
        device: str,
        output_path: Path | str,
        output_format: str = "mkv_h265",
        job: Optional[Job] = None,
    ) -> Path:
        output_format = output_format.lower().strip()
        if output_format not in self.FORMATS:
            raise RipError(f"Nicht unterstütztes Rip-Format: {output_format}")
        root = self._root(device)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if job:
            job.update_progress(5, "Disc wird gelesen...")

        if output_format == "iso":
            if (root / "VIDEO_TS").is_dir():
                disc_type = DiscType.DVD
            elif (root / "BDMV").is_dir():
                disc_type = DiscType.BLURAY
            else:
                disc_type = DiscType.CD
            return await self.disc.create_iso(
                root, output_path, volume_label="RETRODISC_RIP",
                disc_type=disc_type, job=job,
            )

        media_files = self._dvd_title_files(root)
        if not media_files:
            media_files = self._bluray_streams(root)
        if not media_files:
            raise RipError(
                "Keine lesbare DVD-/Blu-ray-Videostruktur gefunden. "
                "Audio-CDs und kopiergeschützte Medien benötigen ein externes Rip-Backend."
            )

        temp_dir = Path(tempfile.mkdtemp(prefix="retrodisc_rip_", dir=output_path.parent))
        try:
            source = media_files[0]
            if len(media_files) > 1:
                source = await self.ffmpeg.merge(media_files, temp_dir / "main-title.mkv", job=job)
            if job:
                job.update_progress(25, "Hauptfilm wird verarbeitet...")

            if output_format == "mkv_copy":
                if source.suffix.lower() == ".mkv":
                    # ``os.replace`` statt ``shutil.move``: der Aufrufer hat den
                    # Zielnamen bereits als leere Datei reserviert, und
                    # ``shutil.move`` wuerde darauf unter Windows in den
                    # langsamen Kopierzweig fallen. Quelle und Ziel liegen im
                    # selben Verzeichnisbaum, das Umbenennen bleibt atomar.
                    os.replace(source, output_path)
                    return output_path
                return await self.ffmpeg.convert(
                    source, output_path, video_codec="copy", audio_codec="copy",
                    overwrite=True, job=job,
                )
            if output_format == "mp4_h264":
                return await self.ffmpeg.convert(
                    source, output_path, video_codec="libx264", audio_codec="aac",
                    audio_bitrate="192k", extra_args=["-crf", "20", "-movflags", "+faststart"],
                    overwrite=True, job=job,
                )
            return await self.ffmpeg.convert(
                source, output_path, video_codec="libx265", audio_codec="aac",
                audio_bitrate="192k", extra_args=["-crf", "22"],
                overwrite=True, job=job,
            )
        except (DiscError, OSError) as exc:
            raise RipError(
                f"Disc konnte nicht gelesen werden: {exc}. "
                "Bei kopiergeschützten Medien ist ein externes MakeMKV-Backend erforderlich."
            ) from exc
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
