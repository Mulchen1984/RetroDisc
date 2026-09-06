"""MediaDownloader - yt-dlp-Aufruf, Fortschritt, Fehlerbehandlung.

Steuert den vorhandenen ``src.core.downloader.Downloader``, statt yt-dlp ein
zweites Mal anzubinden. Damit gelten hier unveraendert: das private
Arbeitsverzeichnis je Download, das atomare Veroeffentlichen, das
Zusammenhalten von Medium und Begleitdateien und die cp1252-Absicherung.

Neu ist allein die Reihenfolge: **erst den Titel ermitteln, dann die Mappe
anlegen, dann hineinladen.** Nur so heisst der Ordner nach dem Medium und
nicht nach einer Job-Id, und ``original.<ext>`` traegt die Endung, die yt-dlp
tatsaechlich geliefert hat.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Optional

import structlog

from src.core.downloader import DownloadError, Downloader
from src.services.media_ai.workspace import (
    ORIGINAL_STEM,
    MediaWorkspace,
    create_workspace,
)
from src.utils.subprocesses import (
    create_hidden_subprocess,
    decode_console_output,
    terminate_process,
)

log = structlog.get_logger()

#: Ein Metadatenabruf ist ein einzelner HTTP-Zugriff. Laenger als das darf er
#: nicht haengen, sonst steht der Auftrag ohne Rueckmeldung.
PROBE_TIMEOUT_SECONDS = 60


class MediaDownloadError(Exception):
    """Der Import ist gescheitert - mit einem Text fuer den Nutzer."""


class MediaDownloader:
    """Laedt ein Medium in eine eigene Arbeitsmappe."""

    def __init__(self, ytdlp_path: str, ffmpeg_path: Optional[str] = None):
        self.ytdlp_path = ytdlp_path
        self.ffmpeg_path = ffmpeg_path

    # ── Schritt 1: Wer ist das? ───────────────────────────────────────
    async def probe(self, url: str) -> dict[str, Any]:
        """Liest Titel und Eckdaten, ohne etwas herunterzuladen."""
        url = Downloader.validate_url(url)
        cmd = [self.ytdlp_path, "--dump-single-json", "--no-warnings",
               "--skip-download", "--no-playlist", url]
        proc = None
        try:
            proc = await create_hidden_subprocess(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=PROBE_TIMEOUT_SECONDS)
        except asyncio.TimeoutError as exc:
            if proc is not None:
                await terminate_process(proc)
            raise MediaDownloadError(
                "Die Quelle hat nicht geantwortet. Bitte die URL pruefen oder "
                "es spaeter erneut versuchen.") from exc
        except FileNotFoundError as exc:
            raise MediaDownloadError(
                f"yt-dlp wurde nicht gefunden: {self.ytdlp_path}. "
                "Den Pfad in den Einstellungen pruefen.") from exc

        if proc.returncode != 0:
            detail = decode_console_output(stderr or b"").strip().splitlines()
            raise MediaDownloadError(
                "Die Quelle konnte nicht gelesen werden. "
                + (detail[-1] if detail else "Unbekannter Fehler von yt-dlp."))
        try:
            data = json.loads(decode_console_output(stdout or b"") or "{}")
        except ValueError as exc:
            raise MediaDownloadError(
                "Die Antwort der Quelle war unlesbar.") from exc

        return {
            "title": (data.get("title") or "").strip() or "Import",
            "id": str(data.get("id") or ""),
            "duration": data.get("duration"),
            "uploader": (data.get("uploader") or data.get("channel") or ""),
            "extractor": data.get("extractor_key") or data.get("extractor") or "",
        }

    # ── Schritt 2: Mappe anlegen ──────────────────────────────────────
    def prepare_workspace(self, base_dir: Path, title: str) -> MediaWorkspace:
        return create_workspace(base_dir, title)

    # ── Schritt 3: Hineinladen ────────────────────────────────────────
    async def fetch(
        self,
        url: str,
        workspace: MediaWorkspace,
        quality: str = "best",
        job: Optional[Any] = None,
    ) -> Path:
        """Laedt das Medium als ``original.<ext>`` in die Mappe.

        Der eigentliche Download geht durch den bestehenden ``Downloader``,
        dessen Ausgabeordner hier die Mappe selbst ist. ``output_template``
        legt den Namen fest; die Endung bestimmt yt-dlp.
        """
        downloader = Downloader(
            ytdlp_path=self.ytdlp_path,
            output_dir=workspace.root,
            ffmpeg_path=self.ffmpeg_path,
        )
        try:
            result = await downloader.download(
                url=url,
                format=quality,
                output_template=f"{ORIGINAL_STEM}.%(ext)s",
                job=job,
            )
        except DownloadError as exc:
            # Der Rohtext von yt-dlp gehoert ins Log, nicht in die Oberflaeche.
            log.error("Download fehlgeschlagen", url=url, error=str(exc))
            raise MediaDownloadError(_friendly_download_error(str(exc))) from exc

        if result is None or not Path(result).is_file():
            raise MediaDownloadError(
                "Der Download hat keine Datei hinterlassen.")
        log.info("Medium geladen", path=str(result))
        return Path(result)


def _friendly_download_error(raw: str) -> str:
    """Uebersetzt die haeufigsten yt-dlp-Fehler in einen Satz fuer den Nutzer.

    Der Rohtext bleibt im Log. Ein Endanwender kann mit 1200 Zeichen
    yt-dlp-Ausgabe nichts anfangen; mit "Video ist privat" schon.
    """
    lowered = raw.lower()
    known = [
        ("http error 403", "Die Quelle hat den Zugriff verweigert (403). "
                           "Haeufig hilft ein Update von yt-dlp."),
        ("http error 404", "Die Quelle wurde nicht gefunden (404). "
                           "Ist der Link noch gueltig?"),
        ("private video", "Das Video ist privat und kann nicht geladen werden."),
        ("members-only", "Das Video ist nur fuer Mitglieder verfuegbar."),
        ("age", "Die Quelle verlangt eine Altersbestaetigung."),
        ("unsupported url", "Diese Adresse wird nicht unterstuetzt."),
        ("unable to download webpage", "Die Quelle war nicht erreichbar. "
                                       "Besteht eine Internetverbindung?"),
        ("no space left", "Auf dem Zieldatentraeger ist kein Platz mehr."),
        ("sign in", "Die Quelle verlangt eine Anmeldung."),
    ]
    for needle, message in known:
        if needle in lowered:
            return message
    return ("Der Download ist fehlgeschlagen. Einzelheiten stehen im "
            "Protokoll (Einstellungen -> Logordner oeffnen).")
