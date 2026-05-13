"""RetroDisc Watch Folder — Automatische Verarbeitung neuer Dateien.

Überwacht Ordner auf neue Dateien und verarbeitet sie automatisch
mit vordefinierten Regeln (z.B. alle neuen Videos → DVD brennen).
"""

from __future__ import annotations

import asyncio
import structlog
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = structlog.get_logger()


@dataclass
class WatchRule:
    """Regel für die automatische Verarbeitung."""
    name: str
    extensions: set[str]           # z.B. {".mp4", ".mkv"}
    action: str                    # "convert", "burn_dvd", "extract_audio"
    preset: Optional[str] = None   # Konvertierungs-Preset
    enabled: bool = True


class WatchFolder:
    """
    Überwacht Ordner und verarbeitet neue Dateien automatisch.

    Beispiel:
        watcher = WatchFolder(
            folder="/home/marco/Watch",
            rules=[WatchRule("Videos → DVD", {".mp4",".mkv"}, "burn_dvd")]
        )
        await watcher.start()
    """

    def __init__(
        self,
        folder: Path | str,
        rules: Optional[list[WatchRule]] = None,
        pipeline=None,
    ):
        self.folder = Path(folder)
        self.rules = rules or []
        self.pipeline = pipeline
        self._known_files: set[Path] = set()
        self._running = False
        self._poll_interval = 3.0  # Sekunden

    async def start(self) -> None:
        """Startet die Ordner-Überwachung."""
        self.folder.mkdir(parents=True, exist_ok=True)
        self._running = True

        # Bestehende Dateien merken (nicht verarbeiten)
        self._known_files = {
            f for f in self.folder.iterdir() if f.is_file()
        }

        log.info("Watch Folder gestartet",
                 folder=str(self.folder),
                 rules=len(self.rules),
                 known_files=len(self._known_files))

        while self._running:
            await self._check_new_files()
            await asyncio.sleep(self._poll_interval)

    async def stop(self) -> None:
        self._running = False
        log.info("Watch Folder gestoppt")

    async def _check_new_files(self) -> None:
        """Prüft auf neue Dateien."""
        try:
            current = {f for f in self.folder.iterdir() if f.is_file()}
            new_files = current - self._known_files

            for file in new_files:
                log.info("Neue Datei erkannt", file=file.name)
                await self._process_file(file)
                self._known_files.add(file)

        except Exception as e:
            log.error("Watch-Folder Fehler", error=str(e))

    async def _process_file(self, file: Path) -> None:
        """Verarbeitet eine neue Datei gemäß passender Regeln."""
        ext = file.suffix.lower()

        for rule in self.rules:
            if not rule.enabled:
                continue
            if ext not in rule.extensions:
                continue

            log.info("Regel angewendet",
                     file=file.name,
                     rule=rule.name,
                     action=rule.action)

            if self.pipeline:
                from src.models.media import Job, JobType
                action_map = {
                    "convert": JobType.CONVERT,
                    "burn_dvd": JobType.BURN_DVD,
                    "extract_audio": JobType.CONVERT,
                }
                job_type = action_map.get(rule.action, JobType.CONVERT)
                job = Job(
                    job_type=job_type,
                    input_files=[file],
                    params={
                        "preset": rule.preset,
                        "display_name": f"Auto: {file.name} [{rule.name}]",
                    }
                )
                await self.pipeline.submit(job)
            break
