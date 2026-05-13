"""RetroDisc FFmpeg-Wrapper — Kern-Engine für alle Konvertierungen."""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import structlog
from pathlib import Path
from typing import Optional

from src.models.media import (
    AudioStream, MediaFile, MediaType, SubtitleStream, VideoStream, Job
)

log = structlog.get_logger()


class FFmpegError(Exception):
    """Fehler bei FFmpeg-Operationen."""
    pass


class FFmpegNotFoundError(FFmpegError):
    """FFmpeg oder FFprobe nicht gefunden."""
    pass


class FFmpeg:
    """
    Wrapper für FFmpeg und FFprobe.

    Alle Konvertierungen, Analysen und Manipulationen laufen über diese Klasse.
    FFmpeg wird als subprocess aufgerufen — nie direkt importiert.

    Beispiel:
        ffmpeg = FFmpeg()
        info = await ffmpeg.probe("/path/to/video.mp4")
        await ffmpeg.convert(
            input_path="/path/to/video.mp4",
            output_path="/path/to/output.mkv",
            video_codec="libx265",
            audio_codec="aac",
        )
    """

    def __init__(
        self,
        ffmpeg_path: Optional[str] = None,
        ffprobe_path: Optional[str] = None,
    ):
        self.ffmpeg_path = ffmpeg_path or shutil.which("ffmpeg") or "ffmpeg"
        self.ffprobe_path = ffprobe_path or shutil.which("ffprobe") or "ffprobe"
        self._validated = False

    async def validate(self) -> dict[str, str]:
        """Prüft ob FFmpeg und FFprobe verfügbar sind und gibt Versionen zurück."""
        versions = {}

        for name, path in [("ffmpeg", self.ffmpeg_path), ("ffprobe", self.ffprobe_path)]:
            try:
                proc = await asyncio.create_subprocess_exec(
                    path, "-version",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await proc.communicate()
                first_line = stdout.decode().split("\n")[0]
                match = re.search(r"version\s+(\S+)", first_line)
                versions[name] = match.group(1) if match else "unknown"
                log.info(f"{name} gefunden", version=versions[name], path=path)
            except FileNotFoundError:
                raise FFmpegNotFoundError(
                    f"{name} nicht gefunden unter '{path}'. "
                    f"Bitte installieren: https://ffmpeg.org/download.html"
                )

        self._validated = True
        return versions

    async def probe(self, input_path: Path | str) -> MediaFile:
        """
        Analysiert eine Mediendatei und gibt ein MediaFile-Objekt zurück.

        Args:
            input_path: Pfad zur Datei

        Returns:
            MediaFile mit allen Metadaten
        """
        input_path = Path(input_path)
        if not input_path.exists():
            raise FFmpegError(f"Datei nicht gefunden: {input_path}")

        cmd = [
            self.ffprobe_path,
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(input_path),
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise FFmpegError(f"FFprobe Fehler: {stderr.decode()}")

        data = json.loads(stdout.decode())
        return self._parse_probe_data(input_path, data)

    def _parse_probe_data(self, path: Path, data: dict) -> MediaFile:
        """Parst FFprobe JSON-Output in ein MediaFile."""
        fmt = data.get("format", {})
        streams = data.get("streams", [])

        media_file = MediaFile(
            path=path,
            container=fmt.get("format_name", ""),
            duration_seconds=float(fmt.get("duration", 0)),
            file_size_bytes=int(fmt.get("size", 0)),
            title=fmt.get("tags", {}).get("title"),
            artist=fmt.get("tags", {}).get("artist"),
            album=fmt.get("tags", {}).get("album"),
        )

        for stream in streams:
            codec_type = stream.get("codec_type")

            if codec_type == "video":
                # Bilder überspringen (z.B. Album-Cover)
                if stream.get("disposition", {}).get("attached_pic", 0):
                    continue
                media_file.video_streams.append(VideoStream(
                    index=stream.get("index", 0),
                    codec=stream.get("codec_name", "unknown"),
                    width=stream.get("width", 0),
                    height=stream.get("height", 0),
                    fps=self._parse_fps(stream.get("r_frame_rate", "0/1")),
                    bitrate=int(stream["bit_rate"]) if "bit_rate" in stream else None,
                    hdr="bt2020" in stream.get("color_space", ""),
                ))

            elif codec_type == "audio":
                media_file.audio_streams.append(AudioStream(
                    index=stream.get("index", 0),
                    codec=stream.get("codec_name", "unknown"),
                    channels=stream.get("channels", 2),
                    sample_rate=int(stream.get("sample_rate", 44100)),
                    bitrate=int(stream["bit_rate"]) if "bit_rate" in stream else None,
                    language=stream.get("tags", {}).get("language"),
                ))

            elif codec_type == "subtitle":
                media_file.subtitle_streams.append(SubtitleStream(
                    index=stream.get("index", 0),
                    codec=stream.get("codec_name", "unknown"),
                    language=stream.get("tags", {}).get("language"),
                ))

        # MediaType bestimmen
        if media_file.has_video:
            media_file.media_type = MediaType.VIDEO
        elif media_file.has_audio:
            media_file.media_type = MediaType.AUDIO
        else:
            media_file.media_type = MediaType.UNKNOWN

        return media_file

    @staticmethod
    def _parse_fps(fps_str: str) -> float:
        """Parst FPS-String wie '30000/1001' oder '25/1'."""
        try:
            if "/" in fps_str:
                num, den = fps_str.split("/")
                return round(int(num) / int(den), 3) if int(den) != 0 else 0.0
            return float(fps_str)
        except (ValueError, ZeroDivisionError):
            return 0.0

    async def convert(
        self,
        input_path: Path | str,
        output_path: Path | str,
        video_codec: Optional[str] = None,
        audio_codec: Optional[str] = None,
        video_bitrate: Optional[str] = None,
        audio_bitrate: Optional[str] = None,
        resolution: Optional[str] = None,
        fps: Optional[float] = None,
        sample_rate: Optional[int] = None,
        extra_args: Optional[list[str]] = None,
        job: Optional[Job] = None,
        hwaccel: Optional[str] = None,
    ) -> Path:
        """
        Konvertiert eine Mediendatei.

        Args:
            input_path: Quell-Datei
            output_path: Ziel-Datei
            video_codec: z.B. "libx264", "libx265", "copy"
            audio_codec: z.B. "aac", "libmp3lame", "copy"
            video_bitrate: z.B. "5M", "10M"
            audio_bitrate: z.B. "192k", "320k"
            resolution: z.B. "1920:1080", "1280:720"
            fps: Ziel-Framerate
            sample_rate: Audio Sample Rate
            extra_args: Zusätzliche FFmpeg-Argumente
            job: Job-Objekt für Progress-Updates
            hwaccel: Hardware-Beschleunigung ("cuda", "qsv", "auto")

        Returns:
            Pfad zur Output-Datei
        """
        input_path = Path(input_path)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = [self.ffmpeg_path, "-y"]

        # Hardware-Beschleunigung
        if hwaccel:
            cmd.extend(["-hwaccel", hwaccel])

        # Input
        cmd.extend(["-i", str(input_path)])

        # Video
        if video_codec:
            cmd.extend(["-c:v", video_codec])
        if video_bitrate:
            cmd.extend(["-b:v", video_bitrate])
        if resolution:
            cmd.extend(["-vf", f"scale={resolution}"])
        if fps:
            cmd.extend(["-r", str(fps)])

        # Audio
        if audio_codec:
            cmd.extend(["-c:a", audio_codec])
        if audio_bitrate:
            cmd.extend(["-b:a", audio_bitrate])
        if sample_rate:
            cmd.extend(["-ar", str(sample_rate)])

        # Extras
        if extra_args:
            cmd.extend(extra_args)

        # Output
        cmd.append(str(output_path))

        log.info("FFmpeg Konvertierung gestartet", input=str(input_path), output=str(output_path))

        # Dauer für Progress-Berechnung holen
        duration = 0.0
        if job:
            try:
                info = await self.probe(input_path)
                duration = info.duration_seconds
            except Exception:
                pass

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Progress aus stderr parsen
        stderr_data = b""
        while True:
            line = await proc.stderr.readline()
            if not line:
                break
            stderr_data += line
            line_str = line.decode("utf-8", errors="replace")

            if job and duration > 0:
                time_match = re.search(r"time=(\d+):(\d+):(\d+)\.(\d+)", line_str)
                if time_match:
                    h, m, s, ms = time_match.groups()
                    current = int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 100
                    progress = min((current / duration) * 100, 99.9)
                    speed_match = re.search(r"speed=\s*([\d.]+)x", line_str)
                    speed = speed_match.group(1) if speed_match else "?"
                    job.update_progress(progress, f"{speed}x Geschwindigkeit")

        await proc.wait()

        if proc.returncode != 0:
            error = stderr_data.decode("utf-8", errors="replace")[-500:]
            raise FFmpegError(f"FFmpeg Fehler (Code {proc.returncode}): {error}")

        if not output_path.exists():
            raise FFmpegError(f"Output-Datei wurde nicht erstellt: {output_path}")

        log.info("FFmpeg Konvertierung abgeschlossen", output=str(output_path))
        return output_path

    async def extract_audio(
        self,
        input_path: Path | str,
        output_path: Path | str,
        codec: str = "libmp3lame",
        bitrate: str = "320k",
        job: Optional[Job] = None,
    ) -> Path:
        """Extrahiert Audio aus einer Videodatei."""
        return await self.convert(
            input_path=input_path,
            output_path=output_path,
            video_codec=None,
            audio_codec=codec,
            audio_bitrate=bitrate,
            extra_args=["-vn"],  # Video-Stream entfernen
            job=job,
        )

    async def to_dvd_mpeg(
        self,
        input_path: Path | str,
        output_path: Path | str,
        standard: str = "pal",
        aspect: str = "16:9",
        job: Optional[Job] = None,
    ) -> Path:
        """Konvertiert ein Video in DVD-kompatibles MPEG."""
        target = f"{standard}-dvd"
        extra = ["-aspect", aspect]
        return await self.convert(
            input_path=input_path,
            output_path=output_path,
            extra_args=["-target", target] + extra,
            job=job,
        )

    async def trim(
        self,
        input_path: Path | str,
        output_path: Path | str,
        start_seconds: float,
        end_seconds: float,
        job: Optional[Job] = None,
    ) -> Path:
        """Schneidet ein Video auf den angegebenen Zeitbereich."""
        duration = end_seconds - start_seconds
        return await self.convert(
            input_path=input_path,
            output_path=output_path,
            video_codec="copy",
            audio_codec="copy",
            extra_args=[
                "-ss", str(start_seconds),
                "-t", str(duration),
            ],
            job=job,
        )

    async def merge(
        self,
        input_paths: list[Path | str],
        output_path: Path | str,
        job: Optional[Job] = None,
    ) -> Path:
        """Fügt mehrere Videos zusammen (concat)."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Concat-Datei erstellen
        concat_file = output_path.parent / f"_concat_{output_path.stem}.txt"
        with open(concat_file, "w") as f:
            for p in input_paths:
                f.write(f"file '{Path(p).resolve()}'\n")

        try:
            cmd = [
                self.ffmpeg_path, "-y",
                "-f", "concat", "-safe", "0",
                "-i", str(concat_file),
                "-c", "copy",
                str(output_path),
            ]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()

            if proc.returncode != 0:
                raise FFmpegError(f"Merge Fehler: {stderr.decode()[-500:]}")

            return output_path
        finally:
            concat_file.unlink(missing_ok=True)

    async def generate_thumbnail(
        self,
        input_path: Path | str,
        output_path: Path | str,
        time_seconds: float = 5.0,
        width: int = 320,
    ) -> Path:
        """Erzeugt ein Thumbnail aus einem Video."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            self.ffmpeg_path, "-y",
            "-ss", str(time_seconds),
            "-i", str(input_path),
            "-vframes", "1",
            "-vf", f"scale={width}:-1",
            str(output_path),
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

        if not output_path.exists():
            raise FFmpegError(f"Thumbnail konnte nicht erstellt werden: {output_path}")

        return output_path
