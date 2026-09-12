"""RetroDisc Blu-ray Workflow - kompletter High-Level BDMV-Erstellungs-Prozess.

Spiegelt ``src/services/dvd_workflow.py::DVDWorkflow`` bewusst 1:1 in Ablauf
und Struktur (Quelle prüfen -> Video wandeln -> Struktur erzeugen -> ISO
erzeugen -> optional brennen), nur mit den Blu-ray-Bausteinen aus diesem
Block statt dvdauthor/DVD-MPEG:

1. Quelle prüfen
2. Zu BD-kompatiblem M2TS wandeln (FFmpeg.to_bluray_stream)
3. BDMV-Struktur erstellen (bluray_authoring.author_bdmv)
4. ISO-Image erstellen (DiscTools.create_iso, disc_type=BLURAY)
5. Optional: auf Disc brennen (DiscTools.burn_iso, disc_type=BLURAY -
   Book Type ist für Blu-ray immer NOT_APPLICABLE, siehe DiscTools._apply_book_type)

Gilt für ALLE ``AuthoringFormat.BDMV``-Zielmedien - sowohl physische
Blu-ray-Rohlinge (BD-25/50/BDXL-100/128) als auch eine BDMV-Struktur auf
einem gewöhnlichen DVD-5/9-Rohling (``bdmv_on_dvd5``/``bdmv_on_dvd9``): die
Struktur- und ISO-Erzeugung ist in beiden Fällen identisch, nur das
physische Zielmedium beim Brennen unterscheidet sich.
"""
from __future__ import annotations

import re
import uuid
import structlog
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from src.core.ffmpeg import FFmpeg
from src.core.disc import DiscTools, DiscError
from src.models.media import DiscType, Job, JobType
from src.services.bluray_authoring import author_bdmv

log = structlog.get_logger()


def _safe_windows_name(value: str, fallback: str = "RetroDisc_BD") -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value.strip())
    cleaned = re.sub(r"\s+", "_", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned).strip(" ._")
    return (cleaned[:40] or fallback)


@dataclass
class BlurayProject:
    """Beschreibt ein Blu-ray-(BDMV-)Projekt."""
    title: str = "RetroDisc Blu-ray"
    input_files: list[Path] = field(default_factory=list)
    output_dir: Optional[Path] = None
    target_medium_id: str = "bd25"
    video_bitrate_bps: Optional[int] = None   # None = konservativer Standardwert in to_bluray_stream
    burn_to_disc: bool = False
    disc_device: str = "/dev/sr0"
    burn_speed: Optional[int] = None
    verify_after_burn: bool = True
    eject_after_burn: bool = True
    only_iso: bool = False


class BlurayWorkflow:
    """Vollständiger BDMV-Erstellungs-Workflow, analog zu ``DVDWorkflow``."""

    STEPS = [
        "Quelldateien prüfen",
        "Video in BD-Format konvertieren",
        "BDMV-Struktur erstellen",
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

    async def run(self, project: BlurayProject, job: Optional[Job] = None) -> Path:
        """Führt den kompletten Blu-ray-Workflow durch.

        Returns:
            Pfad zur fertigen ISO-Datei.
        """
        if not project.input_files:
            raise ValueError("Keine Quelldateien angegeben")

        safe_name = _safe_windows_name(project.title)
        work_dir = self.temp_dir / f"bd_{safe_name}_{uuid.uuid4().hex[:8]}"
        work_dir.mkdir(parents=True, exist_ok=True)
        out_dir = project.output_dir or work_dir.parent

        log.info("Blu-ray-Workflow gestartet", title=project.title, files=len(project.input_files))

        try:
            self._step(job, 1, 5, "Quelldateien werden geprüft...")
            for f in project.input_files:
                if not f.exists():
                    raise FileNotFoundError(f"Quelldatei nicht gefunden: {f}")

            self._step(job, 2, 15, "Video wird in BD-Format gewandelt (BDMV-Authoring läuft)...")
            bd_root = await author_bdmv(
                self.ffmpeg, project.input_files, work_dir,
                video_bitrate_bps=project.video_bitrate_bps, job=job,
            )
            self._step(job, 3, 70, "BDMV-Struktur erstellt")

            self._step(job, 4, 75, "ISO-Image wird erstellt...")
            safe_title = safe_name[:32].upper()
            iso_path = out_dir / f"{safe_name}.iso"
            iso_path = await self.disc.create_iso(
                source_dir=bd_root, output_path=iso_path,
                volume_label=safe_title, disc_type=DiscType.BLURAY, job=job,
            )

            if project.burn_to_disc and not project.only_iso:
                from src.services.booktype import BookType
                from src.services.verify import FAIL as VERIFY_FAIL

                self._step(job, 5, 85, f"Wird auf Disc geschrieben ({project.disc_device})...")
                outcome = await self.disc.burn_iso(
                    iso_path=iso_path, device=project.disc_device, speed=project.burn_speed,
                    verify=project.verify_after_burn, disc_type=DiscType.BLURAY, job=job,
                    book_type=BookType.NATIVE,   # Book Type ist für Blu-ray nicht anwendbar
                )
                if job is not None:
                    job.params["burn_outcome"] = outcome.to_dict()
                if outcome.verify.status == VERIFY_FAIL:
                    raise DiscError(f"Verifikation fehlgeschlagen: {outcome.verify.message}")
                if project.eject_after_burn:
                    await self._eject(project.disc_device)
            else:
                self._step(job, 5, 90, "Kein Brennen (nur ISO)...")

            self._step(job, 6, 100, f"Blu-ray '{project.title}' fertig!")
            log.info("Blu-ray-Workflow abgeschlossen", title=project.title, iso=str(iso_path))
            return iso_path
        finally:
            import shutil
            shutil.rmtree(work_dir, ignore_errors=True)

    def _step(self, job: Optional[Job], step: int, progress: float, text: str):
        log.info(f"Blu-ray-Schritt {step}/{len(self.STEPS)}: {text}")
        if job:
            job.update_progress(progress, f"[{step}/{len(self.STEPS)}] {text}")

    async def _eject(self, device: str):
        from src.services.dvd_workflow import DVDWorkflow
        await DVDWorkflow()._eject(device)
