"""RetroDisc Tool Bootstrap - Automatischer Download externer Tools.

Beim ersten Start prüft RetroDisc ob FFmpeg, yt-dlp etc. vorhanden sind.
Falls nicht, werden sie automatisch heruntergeladen und ins tools/-Verzeichnis
neben der EXE gespeichert.

Alle Tool-URLs zeigen auf offizielle Quellen:
- FFmpeg: github.com/BtbN/FFmpeg-Builds (Windows-Builds)
- yt-dlp: github.com/yt-dlp/yt-dlp (offizielle EXE)
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import struct
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Optional
import urllib.request
import urllib.error

log = logging.getLogger("retrodisc.bootstrap")

# ── Tool-Definitionen ─────────────────────────────────────────────────

TOOLS = {
    "ffmpeg": {
        "exe": "ffmpeg.exe",
        "url_win64": (
            "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
            "ffmpeg-master-latest-win64-gpl.zip"
        ),
        "zip_path": "ffmpeg-master-latest-win64-gpl/bin/ffmpeg.exe",
        "test_args": ["-version"],
        "description": "FFmpeg (Video/Audio Konvertierung)",
        "size_mb": 85,
    },
    "ffprobe": {
        "exe": "ffprobe.exe",
        "url_win64": (
            "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
            "ffmpeg-master-latest-win64-gpl.zip"
        ),
        "zip_path": "ffmpeg-master-latest-win64-gpl/bin/ffprobe.exe",
        "test_args": ["-version"],
        "description": "FFprobe (Medienanalyse)",
        "size_mb": 0,  # Kommt aus dem selben ZIP wie FFmpeg
    },
    "ytdlp": {
        "exe": "yt-dlp.exe",
        "url_win64": (
            "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
        ),
        "zip_path": None,  # Direktdownload, kein ZIP
        "test_args": ["--version"],
        "description": "yt-dlp (YouTube & Mediathek Downloads)",
        "size_mb": 25,
    },
}


class ToolBootstrap:
    """
    Prüft und lädt externe Tools beim ersten Start.

    Beispiel:
        bootstrap = ToolBootstrap(tools_dir=Path("tools"))
        missing = bootstrap.check_missing()
        if missing:
            bootstrap.download_missing_sync(missing)
        paths = bootstrap.get_tool_paths()
    """

    def __init__(self, tools_dir: Path):
        self.tools_dir = Path(tools_dir)
        self.tools_dir.mkdir(parents=True, exist_ok=True)

    def check_missing(self) -> list[str]:
        """Gibt Namen der fehlenden Tools zurück."""
        missing = []

        for name, info in TOOLS.items():
            exe_path = self.tools_dir / info["exe"]

            # Im tools/-Ordner vorhanden?
            if exe_path.exists():
                log.info(f"Tool gefunden: {name}", path=str(exe_path))
                continue

            # Im System-PATH vorhanden?
            system_path = shutil.which(info["exe"].replace(".exe", ""))
            if system_path:
                log.info(f"Tool im PATH: {name}", path=system_path)
                continue

            log.info(f"Tool fehlt: {name}")
            missing.append(name)

        return missing

    def get_tool_paths(self) -> dict[str, Path]:
        """Gibt Pfade zu allen verfügbaren Tools zurück."""
        paths = {}

        for name, info in TOOLS.items():
            # Erst im tools/-Ordner suchen
            local = self.tools_dir / info["exe"]
            if local.exists():
                paths[name] = local
                continue

            # Dann im PATH
            exe_name = info["exe"].replace(".exe", "")
            system = shutil.which(exe_name)
            if system:
                paths[name] = Path(system)

        return paths

    def download_missing_sync(
        self,
        tools: list[str],
        on_progress: Optional[callable] = None,
    ) -> None:
        """
        Lädt fehlende Tools synchron herunter (für Splash-Screen beim Start).

        Args:
            tools: Liste der zu ladenden Tool-Namen
            on_progress: Callback(tool_name, percent, status_text)
        """
        # FFmpeg und FFprobe kommen aus dem selben ZIP
        # -> nur einmal herunterladen
        ffmpeg_zip_needed = (
            "ffmpeg" in tools or "ffprobe" in tools
        )

        if ffmpeg_zip_needed:
            self._download_ffmpeg_bundle(on_progress)
            tools = [t for t in tools if t not in ("ffmpeg", "ffprobe")]

        for tool_name in tools:
            info = TOOLS.get(tool_name)
            if not info:
                continue
            self._download_single(tool_name, info, on_progress)

    def _download_ffmpeg_bundle(self, on_progress=None) -> None:
        """Lädt das FFmpeg-Bundle (ZIP mit ffmpeg.exe + ffprobe.exe)."""
        info = TOOLS["ffmpeg"]
        url = info["url_win64"]
        zip_path = self.tools_dir / "ffmpeg_bundle.zip"

        log.info("Lade FFmpeg-Bundle herunter...", url=url)

        try:
            self._download_file(url, zip_path, "FFmpeg-Bundle", on_progress)

            # Aus ZIP extrahieren
            with zipfile.ZipFile(zip_path) as zf:
                for tool_name in ("ffmpeg", "ffprobe"):
                    t_info = TOOLS[tool_name]
                    zip_member = t_info["zip_path"]
                    target = self.tools_dir / t_info["exe"]

                    if zip_member in zf.namelist():
                        with zf.open(zip_member) as src, open(target, "wb") as dst:
                            shutil.copyfileobj(src, dst)
                        log.info(f"{tool_name}.exe extrahiert", path=str(target))
                    else:
                        log.warning(f"{zip_member} nicht im ZIP gefunden")

        finally:
            zip_path.unlink(missing_ok=True)

    def _download_single(self, name: str, info: dict, on_progress=None) -> None:
        """Lädt ein einzelnes Tool direkt herunter (kein ZIP)."""
        url = info["url_win64"]
        target = self.tools_dir / info["exe"]

        log.info(f"Lade {name} herunter...", url=url)
        self._download_file(url, target, info["description"], on_progress)
        log.info(f"{name} heruntergeladen", path=str(target))

    def _download_file(
        self,
        url: str,
        target: Path,
        label: str,
        on_progress=None,
    ) -> None:
        """Lädt eine Datei mit Fortschrittsanzeige herunter."""
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "RetroDisc/1.0"},
            )
            with urllib.request.urlopen(req, timeout=60) as response:
                total = int(response.headers.get("Content-Length", 0))
                downloaded = 0
                chunk_size = 65536  # 64 KB

                with open(target, "wb") as f:
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)

                        if on_progress and total > 0:
                            percent = (downloaded / total) * 100
                            mb_done = downloaded / 1024 / 1024
                            mb_total = total / 1024 / 1024
                            on_progress(
                                label,
                                percent,
                                f"{mb_done:.1f} / {mb_total:.1f} MB"
                            )

        except urllib.error.URLError as e:
            target.unlink(missing_ok=True)
            raise RuntimeError(f"Download fehlgeschlagen für {label}: {e}")

    def verify_tool(self, name: str) -> bool:
        """Prüft ob ein Tool funktionsfähig ist."""
        info = TOOLS.get(name)
        if not info:
            return False

        exe = self.tools_dir / info["exe"]
        if not exe.exists():
            system = shutil.which(info["exe"].replace(".exe", ""))
            if not system:
                return False
            exe = Path(system)

        try:
            result = subprocess.run(
                [str(exe)] + info["test_args"],
                capture_output=True,
                timeout=10,
            )
            return result.returncode == 0
        except Exception:
            return False

    def get_status_report(self) -> dict:
        """Gibt einen Status-Bericht über alle Tools zurück."""
        report = {}
        paths = self.get_tool_paths()

        for name, info in TOOLS.items():
            if name in paths:
                ok = self.verify_tool(name)
                report[name] = {
                    "available": True,
                    "functional": ok,
                    "path": str(paths[name]),
                    "description": info["description"],
                }
            else:
                report[name] = {
                    "available": False,
                    "functional": False,
                    "path": None,
                    "description": info["description"],
                }

        return report
