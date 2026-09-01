"""RetroDisc Disc — DVD/Blu-ray Authoring & Brennen."""

from __future__ import annotations

import asyncio
import shutil
import structlog
from pathlib import Path
from typing import Optional

from src.models.media import DiscType, Job
from src.utils.subprocesses import create_hidden_subprocess

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
        mediainfo_path: Optional[str] = None,
    ):
        self.dvdauthor = dvdauthor_path or shutil.which("dvdauthor") or "dvdauthor"
        self.mkisofs = mkisofs_path or shutil.which("mkisofs") or shutil.which("genisoimage") or "mkisofs"
        self.growisofs = growisofs_path or shutil.which("growisofs") or "growisofs"
        self.cdrecord = cdrecord_path or shutil.which("cdrecord") or shutil.which("wodim") or "cdrecord"
        self.mediainfo = mediainfo_path or shutil.which("dvd+rw-mediainfo") or "dvd+rw-mediainfo"

    async def validate(self) -> dict[str, bool]:
        """Prüft welche Disc-Tools verfügbar sind."""
        tools = {}
        for name, path in [
            ("dvdauthor", self.dvdauthor),
            ("mkisofs", self.mkisofs),
            ("growisofs", self.growisofs),
            ("cdrecord", self.cdrecord),
            ("dvd+rw-mediainfo", self.mediainfo),
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

        # XML-Konfiguration mit ElementTree erstellen, damit Unicode und
        # Sonderzeichen in Windows-Pfaden korrekt escaped werden.
        import xml.etree.ElementTree as ET
        xml_path = output_dir / "dvdauthor.xml"
        root = ET.Element("dvdauthor", {"dest": str(dvd_dir.resolve())})
        ET.SubElement(root, "vmgm")
        titleset = ET.SubElement(root, "titleset")
        titles = ET.SubElement(titleset, "titles")
        pgc = ET.SubElement(titles, "pgc")
        for media_file in mpeg_files:
            ET.SubElement(pgc, "vob", {"file": str(media_file.resolve())})
        ET.ElementTree(root).write(xml_path, encoding="utf-8", xml_declaration=True)

        # VIDEO_FORMAT setzen
        import os
        env = os.environ.copy()
        env["VIDEO_FORMAT"] = standard.strip().upper()

        if job:
            job.update_progress(10, "DVD-Struktur wird erstellt...")

        cmd = [self.dvdauthor, "-x", str(xml_path)]
        proc = await create_hidden_subprocess(
            *cmd, env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        if job:
            job._process = proc
        _, stderr = await proc.communicate()
        if job:
            job._process = None

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

        proc = await create_hidden_subprocess(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        if job:
            job._process = proc
        _, stderr = await proc.communicate()
        if job:
            job._process = None

        if proc.returncode != 0:
            raise DiscError(f"ISO-Erstellung fehlgeschlagen: {stderr.decode('utf-8', errors='replace')[-1000:]}")

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

        proc = await create_hidden_subprocess(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        if job:
            job._process = proc

        # Beide Pipes gleichzeitig leeren, damit lange Brennläufe nicht durch
        # einen vollen stdout/stderr-Puffer blockieren.
        stdout, stderr = await proc.communicate()
        if job:
            job._process = None
        combined = (stdout + b"\n" + stderr).decode("utf-8", errors="replace")
        if job:
            import re
            percentages = re.findall(r"(\d+(?:\.\d+)?)%", combined)
            if percentages:
                progress = float(percentages[-1])
                job.update_progress(min(progress * 0.9, 90), f"Brennen: {progress:.0f}%")

        if proc.returncode != 0:
            raise DiscError(f"Brennvorgang fehlgeschlagen: {combined[-1200:]}")

        if job:
            job.update_progress(95, "Brennvorgang abgeschlossen")

        log.info("Disc gebrannt", iso=str(iso_path), device=device)
        if verify:
            if job:
                job.update_progress(96, "Gebrannte Daten werden verifiziert...")
            await self.verify_iso(iso_path, device)
            if job:
                job.update_progress(99, "Verifikation erfolgreich")
        return True

    async def verify_iso(self, iso_path: Path, device: str) -> bool:
        """Compares the ISO bytes with the beginning of the burned medium."""
        import hashlib
        import os

        source = Path(iso_path)
        raw_device = device
        import re
        if os.name == "nt" and re.fullmatch(r"[A-Za-z]:[\\/]?", device):
            raw_device = rf"\\.\{device[:2]}"

        def _digest(path_or_device, byte_limit: Optional[int] = None) -> str:
            digest = hashlib.sha256()
            remaining = byte_limit
            with open(path_or_device, "rb", buffering=0) as stream:
                while remaining is None or remaining > 0:
                    amount = 1024 * 1024 if remaining is None else min(1024 * 1024, remaining)
                    chunk = stream.read(amount)
                    if not chunk:
                        break
                    digest.update(chunk)
                    if remaining is not None:
                        remaining -= len(chunk)
            if remaining not in (None, 0):
                raise DiscError("Das gebrannte Medium ist kürzer als das ISO-Image.")
            return digest.hexdigest()

        try:
            iso_hash, disc_hash = await asyncio.gather(
                asyncio.to_thread(_digest, source),
                asyncio.to_thread(_digest, raw_device, source.stat().st_size),
            )
        except Exception as e:
            if isinstance(e, DiscError):
                raise
            raise DiscError(f"Disc-Verifikation konnte nicht gelesen werden: {e}") from e
        if iso_hash != disc_hash:
            raise DiscError("Disc-Verifikation fehlgeschlagen: Prüfsummen stimmen nicht überein.")
        log.info("Disc verifiziert", iso=str(source), device=device, sha256=iso_hash)
        return True

    async def get_disc_info(self, device: str = "/dev/sr0") -> dict:
        """Liest Medienprofil und Kapazität eines optischen Laufwerks."""
        info = {
            "device": device, "present": False, "readable": False,
            "type": "unknown", "profile": "", "label": "", "tracks": 0,
            "blank": False, "rewritable": False,
        }

        # Windows: dvd+rw-mediainfo kann auch leere Rohlinge und Medienprofile
        # auslesen und wird mit RetroDisc gebündelt.
        import os
        if os.name == "nt" and shutil.which(self.mediainfo):
            try:
                proc = await create_hidden_subprocess(
                    self.mediainfo, device,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=20)
                output = (stdout + b"\n" + stderr).decode("utf-8", errors="replace")
                lower_output = output.lower()
                if ("no media mounted" in lower_output
                        or "unable to test unit ready" in lower_output
                        or "medium not present" in lower_output):
                    return info
                info["present"] = True

                import re
                mounted = re.search(r"Mounted Media:\s+.*?\"([^\"]+)\"", output, re.I)
                if mounted:
                    profile = mounted.group(1).strip()
                    info["profile"] = profile
                    info["type"] = profile
                    upper = profile.upper()
                    info["rewritable"] = any(x in upper for x in ("RW", "RAM", "RE"))
                status = re.search(r"Disc status:\s*([^\r\n]+)", output, re.I)
                if status:
                    disc_status = status.group(1).strip().lower()
                    info["blank"] = "blank" in disc_status or "empty" in disc_status
                    info["readable"] = not info["blank"]
                capacity = re.search(r"READ CAPACITY:.*?=\s*(\d+)", output, re.I)
                if capacity:
                    size_bytes = int(capacity.group(1))
                    info["capacity_bytes"] = size_bytes
                    info["capacity_gb"] = round(size_bytes / (1024 ** 3), 2)
                info["raw"] = output[-4000:]
                return info
            except Exception as exc:
                log.warning("dvd+rw-mediainfo Fehler", error=str(exc), device=device)

        # Portable ISO9660-Fallback für bereits beschriebene Medien.
        isoinfo = shutil.which("isoinfo")
        if not isoinfo:
            return info
        try:
            proc = await create_hidden_subprocess(
                isoinfo, "-d", "-i", device,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode != 0:
                return info
            output = stdout.decode("utf-8", errors="replace")
            info["present"] = info["readable"] = True
            for line in output.splitlines():
                if "Volume id:" in line:
                    info["label"] = line.split(":", 1)[1].strip()
                elif "Volume size is:" in line:
                    try:
                        blocks = int(line.split(":", 1)[1].strip())
                        info["capacity_bytes"] = blocks * 2048
                        info["capacity_gb"] = round((blocks * 2048) / (1024 ** 3), 2)
                    except ValueError:
                        pass
        except Exception as exc:
            log.warning("Disc-Info Fehler", error=str(exc))
        return info
