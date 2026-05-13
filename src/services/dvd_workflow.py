"""RetroDisc DVD Workflow — Kompletter High-Level DVD-Erstellungs-Prozess.

Orchestriert den gesamten Ablauf von der Quelldatei bis zur fertigen DVD:
1. Quelle analysieren (FFprobe)
2. Zu DVD-MPEG konvertieren (FFmpeg)
3. DVD-Struktur erstellen (dvdauthor)
4. ISO-Image erstellen (mkisofs)
5. Optional: auf Disc brennen (growisofs)
"""

from __future__ import annotations

import asyncio
import structlog
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from src.core.ffmpeg import FFmpeg
from src.core.disc import DiscTools, DiscError
from src.models.media import DiscType, Job, JobType

log = structlog.get_logger()


@dataclass
class DVDProject:
    """Beschreibt ein DVD-Projekt."""
    title: str = "RetroDisc DVD"
    input_files: list[Path] = field(default_factory=list)
    output_dir: Optional[Path] = None
    standard: str = "PAL"          # "PAL" oder "NTSC"
    aspect: str = "16:9"           # "16:9" oder "4:3"
    burn_to_disc: bool = False
    disc_device: str = "/dev/sr0"
    burn_speed: Optional[int] = None
    verify_after_burn: bool = True
    eject_after_burn: bool = True
    only_iso: bool = False          # Kein Brennen, nur ISO erstellen


class DVDWorkflow:
    """
    Vollständiger DVD-Erstellungs-Workflow.

    Koordiniert alle Schritte von der Quelldatei bis zur fertigen Disc.

    Beispiel:
        wf = DVDWorkflow()
        project = DVDProject(
            title="Mein Konzert",
            input_files=[Path("konzert.mp4")],
            burn_to_disc=True,
        )
        iso_path = await wf.run(project, job=job)
    """

    STEPS = [
        "Quelldateien prüfen",
        "Video in DVD-Format konvertieren",
        "DVD-Struktur erstellen",
        "ISO-Image erzeugen",
        "Auf Disc schreiben",
        "Fertig!",
    ]

    def __init__(
        self,
        ffmpeg: Optional[FFmpeg] = None,
        disc_tools: Optional[DiscTools] = None,
        temp_dir: Optional[Path] = None,
    ):
        self.ffmpeg = ffmpeg or FFmpeg()
        self.disc = disc_tools or DiscTools()
        self.temp_dir = temp_dir or Path.home() / ".retrodisc" / "temp"

    async def run(
        self,
        project: DVDProject,
        job: Optional[Job] = None,
    ) -> Path:
        """
        Führt den kompletten DVD-Workflow durch.

        Returns:
            Pfad zur fertigen ISO-Datei
        """
        if not project.input_files:
            raise ValueError("Keine Quelldateien angegeben")

        # Arbeitsverzeichnis vorbereiten
        work_dir = self.temp_dir / f"dvd_{project.title[:30].replace(' ', '_')}"
        work_dir.mkdir(parents=True, exist_ok=True)
        out_dir = project.output_dir or work_dir.parent

        log.info("DVD-Workflow gestartet",
                 title=project.title,
                 files=len(project.input_files))

        try:
            # ── Schritt 1: Quelldateien prüfen ──────────────────────
            self._step(job, 1, 5, "Quelldateien werden geprüft...")
            for f in project.input_files:
                if not f.exists():
                    raise FileNotFoundError(f"Quelldatei nicht gefunden: {f}")
            log.info("Quelldateien OK", count=len(project.input_files))

            # ── Schritt 2: Zu DVD-MPEG konvertieren ─────────────────
            self._step(job, 2, 20, "Konvertierung zu DVD-Format läuft...")
            mpeg_files = []
            for i, src in enumerate(project.input_files):
                mpeg_out = work_dir / f"title_{i+1:02d}.mpg"

                # Nur konvertieren wenn nötig (VOB/MPG überspringen)
                if src.suffix.lower() in (".mpg", ".mpeg", ".vob"):
                    mpeg_files.append(src)
                    log.info("Datei bereits DVD-kompatibel", file=src.name)
                else:
                    sub_job = None
                    if job:
                        sub_job = Job(job_type=JobType.CONVERT)
                        # Progress anteilig weiterreichen
                        file_start = 20 + (i / len(project.input_files)) * 30
                        file_end = 20 + ((i+1) / len(project.input_files)) * 30
                        sub_job.on_progress = lambda p, t, s=file_start, e=file_end: (
                            job.update_progress(s + (p/100)*(e-s), f"[{i+1}/{len(project.input_files)}] {t}")
                        )

                    await self.ffmpeg.to_dvd_mpeg(
                        input_path=src,
                        output_path=mpeg_out,
                        standard=project.standard,
                        aspect=project.aspect,
                        job=sub_job,
                    )
                    mpeg_files.append(mpeg_out)
                    log.info("MPEG erstellt", file=mpeg_out.name)

            # ── Schritt 3: DVD-Struktur erstellen ───────────────────
            self._step(job, 3, 55, "DVD-Struktur wird erstellt (dvdauthor)...")
            dvd_dir = await self.disc.create_dvd_structure(
                mpeg_files=mpeg_files,
                output_dir=work_dir,
                title=project.title,
                standard=project.standard,
                job=job,
            )

            # ── Schritt 4: ISO erstellen ─────────────────────────────
            self._step(job, 4, 75, "ISO-Image wird erstellt...")
            safe_title = project.title[:32].replace(" ", "_").upper()
            iso_path = out_dir / f"{project.title[:40].replace(' ', '_')}.iso"

            iso_path = await self.disc.create_iso(
                source_dir=dvd_dir,
                output_path=iso_path,
                volume_label=safe_title,
                disc_type=DiscType.DVD,
                job=job,
            )

            # ── Schritt 5: Brennen (optional) ──────────────────────
            if project.burn_to_disc and not project.only_iso:
                self._step(job, 5, 85, f"Wird auf Disc geschrieben ({project.disc_device})...")
                await self.disc.burn_iso(
                    iso_path=iso_path,
                    device=project.disc_device,
                    speed=project.burn_speed,
                    verify=project.verify_after_burn,
                    disc_type=DiscType.DVD,
                    job=job,
                )
                if project.eject_after_burn:
                    await self._eject(project.disc_device)
            else:
                self._step(job, 5, 90, "Kein Brennen (nur ISO)...")

            # ── Schritt 6: Fertig ────────────────────────────────────
            self._step(job, 6, 100, f"DVD '{project.title}' fertig!")
            log.info("DVD-Workflow abgeschlossen",
                     title=project.title,
                     iso=str(iso_path))
            return iso_path

        finally:
            # Temp-Dateien aufräumen (MPEG-Zwischendateien)
            import shutil
            shutil.rmtree(work_dir, ignore_errors=True)

    def _step(self, job: Optional[Job], step: int, progress: float, text: str):
        """Aktualisiert Job-Progress mit Schritt-Info."""
        log.info(f"DVD-Schritt {step}/{len(self.STEPS)}: {text}")
        if job:
            job.update_progress(progress, f"[{step}/{len(self.STEPS)}] {text}")

    async def _eject(self, device: str):
        """Wirft die Disc aus."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "eject", device,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.communicate()
            log.info("Disc ausgeworfen", device=device)
        except Exception as e:
            log.warning("Auswerfen fehlgeschlagen", error=str(e))


class AudioCDWorkflow:
    """
    Workflow für Audio-CD-Erstellung.

    Konvertiert Audio-Dateien zu CDDA-WAV und brennt eine Audio-CD.
    Unterstützt auch YouTube/Mediathek-URLs als Quelle.

    Beispiel:
        wf = AudioCDWorkflow()
        await wf.run(
            sources=["song1.mp3", "song2.flac", "https://youtube.com/..."],
            device="/dev/sr0",
        )
    """

    def __init__(
        self,
        ffmpeg: Optional[FFmpeg] = None,
        disc_tools: Optional[DiscTools] = None,
        temp_dir: Optional[Path] = None,
    ):
        self.ffmpeg = ffmpeg or FFmpeg()
        self.disc = disc_tools or DiscTools()
        self.temp_dir = temp_dir or Path.home() / ".retrodisc" / "temp"

    async def prepare_tracks(
        self,
        sources: list[Path | str],
        work_dir: Optional[Path] = None,
        job: Optional[Job] = None,
    ) -> list[Path]:
        """
        Konvertiert alle Quellen zu CDDA-kompatiblen WAV-Dateien.

        CDDA-Standard: 16-bit PCM, 44100 Hz, Stereo

        Returns:
            Liste der fertigen WAV-Tracks in der richtigen Reihenfolge
        """
        work_dir = work_dir or self.temp_dir / "audio_cd"
        work_dir.mkdir(parents=True, exist_ok=True)

        wav_files = []
        for i, src in enumerate(sources):
            track_num = i + 1
            wav_out = work_dir / f"track_{track_num:02d}.wav"

            if job:
                job.update_progress(
                    (i / len(sources)) * 80,
                    f"Track {track_num}/{len(sources)} wird vorbereitet..."
                )

            # URL → Download
            if isinstance(src, str) and src.startswith(("http://", "https://")):
                from src.core.downloader import Downloader
                dl = Downloader(output_dir=work_dir)
                src = await dl.download(
                    url=src,
                    extract_audio=True,
                    audio_format="wav",
                )

            src = Path(src)

            # Bereits WAV in CDDA-Qualität?
            media = await self.ffmpeg.probe(src)
            is_cdda = (
                src.suffix.lower() == ".wav"
                and media.audio_streams
                and media.audio_streams[0].sample_rate == 44100
                and media.audio_streams[0].channels == 2
            )

            if is_cdda and src != wav_out:
                import shutil
                shutil.copy2(src, wav_out)
            elif not is_cdda:
                await self.ffmpeg.convert(
                    input_path=src,
                    output_path=wav_out,
                    audio_codec="pcm_s16le",
                    sample_rate=44100,
                    extra_args=["-ac", "2", "-vn"],
                    job=None,  # Progress schon oben gesetzt
                )

            wav_files.append(wav_out)
            log.info(f"Track {track_num} bereit", file=wav_out.name)

        return wav_files

    async def get_total_duration(self, wav_files: list[Path]) -> float:
        """Berechnet die Gesamtdauer aller Tracks in Minuten."""
        total = 0.0
        for f in wav_files:
            media = await self.ffmpeg.probe(f)
            total += media.duration_seconds
        return total / 60.0

    async def burn(
        self,
        wav_files: list[Path],
        device: str = "/dev/sr0",
        speed: Optional[int] = None,
        job: Optional[Job] = None,
    ) -> bool:
        """Brennt die vorbereiteten Tracks auf eine Audio-CD."""
        if not wav_files:
            raise ValueError("Keine Tracks vorhanden")

        total_min = await self.get_total_duration(wav_files)
        if total_min > 80:
            log.warning("CD-Kapazität überschritten",
                        minutes=f"{total_min:.1f}",
                        max=80)

        if job:
            job.update_progress(85, f"Brennen: {len(wav_files)} Tracks ({total_min:.1f} Min)...")

        # cdrecord/wodim für Audio-CD
        import shutil as sh
        cdrecord = sh.which("cdrecord") or sh.which("wodim") or "cdrecord"

        cmd = [cdrecord, f"dev={device}", "-v", "-dao", "-audio"]
        if speed:
            cmd.append(f"speed={speed}")
        cmd.extend([str(f) for f in wav_files])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            error = stderr.decode()[-300:]
            raise DiscError(f"Audio-CD Brennen fehlgeschlagen: {error}")

        if job:
            job.update_progress(98, "Audio-CD fertig!")

        log.info("Audio-CD gebrannt",
                 tracks=len(wav_files),
                 duration=f"{total_min:.1f} Min",
                 device=device)
        return True
