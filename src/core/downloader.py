"""RetroDisc Downloader — yt-dlp Wrapper für YouTube & Mediathek-Downloads."""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import structlog
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from src.models.media import Job, SearchResult
from src.utils.subprocesses import create_hidden_subprocess

log = structlog.get_logger()


class DownloadError(Exception):
    """Fehler beim Download."""
    pass


class Downloader:
    """
    Wrapper für yt-dlp — Downloads von YouTube, Mediatheken und mehr.

    Unterstützt:
    - YouTube (Video & Audio)
    - ARD, ZDF, Arte, 3sat und alle ÖR-Mediatheken
    - Vimeo, SoundCloud, Twitch und hunderte weitere
    - Playlist-Downloads
    - Qualitätswahl

    Beispiel:
        dl = Downloader(output_dir="~/Downloads/RetroDisc")
        result = await dl.download("https://youtube.com/watch?v=xxx", format="mp3")
        results = await dl.search("Tatort München", sources=["ard", "youtube"])
    """

    def __init__(
        self,
        ytdlp_path: Optional[str] = None,
        output_dir: Optional[Path] = None,
        ffmpeg_path: Optional[str] = None,
    ):
        self.ytdlp_path = ytdlp_path or shutil.which("yt-dlp") or "yt-dlp"
        self.output_dir = Path(output_dir) if output_dir else Path.home() / "Downloads" / "RetroDisc"
        self.ffmpeg_path = ffmpeg_path or shutil.which("ffmpeg")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def validate_url(url: str) -> str:
        """Normalisiert und prüft eine Download-URL."""
        clean = (url or "").strip()
        parsed = urlparse(clean)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise DownloadError("Bitte eine gültige HTTP- oder HTTPS-URL eingeben.")
        return clean

    def _build_download_command(
        self,
        url: str,
        format: str,
        output_template: Optional[str],
        extract_audio: bool,
        audio_format: str,
        audio_quality: str,
        subtitles: bool,
        subtitle_langs: str,
    ) -> list[str]:
        """Erstellt den reproduzierbaren yt-dlp-Aufruf."""
        template = output_template or "%(title).180B [%(id)s].%(ext)s"
        output_path = self.output_dir / template
        format_map = {
            "480p": "bestvideo[height<=480]+bestaudio/best[height<=480]",
            "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]",
            "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
            "4k": "bestvideo[height<=2160]+bestaudio/best[height<=2160]",
            "best": "bestvideo+bestaudio/best",
        }

        cmd = [
            self.ytdlp_path,
            "--no-warnings",
            "--newline",
            "--windows-filenames",
            "--print", "after_move:__RETRODISC_FILE__:%(filepath)s",
            "-o", str(output_path),
            "-f", "bestaudio/best" if extract_audio else format_map.get(format, format),
        ]

        if self.ffmpeg_path:
            ffmpeg = Path(self.ffmpeg_path)
            location = ffmpeg.parent if ffmpeg.suffix.lower() == ".exe" else ffmpeg
            cmd.extend(["--ffmpeg-location", str(location)])

        if extract_audio:
            cmd.extend([
                "-x",
                "--audio-format", audio_format,
                "--audio-quality", audio_quality.replace("k", ""),
            ])

        if subtitles:
            cmd.extend([
                "--write-sub",
                "--write-auto-sub",
                "--sub-lang", subtitle_langs,
                "--sub-format", "srt",
            ])

        cmd.extend(["--embed-metadata", "--embed-thumbnail", url])
        return cmd

    async def validate(self) -> str:
        """Prüft ob yt-dlp verfügbar ist und gibt die Version zurück."""
        try:
            proc = await create_hidden_subprocess(
                self.ytdlp_path, "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            version = stdout.decode("utf-8", errors="replace").strip()
            log.info("yt-dlp gefunden", version=version)
            return version
        except FileNotFoundError:
            raise DownloadError(
                f"yt-dlp nicht gefunden. Installieren: pip install yt-dlp"
            )

    async def download(
        self,
        url: str,
        format: str = "best",
        output_template: Optional[str] = None,
        extract_audio: bool = False,
        audio_format: str = "mp3",
        audio_quality: str = "320k",
        subtitles: bool = False,
        subtitle_langs: str = "de,en",
        job: Optional[Job] = None,
    ) -> Path:
        """
        Lädt ein Video oder Audio von einer URL herunter.

        Args:
            url: Video-URL
            format: Qualität ("best", "bestvideo+bestaudio", "720p", "1080p", "480p")
            output_template: Dateiname-Template (yt-dlp Syntax)
            extract_audio: Nur Audio extrahieren
            audio_format: Audio-Format bei extract_audio ("mp3", "flac", "wav")
            audio_quality: Audio-Qualität ("320k", "192k", "128k")
            subtitles: Untertitel mitladen
            subtitle_langs: Untertitel-Sprachen
            job: Job-Objekt für Progress-Updates

        Returns:
            Pfad zur heruntergeladenen Datei
        """
        url = self.validate_url(url)
        before = {
            path.resolve(): (path.stat().st_mtime_ns, path.stat().st_size)
            for path in self.output_dir.iterdir()
            if path.is_file()
        }
        cmd = self._build_download_command(
            url=url,
            format=format,
            output_template=output_template,
            extract_audio=extract_audio,
            audio_format=audio_format,
            audio_quality=audio_quality,
            subtitles=subtitles,
            subtitle_langs=subtitle_langs,
        )

        log.info("Download gestartet", url=url, format=format)

        proc = await create_hidden_subprocess(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        if job:
            job._process = proc

        final_path = None
        output_lines: list[str] = []
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            line_str = line.decode("utf-8", errors="replace").strip()
            output_lines.append(line_str)
            if len(output_lines) > 100:
                output_lines.pop(0)

            # Progress parsen
            if job:
                progress_match = re.search(r"(\d+\.?\d*)%", line_str)
                if progress_match:
                    progress = float(progress_match.group(1))
                    speed_match = re.search(r"at\s+(\S+)", line_str)
                    speed = speed_match.group(1) if speed_match else ""
                    job.update_progress(progress, f"Download: {speed}")

            # Von --print after_move ausgegebener endgültiger Dateiname.
            if line_str.startswith("__RETRODISC_FILE__:"):
                final_path = Path(line_str.split(":", 1)[1].strip())

        await proc.wait()
        if job:
            job._process = None

        if proc.returncode != 0:
            details = "\n".join(output_lines)[-1200:]
            raise DownloadError(f"Download fehlgeschlagen: {details}")

        # Wenn wir den finalen Pfad nicht aus dem Output bekommen haben,
        # suche die neueste Datei im Output-Ordner
        if final_path is None or not final_path.exists():
            files = []
            for path in self.output_dir.iterdir():
                if not path.is_file() or path.suffix.lower() in {".part", ".ytdl", ".tmp"}:
                    continue
                signature = (path.stat().st_mtime_ns, path.stat().st_size)
                if before.get(path.resolve()) != signature:
                    files.append(path)
            files.sort(key=lambda f: f.stat().st_mtime_ns, reverse=True)
            if files:
                final_path = files[0]
            else:
                raise DownloadError("Download-Datei nicht gefunden")

        log.info("Download abgeschlossen", path=str(final_path))
        return final_path

    async def search_youtube(
        self,
        query: str,
        max_results: int = 10,
    ) -> list[SearchResult]:
        """Durchsucht YouTube nach Videos."""
        cmd = [
            self.ytdlp_path,
            f"ytsearch{max_results}:{query}",
            "--dump-json",
            "--flat-playlist",
            "--no-warnings",
        ]

        proc = await create_hidden_subprocess(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()

        results = []
        for line in stdout.decode("utf-8", errors="replace").strip().split("\n"):
            if not line:
                continue
            try:
                data = json.loads(line)
                results.append(SearchResult(
                    title=data.get("title", "Unbekannt"),
                    url=data.get("url") or f"https://youtube.com/watch?v={data.get('id', '')}",
                    source="youtube",
                    duration_seconds=data.get("duration"),
                    thumbnail_url=data.get("thumbnail"),
                    description=data.get("description", "")[:200],
                    channel=data.get("channel") or data.get("uploader"),
                ))
            except json.JSONDecodeError:
                continue

        log.info("YouTube-Suche", query=query, results=len(results))
        return results

    async def search_mediathek(
        self,
        query: str,
        sources: Optional[list[str]] = None,
        max_results: int = 20,
    ) -> list[SearchResult]:
        """
        Durchsucht die ÖR-Mediatheken via MediathekViewWeb API.

        Args:
            query: Suchbegriff
            sources: Filter auf bestimmte Sender (z.B. ["ard", "zdf", "arte"])
            max_results: Maximale Ergebnisse
        """
        import httpx

        api_url = "https://mediathekviewweb.de/api/query"
        payload = {
            "queries": [
                {"fields": ["title", "topic"], "query": query}
            ],
            "sortBy": "timestamp",
            "sortOrder": "desc",
            "size": max_results,
        }

        # Sender-Filter
        if sources:
            channel_map = {
                "ard": "ARD", "zdf": "ZDF", "arte": "ARTE",
                "3sat": "3Sat", "phoenix": "PHOENIX",
                "br": "BR", "ndr": "NDR", "wdr": "WDR",
                "hr": "HR", "mdr": "MDR", "swr": "SWR",
                "rbb": "RBB", "sr": "SR", "kika": "KiKA",
            }
            channels = [channel_map.get(s.lower(), s) for s in sources]
            payload["queries"].append({
                "fields": ["channel"],
                "query": " ".join(channels),
            })

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(api_url, json=payload, timeout=10.0)
                resp.raise_for_status()
                data = resp.json()

            results = []
            for item in data.get("result", {}).get("results", []):
                # Beste URL wählen (HD > Normal > Klein)
                url = item.get("url_video_hd") or item.get("url_video") or item.get("url_video_low", "")
                quality = "HD" if item.get("url_video_hd") else "SD"

                results.append(SearchResult(
                    title=item.get("title", ""),
                    url=url,
                    source=item.get("channel", "").lower(),
                    duration_seconds=item.get("duration"),
                    description=item.get("description", "")[:200],
                    published_at=item.get("timestamp"),
                    quality=quality,
                    channel=item.get("channel"),
                ))

            log.info("Mediathek-Suche", query=query, results=len(results))
            return results

        except Exception as e:
            log.error("Mediathek-Suche fehlgeschlagen", error=str(e))
            return []

    async def search_all(
        self,
        query: str,
        include_youtube: bool = True,
        include_mediathek: bool = True,
        mediathek_sources: Optional[list[str]] = None,
        max_results_per_source: int = 10,
    ) -> list[SearchResult]:
        """
        Durchsucht alle Quellen gleichzeitig.

        Returns:
            Kombinierte und nach Relevanz sortierte Ergebnisse
        """
        tasks = []

        if include_youtube:
            tasks.append(self.search_youtube(query, max_results_per_source))
        if include_mediathek:
            tasks.append(self.search_mediathek(query, mediathek_sources, max_results_per_source))

        all_results = []
        for coro in asyncio.as_completed(tasks):
            try:
                results = await coro
                all_results.extend(results)
            except Exception as e:
                log.warning("Suche teilweise fehlgeschlagen", error=str(e))

        log.info("Gesamtsuche", query=query, total_results=len(all_results))
        return all_results
