"""RetroDisc Upscaler - AI Video-Upscaling (Real-ESRGAN) & Frame Interpolation (RIFE)."""

from __future__ import annotations

import asyncio
import re
import shutil
import structlog
from pathlib import Path
from typing import Optional

from src.models.media import Job

log = structlog.get_logger()


class UpscalerError(Exception):
    pass


class VideoUpscaler:
    """
    AI-gestütztes Video-Upscaling und Frame Interpolation.

    Backend-Tools:
    - realesrgan-ncnn-vulkan: GPU-beschleunigtes Upscaling (Vulkan API)
    - rife-ncnn-vulkan: Frame Interpolation für flüssigere Videos

    Beide Tools laufen über die ncnn/Vulkan-Implementierung,
    die auf NVIDIA, AMD und Intel GPUs funktioniert.

    Beispiel:
        upscaler = VideoUpscaler()
        await upscaler.upscale("old_video.mp4", "upscaled_4k.mp4", scale=4)
        await upscaler.interpolate("24fps.mp4", "60fps.mp4", target_fps=60)
    """

    UPSCALE_MODELS = [
        "realesrgan-x4plus",        # Allgemein, 4x
        "realesrgan-x4plus-anime",   # Anime-optimiert, 4x
        "realesr-animevideov3",      # Anime-Video, 4x
    ]

    def __init__(
        self,
        realesrgan_path: Optional[str] = None,
        rife_path: Optional[str] = None,
        ffmpeg_path: Optional[str] = None,
    ):
        self.realesrgan = (
            realesrgan_path
            or shutil.which("realesrgan-ncnn-vulkan")
            or "realesrgan-ncnn-vulkan"
        )
        self.rife = (
            rife_path
            or shutil.which("rife-ncnn-vulkan")
            or "rife-ncnn-vulkan"
        )
        self.ffmpeg = ffmpeg_path or shutil.which("ffmpeg") or "ffmpeg"

    async def validate(self) -> dict[str, bool]:
        """Prüft welche AI-Tools verfügbar sind."""
        tools = {}
        for name, path in [
            ("realesrgan", self.realesrgan),
            ("rife", self.rife),
        ]:
            found = shutil.which(path) is not None
            tools[name] = found
            if found:
                log.info(f"{name} gefunden", path=path)
            else:
                log.warning(f"{name} nicht gefunden", path=path)
        return tools

    async def upscale(
        self,
        input_path: Path | str,
        output_path: Path | str,
        scale: int = 4,
        model: str = "realesrgan-x4plus",
        gpu_id: int = 0,
        tile_size: int = 0,
        job: Optional[Job] = None,
    ) -> Path:
        """
        Skaliert ein Video mit Real-ESRGAN hoch.

        Workflow:
        1. Video in Frames extrahieren (FFmpeg)
        2. Frames upscalen (Real-ESRGAN)
        3. Frames zu Video zusammensetzen (FFmpeg)
        4. Original-Audio hinzufügen

        Args:
            input_path: Quell-Video
            output_path: Ziel-Video
            scale: Skalierungsfaktor (2 oder 4)
            model: Real-ESRGAN Modell
            gpu_id: GPU-ID (0 = erste GPU)
            tile_size: Tile-Größe (0 = Auto)
            job: Job für Progress-Updates
        """
        input_path = Path(input_path)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Temp-Verzeichnisse
        temp_dir = output_path.parent / f"_upscale_temp_{output_path.stem}"
        frames_in = temp_dir / "frames_in"
        frames_out = temp_dir / "frames_out"
        frames_in.mkdir(parents=True, exist_ok=True)
        frames_out.mkdir(parents=True, exist_ok=True)

        try:
            # 1. Frames extrahieren
            if job:
                job.update_progress(5, "Frames werden extrahiert...")

            fps = await self._get_fps(input_path)

            proc = await asyncio.create_subprocess_exec(
                self.ffmpeg, "-y", "-i", str(input_path),
                "-qscale:v", "1", "-qmin", "1", "-qmax", "1",
                str(frames_in / "frame_%08d.png"),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()

            frame_count = len(list(frames_in.glob("*.png")))
            log.info("Frames extrahiert", count=frame_count)

            if frame_count == 0:
                raise UpscalerError("Keine Frames extrahiert")

            # 2. Upscaling mit Real-ESRGAN
            if job:
                job.update_progress(20, f"Upscaling {frame_count} Frames ({scale}x)...")

            cmd = [
                self.realesrgan,
                "-i", str(frames_in),
                "-o", str(frames_out),
                "-n", model,
                "-s", str(scale),
                "-g", str(gpu_id),
                "-f", "png",
            ]
            if tile_size > 0:
                cmd.extend(["-t", str(tile_size)])

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Progress aus stderr lesen
            while True:
                line = await proc.stderr.readline()
                if not line:
                    break
                line_str = line.decode("utf-8", errors="replace")

                if job:
                    match = re.search(r"(\d+)/(\d+)", line_str)
                    if match:
                        current = int(match.group(1))
                        total = int(match.group(2))
                        progress = 20 + (current / total) * 60
                        job.update_progress(progress, f"Frame {current}/{total}")

            await proc.wait()

            if proc.returncode != 0:
                raise UpscalerError("Real-ESRGAN Upscaling fehlgeschlagen")

            # 3. Frames zu Video zusammensetzen + Original-Audio
            if job:
                job.update_progress(85, "Video wird zusammengesetzt...")

            temp_video = temp_dir / "upscaled_noaudio.mp4"
            proc = await asyncio.create_subprocess_exec(
                self.ffmpeg, "-y",
                "-framerate", str(fps),
                "-i", str(frames_out / "frame_%08d.png"),
                "-i", str(input_path),
                "-map", "0:v", "-map", "1:a?",
                "-c:v", "libx264", "-preset", "slow", "-crf", "18",
                "-c:a", "copy",
                "-pix_fmt", "yuv420p",
                str(output_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()

            if not output_path.exists():
                raise UpscalerError("Output-Video wurde nicht erstellt")

            if job:
                job.update_progress(98, "Upscaling abgeschlossen!")

            log.info("Video upscaled",
                     input=str(input_path),
                     output=str(output_path),
                     scale=f"{scale}x",
                     frames=frame_count)

            return output_path

        finally:
            # Temp aufräumen
            shutil.rmtree(temp_dir, ignore_errors=True)

    async def interpolate(
        self,
        input_path: Path | str,
        output_path: Path | str,
        target_fps: float = 60.0,
        gpu_id: int = 0,
        job: Optional[Job] = None,
    ) -> Path:
        """
        Erhöht die Framerate eines Videos mit RIFE Frame Interpolation.

        Args:
            input_path: Quell-Video
            output_path: Ziel-Video
            target_fps: Ziel-Framerate (z.B. 60)
            gpu_id: GPU-ID
            job: Job für Progress-Updates
        """
        input_path = Path(input_path)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        temp_dir = output_path.parent / f"_interpolate_temp_{output_path.stem}"
        frames_in = temp_dir / "frames_in"
        frames_out = temp_dir / "frames_out"
        frames_in.mkdir(parents=True, exist_ok=True)
        frames_out.mkdir(parents=True, exist_ok=True)

        try:
            # FPS ermitteln und Multiplikator berechnen
            source_fps = await self._get_fps(input_path)
            if source_fps <= 0:
                source_fps = 24.0

            # RIFE arbeitet mit 2x Multiplikator
            # Für 24->60 brauchen wir ~2.5x, also 2x interpolieren und dann timestep
            multiplier = max(2, round(target_fps / source_fps))

            if job:
                job.update_progress(5, "Frames werden extrahiert...")

            # Frames extrahieren
            proc = await asyncio.create_subprocess_exec(
                self.ffmpeg, "-y", "-i", str(input_path),
                "-qscale:v", "1",
                str(frames_in / "frame_%08d.png"),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()

            if job:
                job.update_progress(20, f"Frame Interpolation ({source_fps}->{target_fps}fps)...")

            # RIFE Interpolation
            cmd = [
                self.rife,
                "-i", str(frames_in),
                "-o", str(frames_out),
                "-m", "rife-v4.6",
                "-g", str(gpu_id),
                "-j", "1:2:2",  # Thread-Konfiguration
            ]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()

            if proc.returncode != 0:
                raise UpscalerError("RIFE Interpolation fehlgeschlagen")

            if job:
                job.update_progress(80, "Video wird zusammengesetzt...")

            # Zusammensetzen mit Ziel-FPS + Original-Audio
            proc = await asyncio.create_subprocess_exec(
                self.ffmpeg, "-y",
                "-framerate", str(target_fps),
                "-i", str(frames_out / "%08d.png"),
                "-i", str(input_path),
                "-map", "0:v", "-map", "1:a?",
                "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                "-c:a", "copy",
                "-pix_fmt", "yuv420p",
                str(output_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()

            if not output_path.exists():
                raise UpscalerError("Interpoliertes Video wurde nicht erstellt")

            if job:
                job.update_progress(98, "Frame Interpolation abgeschlossen!")

            log.info("Video interpoliert",
                     input_fps=source_fps,
                     target_fps=target_fps,
                     output=str(output_path))

            return output_path

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    async def _get_fps(self, video_path: Path) -> float:
        """Ermittelt die Framerate eines Videos."""
        proc = await asyncio.create_subprocess_exec(
            self.ffmpeg.replace("ffmpeg", "ffprobe"),
            "-v", "0", "-select_streams", "v:0",
            "-show_entries", "stream=r_frame_rate",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        fps_str = stdout.decode().strip()

        try:
            if "/" in fps_str:
                num, den = fps_str.split("/")
                return round(int(num) / int(den), 3)
            return float(fps_str)
        except (ValueError, ZeroDivisionError):
            return 24.0
