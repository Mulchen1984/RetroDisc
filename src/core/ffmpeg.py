"""RetroDisc FFmpeg-Wrapper — Kern-Engine für alle Konvertierungen."""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import tempfile
import structlog
from pathlib import Path
from typing import Optional

from src.models.media import (
    AudioStream, MediaFile, MediaType, SubtitleStream, VideoStream, Job
)
from src.utils.subprocesses import (
    communicate_with_job,
    commit_staged_output,
    create_hidden_subprocess,
    decode_console_output,
    iter_stream_records,
    staging_output_path,
    terminate_process,
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

    async def available_video_encoders(self) -> set[str]:
        """Ask the configured FFmpeg; cache successful results per executable path."""
        cached = getattr(self, "_encoder_cache", None)
        if cached and cached[0] == self.ffmpeg_path:
            return cached[1]
        try:
            proc = await create_hidden_subprocess(
                self.ffmpeg_path, "-hide_banner", "-encoders",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(
                communicate_with_job(proc, max_output_bytes=65536), timeout=5,
            )
            if proc.returncode != 0:
                return set()
        except (OSError, asyncio.TimeoutError):
            return set()
        encoders = {parts[1] for line in stdout.decode("utf-8", errors="replace").splitlines()
                    if len(parts := line.split()) >= 2 and parts[0].startswith("V")}
        self._encoder_cache = (self.ffmpeg_path, encoders)
        return encoders

    async def validate(self) -> dict[str, str]:
        """Prüft ob FFmpeg und FFprobe verfügbar sind und gibt Versionen zurück."""
        versions = {}

        for name, path in [("ffmpeg", self.ffmpeg_path), ("ffprobe", self.ffprobe_path)]:
            try:
                proc = await create_hidden_subprocess(
                    path, "-version",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await proc.communicate()
                first_line = stdout.decode("utf-8", errors="replace").split("\n")[0]
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

        proc = await create_hidden_subprocess(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise FFmpegError(f"FFprobe Fehler: {stderr.decode('utf-8', errors='replace')}")

        data = json.loads(stdout.decode("utf-8", errors="replace"))
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
        if media_file.has_video and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
            media_file.media_type = MediaType.IMAGE
        elif media_file.has_video:
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
        overwrite: bool = False,
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
        if not input_path.exists() or not input_path.is_file():
            raise FFmpegError(f"Datei nicht gefunden: {input_path}")
        if input_path.resolve() == output_path.resolve():
            raise FFmpegError("Quell- und Zieldatei dürfen nicht identisch sein.")
        if output_path.exists() and not overwrite:
            raise FFmpegError(f"Zieldatei existiert bereits: {output_path}")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        staging_path = staging_output_path(output_path)
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
        cmd.append(str(staging_path))

        log.info("FFmpeg Konvertierung gestartet", input=str(input_path), output=str(output_path))

        # Dauer für Progress-Berechnung holen
        duration = 0.0
        if job:
            try:
                info = await self.probe(input_path)
                duration = info.duration_seconds
            except Exception:
                pass

        # Progress aus CR- oder LF-getrenntem stderr parsen. Nur das Ende wird
        # für eine mögliche Fehlermeldung behalten.
        stderr_tail = bytearray()
        proc = None
        try:
            proc = await create_hidden_subprocess(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            if job:
                job._process = proc

            async for record in iter_stream_records(proc.stderr):
                stderr_tail.extend(record)
                stderr_tail.extend(b"\n")
                if len(stderr_tail) > 8192:
                    del stderr_tail[:-8192]
                line_str = decode_console_output(record)

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
                error = decode_console_output(bytes(stderr_tail))[-500:]
                raise FFmpegError(f"FFmpeg Fehler (Code {proc.returncode}): {error}")

            if not staging_path.is_file() or staging_path.stat().st_size == 0:
                raise FFmpegError(f"Output-Datei wurde nicht erstellt: {output_path}")
            commit_staged_output(staging_path, output_path)
        except BaseException:
            if proc is not None:
                await terminate_process(proc)
            staging_path.unlink(missing_ok=True)
            raise
        finally:
            if proc is not None and job and getattr(job, "_process", None) is proc:
                job._process = None

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
        normalized_standard = standard.strip().lower()
        if normalized_standard not in {"pal", "ntsc", "film"}:
            raise ValueError("DVD-Standard muss PAL, NTSC oder FILM sein.")
        target = f"{normalized_standard}-dvd"
        extra = ["-aspect", aspect]
        return await self.convert(
            input_path=input_path,
            output_path=output_path,
            extra_args=["-target", target] + extra,
            job=job,
        )

    # Feste BD-ROM-AV-PIDs (Blu-ray-Spezifikation, Teil 3 Abschnitt "Audio
    # Visual Application Format"): primärer Videostream immer 0x1011,
    # primärer Audiostream immer 0x1100. RetroDiscs eigener BDMV-Authoring-
    # Pfad (``src/services/bluray_authoring.py``) und jeder spec-konforme
    # BD-Player setzen exakt diese PIDs voraus.
    BLURAY_VIDEO_PID = 0x1011
    BLURAY_AUDIO_PID = 0x1100

    async def to_bluray_stream(
        self,
        input_path: Path | str,
        output_path: Path | str,
        video_bitrate_bps: Optional[int] = None,
        job: Optional[Job] = None,
    ) -> Path:
        """Encodes a video into a BD-ROM-compliant BDAV transport stream.

        Real Blu-ray ``STREAM/*.m2ts`` clips are not plain 188-byte MPEG-TS:
        each packet has a 4-byte timestamp prefix (192 bytes total, "M2TS"/
        BDAV format), and the primary video/audio elementary streams sit on
        fixed PIDs (0x1011/0x1100) so a player's PMT lookup and RetroDisc's
        own CLIPINF (``bluray_authoring.write_clip_info``) agree on where to
        find them. ``-mpegts_m2ts_mode`` is FFmpeg's own flag for exactly
        this BDAV packet shape; verified locally against real output
        (sync byte 0x47 at offset 4 of every 192-byte packet, PIDs 0x1011/
        0x1100 confirmed via ffprobe) before this was wired in.

        H.264 High Profile/Level 4.1 + AC-3 is the same combination assumed
        mandatory-support by every BD-Video player; it is not the only
        legal BD codec pairing, but it is the safe, universally playable
        one and the one RetroDisc's DVD path already mirrors in spirit
        (``to_dvd_mpeg`` also targets one fixed, always-compatible profile
        rather than exposing every legal codec combination).
        """
        bitrate_bps = max(1_000_000, int(video_bitrate_bps or 15_000_000))
        video_bitrate = str(bitrate_bps)
        extra = [
            "-map", "0:v:0", "-map", "0:a:0?",
            "-profile:v", "high", "-level:v", "4.1", "-pix_fmt", "yuv420p",
            "-maxrate", video_bitrate, "-bufsize", str(bitrate_bps * 2),
            "-g", "24", "-keyint_min", "24", "-sc_threshold", "0",
            "-mpegts_m2ts_mode", "1", "-muxrate", "48000000", "-pcr_period", "20",
            "-streamid", f"0:0x{self.BLURAY_VIDEO_PID:x}",
            "-streamid", f"1:0x{self.BLURAY_AUDIO_PID:x}",
            "-f", "mpegts",
        ]
        return await self.convert(
            input_path=input_path,
            output_path=output_path,
            video_codec="libx264",
            audio_codec="ac3",
            audio_bitrate="448k",
            video_bitrate=video_bitrate,
            extra_args=extra,
            overwrite=True,
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
        staging_path = staging_output_path(output_path)

        # Eindeutige, ausschliesslich dieser Operation gehoerende Concat-Liste.
        # Ein deterministischer Name (_concat_<stem>.txt) kollidiert bei
        # Paralleljobs und wuerde im finally eine fremde Datei ueberschreiben
        # und loeschen. mkstemp legt die Datei exklusiv an; der Deskriptor wird
        # vor dem FFmpeg-Start sicher geschlossen.
        concat_fd, concat_name = tempfile.mkstemp(
            prefix=f".{output_path.stem}.retrodisc-concat-",
            suffix=".txt",
            dir=output_path.parent,
        )
        concat_file = Path(concat_name)

        try:
            with os.fdopen(concat_fd, "w", encoding="utf-8") as handle:
                for p in input_paths:
                    # Innerhalb von file '...' wird ein echtes ' als '\'' notiert.
                    safe = str(Path(p).resolve()).replace("'", "'\\''")
                    handle.write(f"file '{safe}'\n")

            cmd = [
                self.ffmpeg_path, "-y",
                "-f", "concat", "-safe", "0",
                "-i", str(concat_file),
                "-c", "copy",
                str(staging_path),
            ]

            proc = await create_hidden_subprocess(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            if job:
                job.update_progress(20, "Dateien werden zusammengefügt...")
            _, stderr = await communicate_with_job(proc, job)
            if job:
                job.update_progress(95, "Zusammenfügen abgeschlossen")

            if proc.returncode != 0:
                raise FFmpegError(
                    f"Merge Fehler: {decode_console_output(stderr)[-500:]}"
                )
            if not staging_path.is_file() or staging_path.stat().st_size == 0:
                raise FFmpegError(f"Merge-Ausgabe wurde nicht erstellt: {output_path}")
            commit_staged_output(staging_path, output_path)

            return output_path
        finally:
            # Beide Pfade sind eindeutig und gehoeren nur dieser Operation.
            staging_path.unlink(missing_ok=True)
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
        staging_path = staging_output_path(output_path)

        cmd = [
            self.ffmpeg_path, "-y",
            "-ss", str(time_seconds),
            "-i", str(input_path),
            "-vframes", "1",
            "-vf", f"scale={width}:-1",
            str(staging_path),
        ]

        proc = await create_hidden_subprocess(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await communicate_with_job(proc)
            if proc.returncode != 0:
                raise FFmpegError(
                    f"Thumbnail fehlgeschlagen: {decode_console_output(stderr)[-500:]}"
                )
            if not staging_path.is_file() or staging_path.stat().st_size == 0:
                raise FFmpegError(f"Thumbnail konnte nicht erstellt werden: {output_path}")
            commit_staged_output(staging_path, output_path)
        finally:
            staging_path.unlink(missing_ok=True)

        return output_path
