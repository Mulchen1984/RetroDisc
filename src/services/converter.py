"""RetroDisc Converter — Konvertierungs-Service mit Presets & Batch-Support."""

from __future__ import annotations

import asyncio
import structlog
from pathlib import Path
from typing import Optional

from src.core.ffmpeg import FFmpeg
from src.config.presets import get_preset, ConversionPreset
from src.models.media import Job, JobType, MediaFile

log = structlog.get_logger()


class Converter:
    """
    High-Level Konvertierungs-Service.

    Kombiniert FFmpeg mit Presets, Batch-Verarbeitung und
    intelligenter Format-Erkennung.

    Beispiel:
        converter = Converter()
        await converter.convert_file("video.mkv", preset="iphone")
        await converter.batch_convert(folder, preset="mp3_320k")
        await converter.to_dvd("video.mp4", "dvd_output/")
    """

    # Unterstützte Eingabe-Formate
    VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm",
                        ".mpg", ".mpeg", ".vob", ".ts", ".m4v", ".3gp"}
    AUDIO_EXTENSIONS = {".mp3", ".flac", ".wav", ".aac", ".ogg", ".m4a", ".wma",
                        ".ac3", ".dts", ".opus"}
    ALL_EXTENSIONS = VIDEO_EXTENSIONS | AUDIO_EXTENSIONS

    def __init__(self, ffmpeg: Optional[FFmpeg] = None, output_dir: Optional[Path] = None):
        self.ffmpeg = ffmpeg or FFmpeg()
        self.output_dir = output_dir

    async def convert_file(
        self,
        input_path: Path | str,
        preset: str | ConversionPreset = "mp4_h264_1080p",
        output_path: Optional[Path | str] = None,
        hwaccel: Optional[str] = None,
        job: Optional[Job] = None,
    ) -> Path:
        """
        Konvertiert eine einzelne Datei mit einem Preset.

        Args:
            input_path: Quell-Datei
            preset: Preset-Name oder ConversionPreset-Objekt
            output_path: Ziel-Pfad (optional, wird aus Preset generiert)
            hwaccel: Hardware-Beschleunigung
            job: Job für Progress-Updates
        """
        input_path = Path(input_path)
        p = get_preset(preset) if isinstance(preset, str) else preset

        if output_path is None:
            out_dir = self.output_dir or input_path.parent
            output_path = out_dir / f"{input_path.stem}_{p.name}.{p.container}"
        output_path = Path(output_path)

        log.info("Konvertierung",
                 input=input_path.name,
                 preset=p.display_name,
                 output=output_path.name)

        return await self.ffmpeg.convert(
            input_path=input_path,
            output_path=output_path,
            video_codec=p.video_codec,
            audio_codec=p.audio_codec,
            video_bitrate=p.video_bitrate,
            audio_bitrate=p.audio_bitrate,
            resolution=p.resolution,
            fps=p.fps,
            sample_rate=p.sample_rate,
            extra_args=p.extra_args,
            job=job,
            hwaccel=hwaccel,
        )

    async def batch_convert(
        self,
        input_dir: Path | str,
        preset: str = "mp4_h264_1080p",
        output_dir: Optional[Path | str] = None,
        recursive: bool = False,
        extensions: Optional[set[str]] = None,
        on_file_complete: Optional[callable] = None,
    ) -> list[Path]:
        """
        Konvertiert alle Mediendateien in einem Ordner.

        Args:
            input_dir: Quell-Ordner
            preset: Preset-Name
            output_dir: Ziel-Ordner
            recursive: Unterordner einbeziehen
            extensions: Dateiendungen filtern (None = alle Medien)
            on_file_complete: Callback pro Datei

        Returns:
            Liste der Output-Pfade
        """
        input_dir = Path(input_dir)
        output_dir = Path(output_dir) if output_dir else input_dir / "converted"
        output_dir.mkdir(parents=True, exist_ok=True)

        allowed = extensions or self.ALL_EXTENSIONS
        glob_pattern = "**/*" if recursive else "*"

        files = [
            f for f in input_dir.glob(glob_pattern)
            if f.is_file() and f.suffix.lower() in allowed
        ]

        log.info("Batch-Konvertierung", files=len(files), preset=preset)

        results = []
        for i, file in enumerate(files):
            try:
                output = await self.convert_file(
                    input_path=file,
                    preset=preset,
                    output_path=output_dir / f"{file.stem}.{get_preset(preset).container}",
                )
                results.append(output)

                if on_file_complete:
                    on_file_complete(file, output, i + 1, len(files))

            except Exception as e:
                log.error("Batch-Fehler", file=file.name, error=str(e))

        log.info("Batch abgeschlossen", converted=len(results), total=len(files))
        return results

    async def to_dvd(
        self,
        input_path: Path | str,
        output_dir: Path | str,
        standard: str = "PAL",
        aspect: str = "16:9",
        job: Optional[Job] = None,
    ) -> Path:
        """Konvertiert ein Video in DVD-kompatibles MPEG und erstellt DVD-Struktur."""
        input_path = Path(input_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Schritt 1: Zu DVD-MPEG konvertieren
        mpeg_path = output_dir / f"{input_path.stem}.mpg"

        if job:
            job.update_progress(5, "Konvertiere zu DVD-Format...")

        await self.ffmpeg.to_dvd_mpeg(
            input_path=input_path,
            output_path=mpeg_path,
            standard=standard,
            aspect=aspect,
            job=job,
        )

        return mpeg_path

    async def youtube_to_audio_cd(
        self,
        urls: list[str],
        output_dir: Path | str,
        job: Optional[Job] = None,
    ) -> list[Path]:
        """
        Kompletter Workflow: YouTube-URLs → Audio-CD-taugliche WAV-Dateien.

        Args:
            urls: Liste von YouTube-URLs
            output_dir: Ziel-Ordner für die WAV-Dateien
        """
        from src.core.downloader import Downloader

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        dl = Downloader(output_dir=output_dir / "_downloads")
        wav_files = []

        for i, url in enumerate(urls):
            if job:
                progress = (i / len(urls)) * 80
                job.update_progress(progress, f"Track {i+1}/{len(urls)}")

            # Download als Audio
            mp3_path = await dl.download(
                url=url,
                extract_audio=True,
                audio_format="wav",
                audio_quality="0",  # Beste Qualität
            )

            # Zu CD-Audio konvertieren (16bit, 44.1kHz, Stereo)
            wav_path = output_dir / f"track_{i+1:02d}.wav"
            await self.ffmpeg.convert(
                input_path=mp3_path,
                output_path=wav_path,
                audio_codec="pcm_s16le",
                sample_rate=44100,
                extra_args=["-ac", "2", "-vn"],
            )
            wav_files.append(wav_path)

        if job:
            job.update_progress(95, f"{len(wav_files)} Tracks bereit zum Brennen")

        return wav_files

    async def analyze(self, input_path: Path | str) -> MediaFile:
        """Analysiert eine Mediendatei und gibt alle Informationen zurück."""
        return await self.ffmpeg.probe(input_path)
