"""RetroDisc Disc — DVD/Blu-ray Authoring & Brennen."""

from __future__ import annotations

import asyncio
import shutil
import structlog
from pathlib import Path
from typing import Optional

from src.models.media import DiscType, Job

log = structlog.get_logger()


class DiscError(Exception):
    pass


class DiscTools:
    """
    DVD/Blu-ray Authoring, ISO-Erstellung und Disc-Brennen.

    Backend-Tools:
    - dvdauthor: DVD-Struktur (VIDEO_TS) erstellen
    - mkisofs/genisoimage: ISO-Images erstellen
    - growisofs: DVD/Blu-ray brennen
    - cdrecord/wodim: CD brennen

    Beispiel:
        disc = DiscTools()
        await disc.create_dvd_structure(mpeg_files, output_dir, title="Mein Film")
        await disc.create_iso(dvd_dir, "output.iso")
        await disc.burn_iso("output.iso", device="/dev/sr0")
    """

    def __init__(
        self,
        dvdauthor_path: Optional[str] = None,
        mkisofs_path: Optional[str] = None,
        growisofs_path: Optional[str] = None,
        cdrecord_path: Optional[str] = None,
    ):
        self.dvdauthor = dvdauthor_path or shutil.which("dvdauthor") or "dvdauthor"
        self.mkisofs = mkisofs_path or shutil.which("mkisofs") or shutil.which("genisoimage") or "mkisofs"
        self.growisofs = growisofs_path or shutil.which("growisofs") or "growisofs"
        self.cdrecord = cdrecord_path or shutil.which("cdrecord") or shutil.which("wodim") or "cdrecord"

    async def validate(self) -> dict[str, bool]:
        """Prüft welche Disc-Tools verfügbar sind."""
        tools = {}
        for name, path in [
            ("dvdauthor", self.dvdauthor),
            ("mkisofs", self.mkisofs),
            ("growisofs", self.growisofs),
            ("cdrecord", self.cdrecord),
        ]:
            tools[name] = shutil.which(path) is not None
            if tools[name]:
                log.info(f"{name} gefunden", path=path)
            else:
                log.warning(f"{name} nicht gefunden", path=path)
        return tools

    async def create_dvd_structure(
        self,
        mpeg_files: list[Path],
        output_dir: Path,
        title: str = "RetroDisc DVD",
        standard: str = "PAL",
        job: Optional[Job] = None,
    ) -> Path:
        """
        Erstellt eine DVD-Verzeichnisstruktur (VIDEO_TS) aus MPEG-Dateien.

        Args:
            mpeg_files: Liste der DVD-kompatiblen MPEG-Dateien
            output_dir: Zielverzeichnis für die DVD-Struktur
            title: DVD-Titel
            standard: "PAL" oder "NTSC"
            job: Job für Progress-Updates

        Returns:
            Pfad zum DVD-Verzeichnis (enthält VIDEO_TS/)
        """
        output_dir = Path(output_dir)
        dvd_dir = output_dir / "DVD"
        dvd_dir.mkdir(parents=True, exist_ok=True)

        # XML-Konfiguration für dvdauthor erstellen
        xml_path = output_dir / "dvdauthor.xml"
        vob_entries = "\n".join(
            f'        <vob file="{f.resolve()}" />' for f in mpeg_files
        )

        xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<dvdauthor dest="{dvd_dir.resolve()}">
  <vmgm />
  <titleset>
    <titles>
      <pgc>
{vob_entries}
      </pgc>
    </titles>
  </titleset>
</dvdauthor>
"""
        xml_path.write_text(xml_content)

        # VIDEO_FORMAT setzen
        import os
        env = os.environ.copy()
        env["VIDEO_FORMAT"] = standard

        if job:
            job.update_progress(10, "DVD-Struktur wird erstellt...")

        cmd = [self.dvdauthor, "-x", str(xml_path)]
        proc = await asyncio.create_subprocess_exec(
            *cmd, env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise DiscError(f"dvdauthor Fehler: {stderr.decode()}")

        # VIDEO_TS Ordner prüfen
        video_ts = dvd_dir / "VIDEO_TS"
        if not video_ts.exists():
            raise DiscError("VIDEO_TS Ordner wurde nicht erstellt")

        if job:
            job.update_progress(90, "DVD-Struktur erstellt")

        log.info("DVD-Struktur erstellt", path=str(dvd_dir), files=len(mpeg_files))

        # Cleanup
        xml_path.unlink(missing_ok=True)

        return dvd_dir

    async def create_iso(
        self,
        source_dir: Path,
        output_path: Path,
        volume_label: str = "RETRODISC",
        disc_type: DiscType = DiscType.DVD,
        job: Optional[Job] = None,
    ) -> Path:
        """
        Erstellt ein ISO-Image aus einem Verzeichnis.

        Args:
            source_dir: Quellverzeichnis (z.B. DVD-Struktur)
            output_path: Pfad für die ISO-Datei
            volume_label: Volume-Label der Disc
            disc_type: DVD, Blu-ray oder CD
            job: Job für Progress-Updates
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if job:
            job.update_progress(5, "ISO-Image wird erstellt...")

        cmd = [
            self.mkisofs,
            "-V", volume_label[:32],  # Max 32 Zeichen
            "-o", str(output_path),
        ]

        if disc_type == DiscType.DVD:
            cmd.extend([
                "-dvd-video",  # DVD-Video Kompatibilität
                "-udf",        # UDF Dateisystem
            ])
        elif disc_type == DiscType.BLURAY:
            cmd.extend(["-udf", "-allow-limited-size"])

        cmd.append(str(source_dir))

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise DiscError(f"ISO-Erstellung fehlgeschlagen: {stderr.decode()[-500:]}")

        if not output_path.exists():
            raise DiscError(f"ISO-Datei wurde nicht erstellt: {output_path}")

        size_mb = output_path.stat().st_size / (1024 * 1024)
        log.info("ISO erstellt", path=str(output_path), size_mb=f"{size_mb:.1f}")

        if job:
            job.update_progress(95, f"ISO erstellt ({size_mb:.0f} MB)")

        return output_path

    async def burn_iso(
        self,
        iso_path: Path,
        device: str = "/dev/sr0",
        speed: Optional[int] = None,
        verify: bool = True,
        disc_type: DiscType = DiscType.DVD,
        job: Optional[Job] = None,
    ) -> bool:
        """
        Brennt ein ISO-Image auf eine Disc.

        Args:
            iso_path: Pfad zur ISO-Datei
            device: Brenner-Device
            speed: Brenngeschwindigkeit (None = Auto)
            verify: Nach dem Brennen verifizieren
            disc_type: DVD, Blu-ray oder CD
            job: Job für Progress-Updates

        Returns:
            True wenn erfolgreich
        """
        iso_path = Path(iso_path)
        if not iso_path.exists():
            raise DiscError(f"ISO-Datei nicht gefunden: {iso_path}")

        if job:
            job.update_progress(5, "Brennvorgang wird gestartet...")

        if disc_type in (DiscType.DVD, DiscType.BLURAY):
            cmd = [
                self.growisofs,
                "-dvd-compat",
                f"-Z", f"{device}={iso_path}",
            ]
            if speed:
                cmd.extend(["-speed", str(speed)])
        else:
            # CD brennen
            cmd = [
                self.cdrecord,
                f"dev={device}",
                "-v",
                "-dao",
            ]
            if speed:
                cmd.extend([f"speed={speed}"])
            cmd.append(str(iso_path))

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Progress aus Output parsen
        while True:
            line = await proc.stderr.readline() if proc.stderr else b""
            if not line:
                break
            line_str = line.decode("utf-8", errors="replace")

            if job and "%" in line_str:
                import re
                match = re.search(r"(\d+\.?\d*)%", line_str)
                if match:
                    progress = float(match.group(1))
                    job.update_progress(progress * 0.9, f"Brennen: {progress:.0f}%")

        await proc.wait()

        if proc.returncode != 0:
            raise DiscError("Brennvorgang fehlgeschlagen")

        if job:
            job.update_progress(95, "Brennvorgang abgeschlossen")

        log.info("Disc gebrannt", iso=str(iso_path), device=device)
        return True

    async def get_disc_info(self, device: str = "/dev/sr0") -> dict:
        """Liest Informationen über eine eingelegte Disc."""
        # Über isoinfo oder cdrecord
        info = {"device": device, "type": "unknown", "label": "", "tracks": 0}

        try:
            proc = await asyncio.create_subprocess_exec(
                "isoinfo", "-d", f"-i", device,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            output = stdout.decode()

            for line in output.split("\n"):
                if "Volume id:" in line:
                    info["label"] = line.split(":", 1)[1].strip()
                elif "Volume size is:" in line:
                    try:
                        blocks = int(line.split(":", 1)[1].strip())
                        info["size_mb"] = (blocks * 2048) / (1024 * 1024)
                    except ValueError:
                        pass
        except Exception as e:
            log.warning("Disc-Info Fehler", error=str(e))

        return info
