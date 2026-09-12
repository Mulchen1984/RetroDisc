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


class _MediaInfoInconclusive(Exception):
    """dvd+rw-mediainfo lieferte keinen belastbaren Medienbefund.

    Interner Kontrollfluss von :meth:`DiscTools.get_disc_info`: weder "Medium
    vorhanden" noch "kein Medium" ist damit belegt, es entscheidet der
    Dateisystem-Fallback.
    """


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
        # Book type / bitsetting backend (optional; capability checked before use).
        self.booktype = shutil.which("dvd+rw-booktype") or ""

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
            raise DiscError(f"dvdauthor Fehler: {stderr.decode('utf-8', errors='replace')}")

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

        # Früher Abbruch statt die Platte mitten im Lauf zu füllen.
        from src.services.disk_space import directory_size, ensure_space, iso_estimate
        ensure_space(output_path.parent, iso_estimate(source_dir))

        if job:
            job.update_progress(5, "ISO-Image wird erstellt...")

        base_cmd = [self.mkisofs, "-V", volume_label[:32], "-o", str(output_path)]  # Max 32 Zeichen

        if disc_type == DiscType.DVD:
            flag_sets = [["-dvd-video", "-udf"]]   # DVD-Video-konformes UDF-Dateisystem
        elif disc_type == DiscType.BLURAY:
            # "-allow-limited-size" ist die für große Blu-ray-Clips (oft weit
            # über 4 GiB je Datei) korrekte genisoimage/xorriso-Option. Real
            # gegen die hier verfügbare mkisofs-Variante getestet: ein
            # dvdrtools-basierter Build kennt das Flag nicht und bricht mit
            # "unrecognized option" ab - deshalb der Fallback. "-udf
            # -iso-level 3" ALLEIN reicht nicht als Ersatz: dieselbe
            # dvdrtools-Variante verwirft dabei Dateien >4 GiB
            # stillschweigend (Exit-Code 0, aber ein kaputt-kleines Image) -
            # das fängt die Größenprüfung unten ab, egal welcher mkisofs-
            # Fork tatsächlich im produktiven Windows-Vendor-Paket steckt.
            flag_sets = [["-udf", "-allow-limited-size"], ["-udf", "-iso-level", "3"]]
        else:
            flag_sets = [[]]

        stderr_text = ""
        for attempt, flags in enumerate(flag_sets):
            cmd = base_cmd + flags + [str(source_dir)]
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
            stderr_text = stderr.decode("utf-8", errors="replace")

            if proc.returncode == 0:
                break
            is_last_attempt = attempt == len(flag_sets) - 1
            if is_last_attempt or "unrecognized option" not in stderr_text.lower():
                raise DiscError(f"ISO-Erstellung fehlgeschlagen: {stderr_text[-1000:]}")
            log.warning("mkisofs-Flag nicht unterstützt, versuche Fallback",
                       flags=flags, stderr=stderr_text[-300:])

        if not output_path.exists():
            raise DiscError(f"ISO-Datei wurde nicht erstellt: {output_path}")

        written_bytes = output_path.stat().st_size
        payload_bytes = directory_size(source_dir)
        # Ein ISO ist grundsätzlich mindestens so groß wie sein Nutzinhalt
        # (Dateisystem-Overhead kommt oben drauf, nie ab). Deutlich kleiner
        # heißt: der ISO-Backend hat mindestens eine Datei stillschweigend
        # verworfen oder abgeschnitten (siehe Flag-Fallback-Kommentar oben) -
        # ein solches Image nie unbemerkt als Erfolg zurückgeben.
        if payload_bytes > 0 and written_bytes < payload_bytes * 0.9:
            raise DiscError(
                f"ISO-Erstellung ergab ein verdächtig kleines Abbild ({written_bytes} Bytes "
                f"gegenüber {payload_bytes} Bytes Quellinhalt) - vermutlich wurde mindestens "
                f"eine große Datei vom ISO-Backend stillschweigend verworfen. "
                f"mkisofs-Ausgabe: {stderr_text[-500:]}"
            )

        size_mb = written_bytes / (1024 * 1024)
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
        book_type: "BookType" = None,
        media_type: Optional[str] = None,
    ):
        """
        Der eine kanonische Brennpfad (siehe P0_BURN_PIPELINE_BOOKTYPE.md).

        Brennt ein ISO-Image auf eine Disc, wendet optional Book Type an und
        verifiziert optional - alles über denselben Weg, egal ob über
        ``create_dvd``/``DVDWorkflow`` oder ``copy_disc`` aufgerufen.

        Args:
            iso_path: Pfad zur ISO-Datei
            device: Brenner-Device
            speed: Brenngeschwindigkeit (None = Auto)
            verify: Nach dem Brennen verifizieren (strukturiert, siehe unten)
            disc_type: DVD, Blu-ray oder CD
            job: Job für Progress-Updates
            book_type: AUTO/NATIVE/DVD_ROM (Standard NATIVE = keine Änderung,
                Rückwärtskompatibilität für Aufrufer, die Book Type nicht kennen)
            media_type: Medienfamilie (z. B. "DVD+R"); wird bei ``None``
                automatisch über ``get_disc_info`` ermittelt

        Raises:
            DiscError: wenn der eigentliche Brennvorgang fehlschlägt (nicht
                bei einer fehlgeschlagenen Book-Type-Änderung oder einer
                fehlgeschlagenen Verifikation - beides wird stattdessen im
                zurückgegebenen ``BurnOutcome`` gemeldet).

        Returns:
            BurnOutcome mit getrennten Erfolgsachsen für Brennen, Book Type
            und Verifikation. Ist bei Erfolg immer truthy (kein leeres
            Datenobjekt), sodass ``if await burn_iso(...):`` für bestehende
            Aufrufer weiterhin wie erwartet funktioniert.
        """
        from src.services.booktype import BookType, _as_book_type
        from src.services.burn_outcome import BookTypeStatus, BurnOutcome
        from src.services.verify import NOT_AVAILABLE

        book_type = BookType.NATIVE if book_type is None else _as_book_type(book_type)

        iso_path = Path(iso_path)
        if not iso_path.exists():
            raise DiscError(f"ISO-Datei nicht gefunden: {iso_path}")

        if media_type is None:
            media_type = await self._resolve_media_type(device)

        outcome = BurnOutcome(device=device, disc_type=disc_type.value, media_type=media_type,
                              book_type_requested=book_type.value)

        # Book Type VOR dem Brennen setzen: dvd+rw-booktype wirkt auf den
        # eingelegten Rohling, nicht auf den ISO-Inhalt.
        await self._apply_book_type(outcome, book_type, media_type, disc_type, device)

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
        outcome.burn_success = True
        outcome.burn_speed = f"{speed}x" if speed else "auto"
        try:
            outcome.written_size = iso_path.stat().st_size
        except OSError:
            pass

        if outcome.book_type_status == BookTypeStatus.APPLIED:
            outcome.book_type_actual = await self._read_book_type(device)

        if verify:
            if job:
                job.update_progress(96, "Gebrannte Daten werden verifiziert...")
            outcome.verify = await self.verify_iso_result(iso_path, device)
            if job:
                job.update_progress(99, "Verifikation abgeschlossen")
        else:
            outcome.verify.status = NOT_AVAILABLE
            outcome.verify.message = "Verifikation deaktiviert."

        return outcome

    async def _resolve_media_type(self, device: str) -> str:
        from src.services.booktype import classify_media
        try:
            info = await self.get_disc_info(device)
            return classify_media(info.get("profile") or info.get("type") or "")
        except Exception:
            return "unknown"

    async def _apply_book_type(self, outcome, book_type: "BookType", media_type: str,
                               disc_type: DiscType, device: str) -> None:
        """Setzt ``outcome.book_type_status`` (und ggf. ``book_type_warning``).

        Wirft nie - eine fehlgeschlagene oder nicht mögliche Book-Type-
        Änderung darf den Brennvorgang selbst nie verhindern.
        """
        from src.services.booktype import BookType, booktype_command, supports_bitsetting
        from src.services.burn_outcome import BookTypeStatus

        if book_type == BookType.NATIVE:
            outcome.book_type_status = BookTypeStatus.NOT_REQUESTED
            return

        # Blu-ray bekommt nie eine DVD-spezifische Book-Type-Operation,
        # unabhängig davon, wie media_type klassifiziert wurde.
        if disc_type == DiscType.BLURAY or not supports_bitsetting(media_type):
            outcome.book_type_status = BookTypeStatus.NOT_APPLICABLE
            return

        if not self.book_type_available(media_type):
            outcome.book_type_status = BookTypeStatus.NOT_SUPPORTED
            outcome.book_type_warning = "Laufwerk/Backend unterstützt kein Bitsetting; Book Type unverändert."
            return

        cmd = booktype_command(self.booktype, device, BookType.DVD_ROM, media_type)
        try:
            if cmd:
                await self._run_tool(cmd)
            outcome.book_type_status = BookTypeStatus.APPLIED
        except Exception as exc:
            outcome.book_type_status = BookTypeStatus.FAILED
            outcome.book_type_warning = f"Book Type konnte nicht gesetzt werden: {exc}"

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

    async def verify_iso_result(self, iso_path: Path, device: str):
        """Structured verify result (PASS/FAIL/NOT_AVAILABLE) around verify_iso."""
        from src.services.verify import VerifyResult, Check
        try:
            await self.verify_iso(iso_path, device)
            return VerifyResult.from_checks([Check("hash", True, "Prüfsumme identisch."),
                                             Check("size", True, "Länge stimmt überein.")])
        except DiscError as exc:
            text = str(exc)
            name = "size" if "kürzer" in text or "länger" in text else "hash"
            if "konnte nicht gelesen" in text:            # Lesefehler -> nicht bewertbar
                return VerifyResult.from_checks([Check("read", None, text)])
            return VerifyResult.from_checks([Check(name, False, text)])

    # ── Book type / bitsetting ──────────────────────────────────────────
    def book_type_available(self, media_type: str) -> bool:
        from src.services.booktype import bitsetting_available
        return bitsetting_available(media_type, bool(self.booktype and shutil.which(self.booktype)))

    async def _run_tool(self, cmd: list[str], timeout: int = 30) -> str:
        proc = await create_hidden_subprocess(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        output = (stdout + b"\n" + stderr).decode("utf-8", errors="replace")
        if proc.returncode:
            from src.core.errors import ExternalToolError
            raise ExternalToolError(tool=cmd[0], returncode=proc.returncode, detail=output[-800:])
        return output

    async def _read_book_type(self, device: str) -> str:
        from src.services.booktype import parse_book_type
        try:
            return parse_book_type(await self._run_tool([self.booktype, "-media", device]))
        except Exception:
            return "unknown"

    async def burn_iso_result(self, iso_path: Path, device: str = "/dev/sr0", *,
                              disc_type: DiscType = DiscType.DVD, speed: Optional[int] = None,
                              verify: bool = True, book_type: str = "automatic",
                              media_type: str = "unknown", job: Optional[Job] = None):
        """Burn and return a structured BurnResult, including book type when supported.

        Book type is only set/read when the media family AND the backend support
        it; otherwise a warning is recorded and burning proceeds normally.
        """
        from src.services.booktype import BurnResult, booktype_command, supports_bitsetting
        result = BurnResult(media_type=media_type, book_type_requested=book_type)

        if book_type == "dvd_rom" and supports_bitsetting(media_type):
            if not self.book_type_available(media_type):
                result.warnings.append("Laufwerk/Backend unterstützt kein Bitsetting; Book Type unverändert.")
            else:
                cmd = booktype_command(self.booktype, device, book_type, media_type)
                try:
                    if cmd:
                        await self._run_tool(cmd)
                except Exception as exc:
                    result.warnings.append(f"Book Type konnte nicht gesetzt werden: {exc}")

        await self.burn_iso(iso_path, device, speed=speed, verify=verify,
                            disc_type=disc_type, job=job)
        try:
            result.written_size = Path(iso_path).stat().st_size
        except OSError:
            pass
        result.burn_speed = f"{speed}x" if speed else "auto"
        if supports_bitsetting(media_type) and self.book_type_available(media_type):
            result.book_type_actual = await self._read_book_type(device)
        result.verify_result = "PASS" if verify else "NOT_AVAILABLE"
        return result

    async def inspect_drive(self, device: str):
        """Detect drive capabilities via dvd+rw-mediainfo (detection only)."""
        from src.services.drive_inspector import parse_capabilities
        output = ""
        try:
            proc = await create_hidden_subprocess(
                self.mediainfo, device, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE)
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=20)
            output = (stdout + b"\n" + stderr).decode("utf-8", errors="replace")
        except (OSError, asyncio.TimeoutError) as exc:
            log.debug("inspect_drive: Werkzeug nicht ausführbar", device=device, error=str(exc))
        return parse_capabilities(output, drive_letter=device)

    @staticmethod
    def _windows_volume_info(device: str, info: dict) -> dict:
        """Ermittelt den Medienzustand eines Windows-Laufwerks am Dateisystem.

        Liefert ``present``/``readable`` nur, wenn das Wurzelverzeichnis
        tatsaechlich gelesen werden kann. Ein nicht vorhandener Buchstabe und
        ein leeres Laufwerk fallen damit beide korrekt auf "kein Medium"
        zurueck, ohne dass eine lokalisierte Fehlermeldung geraten werden muss.
        """
        import ctypes
        import os

        letter = device.strip().rstrip("\\/")
        if len(letter) == 1:
            letter = f"{letter}:"
        root = Path(f"{letter}\\")
        try:
            entries = list(os.scandir(root))
        except OSError:
            return info

        info["present"] = True
        info["readable"] = True
        if (root / "VIDEO_TS").is_dir():
            info["type"] = "DVD-Video"
        elif (root / "BDMV").is_dir():
            info["type"] = "Blu-ray"
        elif entries:
            info["type"] = "data"
        else:
            # Lesbar, aber leer: das ist ein beschreibbarer Rohling.
            info["blank"] = True
            info["readable"] = False
            info["type"] = "blank"
        info["tracks"] = len(entries)

        label = ctypes.create_unicode_buffer(261)
        filesystem = ctypes.create_unicode_buffer(261)
        try:
            if ctypes.windll.kernel32.GetVolumeInformationW(
                ctypes.c_wchar_p(str(root)), label, 261,
                None, None, None, filesystem, 261,
            ):
                info["label"] = label.value
                info["filesystem"] = filesystem.value
        except OSError as exc:  # pragma: no cover - hostabhaengig
            log.debug("GetVolumeInformationW fehlgeschlagen", device=device, error=str(exc))

        try:
            usage = shutil.disk_usage(root)
            info["capacity_bytes"] = usage.total
            info["capacity_gb"] = round(usage.total / (1024 ** 3), 2)
        except OSError:
            pass
        return info

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
                    # Auch "kein Medium" ist unter Windows kein Endergebnis:
                    # bei einem virtuell eingebundenen Abbild meldet das
                    # Werkzeug "unable to TEST UNIT READY", obwohl VIDEO_TS
                    # lesbar ist und das Rippen funktioniert. Ein wirklich
                    # leeres Laufwerk faellt im Dateisystem-Fallback ohnehin
                    # korrekt auf present=False zurueck.
                    raise _MediaInfoInconclusive(output)

                import re

                # "present" darf nur aus einem Positivbeleg folgen. Vorher galt
                # jede Ausgabe als Medium, sofern sie keines von drei englischen
                # Fehlermustern enthielt. Auf einem deutschen Windows meldet das
                # Werkzeug fuer einen nicht existierenden Buchstaben aber
                # "Z:: unable to open: Ein oder mehrere Argumente sind
                # ungueltig." -- und RetroDisc behauptete daraufhin ein Medium in
                # einem Laufwerk, das es gar nicht gibt. Fehlt der Positivbeleg,
                # entscheidet stattdessen der Dateisystem-Fallback weiter unten.
                if not re.search(r"(Mounted Media|Disc status|READ CAPACITY)\s*:", output, re.I):
                    log.debug(
                        "dvd+rw-mediainfo ohne Medienbeleg", device=device, output=output[-400:]
                    )
                    raise _MediaInfoInconclusive(output)
                info["present"] = True

                # dvd+rw-mediainfo schreibt das Profil unquotiert hinter den
                # Hex-Code, etwa: `Mounted Media:  11h, DVD-R Sequential`.
                # Die fruehere Regex verlangte Anfuehrungszeichen und konnte
                # deshalb nie greifen -- profile, type und rewritable blieben
                # fuer jede echte Disc leer. Beide Formen werden akzeptiert.
                mounted = re.search(
                    r"Mounted Media:\s*(?:\"([^\"]+)\"|(?:[0-9A-Fa-f]{1,4}h\s*,\s*)?([^\r\n]+))",
                    output,
                    re.I,
                )
                if mounted:
                    profile = (mounted.group(1) or mounted.group(2) or "").strip().strip('"')
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
            except _MediaInfoInconclusive:
                pass
            except Exception as exc:
                log.warning("dvd+rw-mediainfo Fehler", error=str(exc), device=device)

        # Windows-Dateisystem-Fallback. dvd+rw-mediainfo spricht das Laufwerk
        # direkt an und kann deshalb schweigen, wo das Medium trotzdem
        # einwandfrei lesbar ist -- etwa bei einem virtuell eingebundenen
        # Abbild. Ohne diesen Zweig meldete RetroDisc dann "kein Medium",
        # obwohl VIDEO_TS lesbar war und das Rippen funktionierte.
        if os.name == "nt":
            return self._windows_volume_info(device, info)

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
