"""Die Arbeitsmappe eines importierten Mediums.

Eine Mappe je Titel, mit festen Dateinamen. Wer wissen will, was zu einem
Import gehoert, sieht in genau einen Ordner:

    <download_dir>/<Titel>/
        original.<ext>      unveraendert wie geladen
        video.<ext>         Videospur, ohne Neukodierung
        audio.wav           PCM, 16 kHz, mono - fuer Whisper und Voice-Cloning
        transcript.txt      Transkription, sobald erzeugt
        metadata.json       Herkunft, Zustand, erzeugte Artefakte
        frames/             Einzelbilder, sobald extrahiert

``metadata.json`` ist dabei mehr als Beiwerk: es ist der Zustand des Imports
und ueberlebt den Neustart. Die Oberflaeche liest daraus, welche Schritte
schon gelaufen sind und welche noch angeboten werden.

**Zur Ablage:** Die Mappen liegen unter dem bereits konfigurierten
``download_dir`` (``<media_root>/Downloads``), nicht unter einem eigenen
``Media/``-Zweig. Ein zweiter Downloadbaum neben dem eingestellten waere
genau der Fehler, den die Ordnerkonsolidierung beseitigt hat - Dateien, die
der Nutzer an der Stelle sucht, an der sie nicht liegen.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import structlog

log = structlog.get_logger()

#: Feste Namen innerhalb einer Mappe. Wer hier etwas ergaenzt, ergaenzt auch
#: ``MediaJob.artefacts`` - sonst weiss die Oberflaeche nichts davon.
ORIGINAL_STEM = "original"
VIDEO_STEM = "video"
AUDIO_NAME = "audio.wav"
TRANSCRIPT_NAME = "transcript.txt"
METADATA_NAME = "metadata.json"
FRAMES_DIRNAME = "frames"

#: Kuerzt lange Titel. Windows begrenzt den Gesamtpfad, und ein
#: YouTube-Titel kann mehrere hundert Zeichen lang sein.
MAX_TITLE_LENGTH = 60


class WorkspaceError(Exception):
    """Eine Arbeitsmappe konnte nicht angelegt oder gelesen werden."""


def safe_title(value: str, fallback: str = "Import") -> str:
    """Macht aus einem Medientitel einen gueltigen Windows-Ordnernamen.

    Windows verbietet ``<>:"/\\|?*`` und Steuerzeichen, mag keine Namen mit
    Punkt oder Leerzeichen am Ende, und kennt reservierte Geraetenamen wie
    ``CON`` oder ``LPT1`` - ein Ordner mit so einem Namen laesst sich nicht
    anlegen. Zeichen ausserhalb von cp1252 bleiben dagegen erhalten: NTFS
    kann sie, und ein japanischer Titel soll japanisch bleiben.
    """
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", (value or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned).strip(" ._")
    cleaned = cleaned[:MAX_TITLE_LENGTH].strip(" ._")
    if not cleaned:
        return fallback
    reserved = {
        "CON", "PRN", "AUX", "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
    if cleaned.upper() in reserved or cleaned.upper().split(".")[0] in reserved:
        return f"{cleaned}_"
    return cleaned


@dataclass
class MediaJob:
    """Der Zustand eines Imports - was schon da ist und was noch fehlt.

    Bewusst **keine** zweite Jobqueue. Die Ausfuehrung bleibt Sache von
    ``src/core/pipeline.Pipeline``; dieses Objekt beschreibt nur, was in der
    Mappe steht, und wird in ``metadata.json`` gehalten. Dadurch weiss die
    Oberflaeche auch nach einem Neustart noch, dass Audio zwar extrahiert,
    aber noch nicht transkribiert wurde.
    """

    url: str = ""
    title: str = ""
    source_id: str = ""
    duration_seconds: Optional[float] = None
    uploader: str = ""
    imported_at: str = ""
    stages: list[str] = field(default_factory=list)
    artefacts: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def record(self, stage: str) -> None:
        if stage not in self.stages:
            self.stages.append(stage)

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "source_id": self.source_id,
            "duration_seconds": self.duration_seconds,
            "uploader": self.uploader,
            "imported_at": self.imported_at,
            "stages": list(self.stages),
            "artefacts": dict(self.artefacts),
            "errors": list(self.errors),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MediaJob":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in (data or {}).items() if k in known})


@dataclass(frozen=True)
class MediaWorkspace:
    """Eine angelegte Mappe. Kennt ihre Pfade, legt nichts von selbst an."""

    root: Path

    # ── Feste Pfade ───────────────────────────────────────────────────
    @property
    def audio(self) -> Path:
        return self.root / AUDIO_NAME

    @property
    def transcript(self) -> Path:
        return self.root / TRANSCRIPT_NAME

    @property
    def metadata(self) -> Path:
        return self.root / METADATA_NAME

    @property
    def frames(self) -> Path:
        return self.root / FRAMES_DIRNAME

    @property
    def name(self) -> str:
        return self.root.name

    def original(self) -> Optional[Path]:
        """Die geladene Quelldatei; ihre Endung steht erst danach fest."""
        return self._first(ORIGINAL_STEM)

    def video(self) -> Optional[Path]:
        return self._first(VIDEO_STEM)

    def _first(self, stem: str) -> Optional[Path]:
        if not self.root.is_dir():
            return None
        for path in sorted(self.root.glob(f"{stem}.*")):
            if path.is_file() and not path.name.startswith("."):
                return path
        return None

    # ── Zustand ───────────────────────────────────────────────────────
    def load_job(self) -> MediaJob:
        """Liest den Zustand. Eine kaputte Datei blockiert nichts."""
        if not self.metadata.is_file():
            return MediaJob(title=self.name)
        try:
            return MediaJob.from_dict(
                json.loads(self.metadata.read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:
            log.warning("metadata.json nicht lesbar", path=str(self.metadata),
                        error=str(exc))
            return MediaJob(title=self.name)

    def save_job(self, job: MediaJob) -> None:
        """Schreibt den Zustand atomar - wie AppSettings.save."""
        job.artefacts = self.existing_artefacts()
        payload = json.dumps(job.to_dict(), indent=2, ensure_ascii=False)
        temp_path: Optional[Path] = None
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", newline="\n", dir=self.root,
                prefix=f".{METADATA_NAME}.", suffix=".tmp", delete=False,
            ) as handle:
                temp_path = Path(handle.name)
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.metadata)
        except OSError as exc:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
            raise WorkspaceError(
                f"Zustand konnte nicht gespeichert werden: {exc}") from exc

    def existing_artefacts(self) -> dict[str, str]:
        """Was wirklich auf der Platte liegt - nicht, was gemeldet wurde."""
        found: dict[str, str] = {}
        for key, path in (("original", self.original()), ("video", self.video()),
                          ("audio", self.audio), ("transcript", self.transcript)):
            if path is not None and path.is_file() and path.stat().st_size > 0:
                found[key] = str(path)
        if self.frames.is_dir():
            count = sum(1 for _ in self.frames.glob("*.png"))
            if count:
                found["frames"] = str(self.frames)
                found["frame_count"] = str(count)
        return found

    def describe(self) -> dict[str, Any]:
        """Ein Eintrag fuer die Oberflaeche."""
        job = self.load_job()
        data = job.to_dict()
        data.update(name=self.name, root=str(self.root),
                    artefacts=self.existing_artefacts())
        return data


def create_workspace(base_dir: Path, title: str) -> MediaWorkspace:
    """Legt eine neue Mappe an, ohne eine vorhandene zu berueren.

    Ein zweiter Import desselben Titels bekommt ``" (1)"``, ``" (2)"`` - nach
    derselben Regel wie jede andere Ausgabe. ``mkdir`` ohne ``exist_ok`` ist
    dabei der atomare Teil: zwei gleichzeitige Importe koennen sich nicht auf
    dieselbe Mappe einigen.
    """
    base_dir = Path(base_dir)
    base_dir.mkdir(parents=True, exist_ok=True)
    stem = safe_title(title)
    for counter in range(10_000):
        candidate = base_dir / (stem if not counter else f"{stem} ({counter})")
        try:
            candidate.mkdir()
        except FileExistsError:
            continue
        except OSError as exc:
            raise WorkspaceError(
                f"Arbeitsmappe konnte nicht angelegt werden: {candidate} ({exc})"
            ) from exc
        log.info("Arbeitsmappe angelegt", path=str(candidate))
        return MediaWorkspace(candidate)
    raise WorkspaceError(f"Zu viele Mappen mit dem Namen {stem}")


def open_workspace(root: Path) -> MediaWorkspace:
    """Oeffnet eine vorhandene Mappe."""
    root = Path(root)
    if not root.is_dir():
        raise WorkspaceError(f"Arbeitsmappe nicht gefunden: {root}")
    return MediaWorkspace(root)


def list_workspaces(base_dir: Path) -> list[MediaWorkspace]:
    """Alle Mappen unter *base_dir*, neueste zuerst.

    Als Mappe gilt nur ein Ordner mit ``metadata.json``. Damit bleiben die
    Auftragsordner der klassischen Downloadstrecke und die temporaeren
    ``.retrodisc-dl-*`` unberuehrt.
    """
    base_dir = Path(base_dir)
    if not base_dir.is_dir():
        return []
    found = [
        MediaWorkspace(entry)
        for entry in base_dir.iterdir()
        if entry.is_dir() and (entry / METADATA_NAME).is_file()
    ]
    return sorted(found, key=lambda w: w.metadata.stat().st_mtime, reverse=True)


def now_stamp() -> str:
    return datetime.now().isoformat(timespec="seconds")
