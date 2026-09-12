"""
RetroDisc.exe - Single File Launcher
=====================================
Alles in einer EXE:
- Komplettes Python-Backend
- HTML/CSS/JS UI (eingebettet als String)
- Automatischer FFmpeg/yt-dlp Download beim ersten Start
- Kein Installer nötig - einfach doppelklicken

Gebaut mit:  pyinstaller retrodisc_onefile.spec
Ergebnis:    RetroDisc.exe  (~25 MB, standalone)
"""

import sys
import os
import logging
import threading
import tempfile
import json
import struct
import wave
import math
import asyncio
import subprocess
from pathlib import Path
from typing import Optional


# ── Pfad-Setup ────────────────────────────────────────────────────────
if getattr(sys, "frozen", False):
    # Läuft als EXE (PyInstaller --onefile)
    BASE_DIR = Path(sys.executable).parent
    BUNDLE_DIR = Path(sys._MEIPASS)
    sys.path.insert(0, str(BUNDLE_DIR))
else:
    BASE_DIR = Path(__file__).parent
    BUNDLE_DIR = BASE_DIR

# App-Daten ins AppData-Verzeichnis
APPDATA = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "RetroDisc"
APPDATA.mkdir(parents=True, exist_ok=True)
TOOLS_DIR = APPDATA / "tools"
TOOLS_DIR.mkdir(exist_ok=True)
LOG_DIR = APPDATA / "logs"
LOG_DIR.mkdir(exist_ok=True)

# ── Logging ───────────────────────────────────────────────────────────
# Zuerst die Standardstroeme UTF-8-sicher machen. Windows liefert sie mit der
# ANSI-Codepage (cp1252); ein Dateiname mit Emoji oder CJK-Zeichen - bei
# YouTube-Titeln der Normalfall - loest dort sonst schon beim blossen Loggen
# eine UnicodeEncodeError aus und kann bereits fertige Arbeit als Fehler
# erscheinen lassen. Muss vor den Handlern laufen, die die Stroeme einsammeln.
from src.utils.logging_setup import configure_console_encoding, configure_structlog

_STDOUT, _STDERR = configure_console_encoding()
configure_structlog(_STDOUT)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "retrodisc.log", encoding="utf-8"),
        logging.StreamHandler(_STDOUT) if _STDOUT is not None else logging.NullHandler(),
    ],
)
log = logging.getLogger("retrodisc")


# ── HTML UI (eingebettet) ─────────────────────────────────────────────
def get_ui_html() -> str:
    """Lädt die UI-HTML aus dem Bundle oder dem Dateisystem."""
    # Erst im Bundle suchen (PyInstaller)
    for candidate in [
        BUNDLE_DIR / "src" / "ui" / "app.html",
        BASE_DIR / "src" / "ui" / "app.html",
    ]:
        if candidate.exists():
            return candidate.read_text(encoding="utf-8")

    # Fallback: Minimale Fehler-UI
    return """<!DOCTYPE html><html><body style="font-family:Arial;padding:20px;">
    <h2>RetroDisc - UI nicht gefunden</h2>
    <p>src/ui/app.html konnte nicht geladen werden.</p>
    </body></html>"""


# ── Tool Bootstrap ────────────────────────────────────────────────────
def check_tools() -> dict:
    """Prüft verfügbare Tools, gibt Pfade zurück."""
    import shutil
    tools = {}

    if sys.platform == 'darwin' and getattr(sys, 'frozen', False):
        bundled_ytdlp = Path(sys.executable).with_name('yt-dlp')
        if bundled_ytdlp.is_file():tools['ytdlp'] = str(bundled_ytdlp)

    for name, exes in [
        ("ffmpeg",  ["ffmpeg.exe",  "ffmpeg"]),
        ("ffprobe", ["ffprobe.exe", "ffprobe"]),
        ("ytdlp",   ["yt-dlp.exe",  "yt-dlp"]),
    ]:
        if sys.platform == "darwin":
            exes = [exe for exe in exes if not exe.endswith(".exe")]
        # 1. Im Bundle (vendor/ direkt in EXE eingebettet)
        for exe in exes:
            p = BUNDLE_DIR / "vendor" / exe
            if p.exists():
                tools[name] = str(p)
                log.info(f"Tool aus Bundle: {name}")
                break

        if name in tools:
            continue

        # 2. Im AppData tools-Ordner
        for exe in exes:
            p = TOOLS_DIR / exe
            if p.exists():
                tools[name] = str(p)
                log.info(f"Tool aus AppData: {name}")
                break

        if name in tools:
            continue

        # 3. System-PATH
        for exe in exes:
            found = shutil.which(exe)
            if found:
                tools[name] = found
                log.info(f"Tool aus PATH: {name}")
                break

    return tools


def download_tool(name: str, url: str, target: Path, on_progress=None):
    """Lädt ein Tool herunter."""
    import urllib.request
    import zipfile

    log.info(f"Lade {name}...", )

    tmp = target.parent / (target.name + ".tmp")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "RetroDisc/1.0"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            done = 0
            with open(tmp, "wb") as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if on_progress and total:
                        on_progress(name, done / total * 100)

        # ZIP entpacken falls nötig
        if url.endswith(".zip"):
            with zipfile.ZipFile(tmp) as zf:
                # ffmpeg.exe / ffprobe.exe aus dem ZIP holen
                for member in zf.namelist():
                    bn = Path(member).name
                    if bn in ("ffmpeg.exe", "ffprobe.exe"):
                        dest = TOOLS_DIR / bn
                        with zf.open(member) as src, open(dest, "wb") as dst:
                            import shutil as sh
                            sh.copyfileobj(src, dst)
                        log.info(f"Extrahiert: {bn}")
        else:
            tmp.rename(target)
            log.info(f"{name} heruntergeladen: {target}")

    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


# ── Fertig-Sound ──────────────────────────────────────────────────────
def play_completion_sound():
    """Spielt den RetroDisc-Jingle ab."""
    try:
        sr = 44100
        notes = [
            (880, 0.0, 0.18), (1108, 0.14, 0.18),
            (1318, 0.28, 0.18), (1760, 0.42, 0.50),
        ]
        duration = 1.2
        samples = [0.0] * int(sr * duration)

        for freq, start, dur in notes:
            s0 = int(start * sr)
            for i in range(int(dur * sr)):
                if s0 + i >= len(samples):
                    break
                t = i / sr
                val = (
                    math.sin(2 * math.pi * freq * t) * 0.7
                    + math.sin(2 * math.pi * freq * 2 * t) * 0.2
                )
                env = min(t / 0.02, 1.0) * max(0, 1.0 - (t / dur) ** 1.5) * 0.3
                samples[s0 + i] += val * env

        mx = max(abs(s) for s in samples) or 1.0
        ints = [int(max(-1, min(1, s / mx)) * 32000) for s in samples]

        wav_path = APPDATA / "complete.wav"
        with wave.open(str(wav_path), "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(struct.pack(f"<{len(ints)}h", *ints))

        # Abspielen
        try:
            import sounddevice as sd
            import soundfile as sf
            data, rate = sf.read(str(wav_path))
            sd.play(data, rate)
        except ImportError:
            try:
                import winsound
                winsound.PlaySound(str(wav_path),
                                   winsound.SND_FILENAME | winsound.SND_ASYNC)
            except Exception:
                pass
    except Exception as e:
        log.debug(f"Sound-Fehler: {e}")


# ── Python ↔ JavaScript Bridge ────────────────────────────────────────
class RetroDiscBridge:
    """
    Alle public Methoden sind aus JavaScript aufrufbar:
        window.pywebview.api.convert_file(...)
        window.pywebview.api.download_url(...)
        etc.
    """

    def __init__(self, window=None):
        self.window = window
        self._splash_transition_started = False
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=lambda: self._loop.run_forever(), daemon=True
        )
        self._thread.start()

        # Settings laden
        from src.config.settings import AppSettings
        self.settings = AppSettings.load()
        tool_paths = check_tools()

        if "ffmpeg" in tool_paths and self.settings.tools.ffmpeg == "ffmpeg":
            self.settings.tools.ffmpeg = tool_paths["ffmpeg"]
        if "ffprobe" in tool_paths and self.settings.tools.ffprobe == "ffprobe":
            self.settings.tools.ffprobe = tool_paths["ffprobe"]
        if "ytdlp" in tool_paths and self.settings.tools.ytdlp == "yt-dlp":
            self.settings.tools.ytdlp = tool_paths["ytdlp"]

        try:
            self.settings.ensure_directories()
        except (OSError, ValueError) as exc:
            log.warning('Zielverzeichnis ungültig; bitte Einstellungen korrigieren: %s', exc)

        # Core-Module
        from src.core.ffmpeg import FFmpeg
        from src.core.pipeline import Pipeline
        from src.core.downloader import Downloader
        from src.services.converter import Converter
        from src.services.search import MediaSearch
        from src.core.disc import DiscTools
        from src.services.dvd_workflow import DVDWorkflow
        from src.services.library import MediaLibrary
        from src.services.disc_analyzer import DiscAnalyzer
        from src.services.capacity_planner import CapacityPlanner
        from src.services.transcode.probe import MediaProbeService

        self.ffmpeg = FFmpeg(
            self.settings.tools.ffmpeg,
            self.settings.tools.ffprobe,
        )
        self.pipeline = Pipeline(
            max_concurrent=self.settings.conversion.max_concurrent_jobs,
            play_sound=False,  # Wir spielen selbst
        )
        self.pipeline.on_job_complete = self._on_complete
        self.pipeline.on_job_failed = self._on_failed
        self.downloader = Downloader(
            ytdlp_path=self.settings.tools.ytdlp,
            output_dir=self.settings.directories.download_dir,
            ffmpeg_path=self.settings.tools.ffmpeg,
        )
        self.converter = Converter(
            ffmpeg=self.ffmpeg,
            output_dir=self.settings.directories.output_dir,
        )
        self.search = MediaSearch(downloader=self.downloader)
        dvd_bin = BUNDLE_DIR / "vendor" / "dvdtools"
        disc_paths = self._resolve_disc_tool_paths(self.settings.tools)
        self.disc = DiscTools(
            dvdauthor_path=disc_paths["dvdauthor"],
            mkisofs_path=disc_paths["mkisofs"],
            growisofs_path=disc_paths["growisofs"],
            cdrecord_path=self.settings.tools.cdrecord,
            mediainfo_path=str(dvd_bin / "dvd+rw-mediainfo.exe") if (dvd_bin / "dvd+rw-mediainfo.exe").is_file() else None,
        )
        self.dvd_workflow = DVDWorkflow(
            ffmpeg=self.ffmpeg,
            disc_tools=self.disc,
            temp_dir=self.settings.directories.temp_dir,
        )
        from src.services.bluray_workflow import BlurayWorkflow
        self.bluray_workflow = BlurayWorkflow(
            ffmpeg=self.ffmpeg,
            disc_tools=self.disc,
            temp_dir=self.settings.directories.temp_dir,
        )
        self.disc_analyzer = DiscAnalyzer(
            disc_tools=self.disc,
            probe=MediaProbeService(self.settings.tools.ffprobe),
        )
        self.capacity_planner = CapacityPlanner()
        from src.services.player import PlayerService
        self.player = PlayerService()
        self._player_mount = None   # aktiver ISO-Mount (falls die Quelle ein ISO war)
        self.library = MediaLibrary(ffmpeg=self.ffmpeg)
        self.library.open()
        self._watch = None
        # Nicht mehr hier blockierend erzeugen: die Konstruktion (inkl. SQLite-Connect)
        # muss auf self._loop laufen, damit spätere Zugriffe (submit/rows/...), die
        # über self._async() ebenfalls auf self._loop laufen, dieselbe Connection aus
        # demselben Thread benutzen. Bis zum ersten echten Bedarf lazy verzögert, statt
        # __init__ synchron auf den Hintergrund-Thread warten zu lassen (der in manchen
        # Testfixtures bewusst nie gestartet wird).
        self.conversion_queue = None

        log.info("Bridge initialisiert")

    async def _ensure_conversion_queue(self):
        if self.conversion_queue is None:
            from src.services.pipeline.conversion_queue import ConversionQueue
            self.conversion_queue = ConversionQueue(self.library.db_path.parent / 'pipeline.db', self.converter,
                                   self._emit, self._on_complete,
                                   self.settings.conversion.max_concurrent_jobs)
        return self.conversion_queue

    async def _submit_conversion_job(self, job):
        queue = await self._ensure_conversion_queue()
        return await queue.submit(job)

    def _async(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def _emit(self, event: str, data: dict):
        if self.window:
            try:
                payload = json.dumps({"event": event, "data": data})
                self.window.evaluate_js(
                    f"window.onPythonEvent && window.onPythonEvent({payload})"
                )
            except Exception as exc:
                # The UI is an observer. A closed/reloading WebView must never
                # turn an otherwise successful backend operation into a failure.
                log.warning("UI-Ereignis %s konnte nicht zugestellt werden: %s", event, exc)

    def _on_complete(self, job):
        try:
            self.library.record_job_outputs(job, excluded_dirs=[self.settings.directories.temp_dir, self.library.thumb_dir])
        except Exception as exc:
            log.warning("Recent-Media-Verlauf konnte nicht gespeichert werden: %s", exc)
        self._emit("job_done", {
            "id": job.id,
            "name": job.params.get("display_name", job.id),
            "type": job.job_type.value,
            "output": str(job.output_path) if job.output_path else None,
            "elapsed": round(job.elapsed_seconds, 1),
            **({"subtitle_paths":job.params["subtitle_paths"]} if "subtitle_paths" in job.params else {}),
            **({"output_paths": job.params["output_paths"]} if "output_paths" in job.params else {}),
            **({"archive": job.params["archive"]} if "archive" in job.params else {}),
            **({"batch_summary": job.params["batch_summary"]} if "batch_summary" in job.params else {}),
        })
        if self.settings.sound.play_on_complete:
            threading.Thread(target=play_completion_sound, daemon=True).start()

    def _on_failed(self, job):
        self._emit("job_failed", {
            "id": job.id,
            "name": job.params.get("display_name", job.id),
            "error": job.error_message,
        })

    def _wire_job_progress(self, job) -> None:
        """Leitet echte Fortschrittswerte aus FFmpeg/yt-dlp an die UI weiter."""
        job.on_progress = lambda progress, status: self._emit("job_progress", {
            "id": job.id,
            "name": job.params.get("display_name", job.id),
            "progress": progress,
            "status": status,
        })

    # ── Window sizing (CloneCD style: compact home, larger work flows) ──
    def resize_compact(self) -> bool:
        """Resize the window to the compact launcher/home size."""
        try:
            if self.window:
                self.window.resize(640, 460)
            return True
        except Exception as e:
            log.warning(f"resize_compact failed: {e}")
            return False

    def resize_work(self) -> bool:
        """Resize the window to the larger work-flow size."""
        try:
            if self.window:
                self.window.resize(1180, 760)
            return True
        except Exception as e:
            log.warning(f"resize_work failed: {e}")
            return False

    # ── Datei-Dialog ──────────────────────────────────────────────────
    def open_file_dialog(self) -> str:
        if self.window:
            result = self.window.create_file_dialog(
                10,  # OPEN_DIALOG
                allow_multiple=True,
                file_types=(
                    "Mediendateien (*.mp4;*.mkv;*.avi;*.mov;*.mp3;*.flac;*.wav;*.iso;*.vob;*.jpg;*.jpeg;*.png;*.webp)",
                    "Alle Dateien (*.*)",
                )
            )
            if result:
                files = []
                errors = []
                for path in result:
                    info = json.loads(self.probe_file(path))
                    if "error" in info:
                        errors.append({"path": path, "error": info["error"]})
                    else:
                        files.append(info)
                if files:
                    return json.dumps({"files": files, "errors": errors})
                if errors:
                    return json.dumps({"error": errors[0]["error"], "errors": errors})
        return json.dumps({"error": "Abgebrochen"})

    def open_tool_dialog(self) -> str:
        """Selects one executable for an external-tool setting."""
        if self.window:
            try:
                result = self.window.create_file_dialog(
                    10, allow_multiple=False,
                    file_types=("Programme (*.exe)", "Alle Dateien (*.*)"),
                )
                if result:
                    selected = result[0] if isinstance(result, (list, tuple)) else result
                    return json.dumps({"path": str(selected)})
            except Exception as e:
                return json.dumps({"error": str(e)})
        return json.dumps({"error": "Abgebrochen"})

    def probe_file(self, path: str) -> str:
        future = self._async(self.ffmpeg.probe(path))
        try:
            m = future.result(timeout=15)
            return json.dumps({
                "path": str(m.path),
                "name": m.path.name,
                "type": m.media_type.value,
                "duration_formatted": m.duration_formatted,
                "duration_fmt": m.duration_formatted,
                "duration_seconds": m.duration_seconds,
                "size_formatted": m.file_size_formatted,
                "size_fmt": m.file_size_formatted,
                "size_bytes": m.file_size_bytes,
                "resolution": m.resolution,
                "video_codec": m.video_streams[0].codec if m.video_streams else None,
                "audio_codec": m.audio_streams[0].codec if m.audio_streams else None,
                "video": [{"codec": v.codec, "width": v.width, "height": v.height,
                           "fps": v.fps, "bitrate": v.bitrate} for v in m.video_streams],
                "audio": [{"codec": a.codec, "channels": a.channels,
                           "sample_rate": a.sample_rate, "bitrate": a.bitrate,
                           "language": a.language} for a in m.audio_streams],
                "subs": [{"codec": s.codec, "lang": s.language}
                         for s in m.subtitle_streams],
            })
        except Exception as e:
            return json.dumps({"error": str(e)})

    # ── Konvertierung ─────────────────────────────────────────────────
    def convert_file(self, input_path: str, preset_name: str,
                     output_path: str = None, overwrite: bool = False, encoder: str = "auto") -> str:
        from src.config.presets import get_preset
        from src.models.media import Job, JobType

        try:
            preset = get_preset(preset_name)
        except ValueError as e:
            return json.dumps({"error": str(e)})

        source = Path(input_path)
        if not source.exists() or not source.is_file():
            return json.dumps({"error": f"Quelldatei nicht gefunden: {source}"})

        job = Job(
            job_type=JobType.CONVERT,
            input_files=[source],
            output_path=Path(output_path) if output_path else None,
            preset=preset,
            params={"display_name": f"{source.name} -> {preset.display_name}",
                    "overwrite": bool(overwrite), "encoder": encoder, "preset_name": preset_name},
        )
        async def _handler(j):
            result = await self.converter.convert_file(
                j.input_files[0], j.preset, j.output_path, job=j,
                overwrite=j.params["overwrite"],
                hwaccel=j.params["encoder"] if sys.platform == "darwin" else None,
            )
            j.output_path = result

        return self._submit_job(job, _handler)

    def get_recent_media(self) -> str:
        from src.services.dvd_workflow import DVDWorkflow
        rows = self.library.recent_outputs()
        for row in rows:
            row["can_convert"] = row["type"] in ("video", "audio")
            row["can_burn"] = DVDWorkflow.supports_recent_source(Path(row["path"]))
        return json.dumps(rows)

    def get_encoder_options(self) -> str:
        if sys.platform != "darwin":
            return json.dumps([])
        return json.dumps([
            {"id": "auto", "name": "Automatisch – Apple Hardware bevorzugt"},
            {"id": "videotoolbox", "name": "Apple Hardware – schnell"},
            {"id": "cpu", "name": "CPU – maximale Qualitätskontrolle"},
        ])

    def get_presets(self, category: str = None) -> str:
        from src.config.presets import ALL_PRESETS, get_presets_by_category
        presets = ALL_PRESETS if not category else get_presets_by_category(category)
        return json.dumps([{
            "id": p.name, "name": p.display_name,
            "category": p.category, "container": p.container,
            "media_type": "video" if p.video_codec else "audio",
        } for p in presets])

    # ── Download ──────────────────────────────────────────────────────
    def download_url(self, url: str, format: str = "best",
                     audio_only: bool = False, subtitles: bool = False) -> str:
        from src.models.media import Job, JobType

        # Backwards compatibility: older UI called (url, audio_only, format).
        if isinstance(format, bool):
            audio_only, format = format, "best"

        try:
            url = self.downloader.validate_url(url)
        except Exception as e:
            return json.dumps({"error": str(e)})

        audio_format = format if audio_only and format in {"mp3", "flac", "wav"} else "mp3"
        quality = "best" if audio_only else (format or "best")
        job = Job(
            job_type=JobType.DOWNLOAD,
            params={"url": url, "audio_only": bool(audio_only), "format": quality,
                    "audio_format": audio_format,
                    "subtitles": bool(subtitles),
                    "display_name": f"Download: {url[:50]}"},
        )
        async def _handler(j):
            downloader = self.downloader
            if sys.platform == "darwin" and j.params["audio_only"]:
                from src.core.downloader import Downloader
                downloader = Downloader(
                    ytdlp_path=self.downloader.ytdlp_path,
                    ffmpeg_path=self.downloader.ffmpeg_path,
                    output_dir=self.settings.directories.audio_dir,
                )
            result = await downloader.download(
                url=j.params["url"],
                format=j.params["format"],
                extract_audio=j.params["audio_only"],
                audio_format=j.params["audio_format"],
                subtitles=j.params["subtitles"],
                job=j,
            )
            j.output_path = result
            if sys.platform == "darwin":
                j.params["output_paths"] = [str(result)]
                if not j.params["audio_only"]:
                    audio = self.settings.directories.audio_dir / f"{result.stem[:120]}_{j.id}.mp3"
                    audio = await self.ffmpeg.extract_audio(result, audio, job=j)
                    j.params["output_paths"].append(str(audio))

        return self._submit_job(job, _handler)

    # ── Suche ─────────────────────────────────────────────────────────
    def search_media(self, query: str, sources: str = "[]", max_results: int = 15) -> str:
        future = self._async(
            self.search.search(query, max_results=max_results)
        )
        try:
            results = future.result(timeout=20)
            return json.dumps([{
                "title": r.title, "url": r.url,
                "source": r.source, "duration": r.duration_seconds,
                "quality": r.quality, "channel": r.channel,
            } for r in results])
        except Exception as e:
            return json.dumps({"error": str(e)})

    # ── Queue ─────────────────────────────────────────────────────────
    def get_queue(self) -> str:
        jobs = []
        for j in list(self.pipeline._queue) + self.pipeline._running:
            jobs.append({"id": j.id,
                         "name": j.params.get("display_name", j.id),
                         "state": j.state.value,
                         "progress": j.progress,
                         "output": str(j.output_path) if j.output_path else None,
                         "awaiting_copy_medium": j.params.get("awaiting_copy_medium", False),
                         **({"output_paths": j.params["output_paths"]} if "output_paths" in j.params else {})})
        for j in self.pipeline.completed_jobs[-20:]:
            jobs.append({"id": j.id,
                         "name": j.params.get("display_name", j.id),
                         "state": j.state.value,
                         "progress": j.progress,
                         "output": str(j.output_path) if j.output_path else None,
                         **({"output_paths": j.params["output_paths"]} if "output_paths" in j.params else {})})
        if getattr(self, 'conversion_queue', None):
            jobs.extend(self._async(self.conversion_queue.rows()).result(timeout=5))
        return json.dumps(jobs)

    # ── Settings ──────────────────────────────────────────────────────
    def get_platform_info(self) -> str:
        from src.utils.platform_ui import platform_info
        return json.dumps(platform_info())

    def get_path_status(self) -> str:
        rows = []
        for name, path in self.settings.directories:
            try:
                rows.append({'name':name, **self.settings.validate_directory(path)})
            except (OSError, ValueError) as exc:
                rows.append({'name':name, 'path':str(path), 'error':str(exc)})
        internal = {'config':self.settings._default_config_path(), 'logs':LOG_DIR,
                    'database / recent media':self.library.db_path,
                    'thumbnails':self.library.thumb_dir,
                    'director projects':self.library.db_path.parent / 'projects',
                    'preview':self.settings.directories.temp_dir / 'preview'}
        rows.extend({'name':name,'path':str(path),'exists':path.exists(),
                     'usage':'Bei Bedarf erstellt' if not path.exists() else 'Vorhanden'}
                    for name,path in internal.items())
        return json.dumps(rows)

    def get_settings(self) -> str:
        return self.settings.model_dump_json()

    @staticmethod
    def _deep_merge_settings(current: dict, updates: dict) -> dict:
        """Merge UI partial settings without resetting hidden preferences."""
        merged = dict(current)
        for key, value in updates.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = RetroDiscBridge._deep_merge_settings(merged[key], value)
            else:
                merged[key] = value
        return merged

    @staticmethod
    def _resolve_disc_tool_paths(tools) -> dict[str, str]:
        """Resolve DVD tools for this run; keep extraction paths out of settings."""
        resolved = {}
        dvd_bin = BUNDLE_DIR / "vendor" / "dvdtools"
        for name in ("dvdauthor", "mkisofs", "growisofs"):
            configured = getattr(tools, name)
            path = Path(configured)
            bundled = dvd_bin / f"{name}.exe"
            # Migrate paths saved by older launchers, including an extraction
            # directory that still exists while another instance is running.
            legacy_bundle = (
                path.parent.name.lower() == "dvdtools"
                and path.parent.parent.name.lower() == "vendor"
                and path.parent.parent.parent.name.lower().startswith("_mei")
            )
            if path == bundled or legacy_bundle:
                configured = name
                setattr(tools, name, configured)
            resolved[name] = (
                str(bundled) if configured == name and bundled.is_file() else configured
            )
        return resolved

    def _apply_runtime_settings(self) -> None:
        """Apply persisted paths/directories to already-created services."""
        tools = self.settings.tools
        directories = self.settings.directories
        self.ffmpeg.ffmpeg_path = tools.ffmpeg
        self.ffmpeg.ffprobe_path = tools.ffprobe
        self.converter.output_dir = directories.output_dir
        self.dvd_workflow.temp_dir = directories.temp_dir
        self.downloader.ytdlp_path = tools.ytdlp
        self.downloader.ffmpeg_path = tools.ffmpeg
        self.downloader.output_dir = directories.download_dir
        for name, path in self._resolve_disc_tool_paths(tools).items():
            setattr(self.disc, name, path)
        self.disc.cdrecord = tools.cdrecord
        self.pipeline.max_concurrent = self.settings.conversion.max_concurrent_jobs

    def save_settings(self, data: str) -> str:
        try:
            from src.config.settings import AppSettings
            updates = json.loads(data)
            if not isinstance(updates, dict):
                raise ValueError("Einstellungen müssen ein JSON-Objekt sein.")
            merged = self._deep_merge_settings(
                self.settings.model_dump(mode="json"), updates
            )
            new_settings = AppSettings.model_validate(merged)
            self._resolve_disc_tool_paths(new_settings.tools)
            new_settings.ensure_directories()
            new_settings.save()
            self.settings = new_settings
            self._apply_runtime_settings()
            return json.dumps({"ok": True})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def get_tool_status(self) -> str:
        import shutil
        status = {}
        runtime = {'ffmpeg':(getattr(self,'ffmpeg',None),'ffmpeg_path'),
                   'ffprobe':(getattr(self,'ffmpeg',None),'ffprobe_path'),
                   'ytdlp':(getattr(self,'downloader',None),'ytdlp_path')}
        for name, configured in self.settings.tools:
            service, attribute = runtime.get(name,(getattr(self,'disc',None),name))
            configured = getattr(service,attribute,configured)
            resolved = shutil.which(configured)
            status[name] = {'available': bool(resolved), 'path':resolved or configured}
        return json.dumps(status)

    def diagnostics(self) -> str:
        """Honest capability dashboard (Mission 12). Real detection only, no fake availability."""
        groups = {"Werkzeuge": [], "KI & Sprache": [], "Encoder": [], "Restaurierung": []}

        def add(cat, name, status, detail=""):
            groups[cat].append({"name": name, "status": status, "detail": detail})

        try:
            tools = json.loads(self.get_tool_status())
            for key, label in (("ffmpeg", "FFmpeg"), ("ffprobe", "FFprobe"), ("ytdlp", "yt-dlp")):
                info = tools.get(key, {})
                add("Werkzeuge", label, "available" if info.get("available") else "unavailable",
                    info.get("path", ""))
        except Exception as exc:
            add("Werkzeuge", "FFmpeg/yt-dlp", "unavailable", str(exc))

        # Ollama, Whisper, TTS aus dem Director-Capability-Aggregat.
        try:
            dc = self._async(self._director_service().capabilities()).result(timeout=10)
            models = dc.get("llm_models", [])
            add("KI & Sprache", "Ollama (LLM)", "available" if models else "unavailable",
                (", ".join(models[:4]) + ("…" if len(models) > 4 else "")) if models else "kein lokales Modell")
            whisper = dc.get("whisper", {})
            wstatus = {"available": "available", "package_missing": "unavailable",
                       "model_missing": "model_missing", "not_configured": "optional"}.get(whisper.get("status"), "unavailable")
            add("KI & Sprache", "Whisper (ASR)", wstatus, whisper.get("note", ""))
            tts = dc.get("tts", {})
            add("KI & Sprache", "TTS (Systemstimmen)", "available" if tts.get("available") else "unavailable",
                tts.get("engine", "") if tts.get("available") else "keine lokale TTS")
        except Exception as exc:
            add("KI & Sprache", "Ollama/Whisper/TTS", "unavailable", str(exc))

        try:
            sc = self._async(self._smart_editor_service().capabilities()).result(timeout=10)
            hw = sc.get("hardware_encode", [])
            add("Encoder", "Hardware-Encoder", "available" if hw else "optional",
                ", ".join(hw) if hw else "nur CPU (libx264/libx265)")
            add("Encoder", "libass (Untertitel einbrennen)",
                "available" if sc.get("captions") else "unavailable",
                "" if sc.get("captions") else "FFmpeg ohne libass – SRT-Export bleibt möglich")
        except Exception as exc:
            add("Encoder", "Encoder/libass", "unavailable", str(exc))

        try:
            rc = self._async(self._restoration_service().capabilities()).result(timeout=10)
            level = rc.get("stabilization", {}).get("level", "none")
            add("Restaurierung", "libvidstab (Stabilisierung)",
                "available" if level == "advanced" else "optional" if level == "basic" else "unavailable",
                {"advanced": "vidstab", "basic": "nur deshake (basic)", "none": "kein Stabilisierungsfilter"}.get(level, ""))
            for key, info in rc.get("providers", {}).items():
                add("Restaurierung", {"qtgmc": "QTGMC/VapourSynth", "realesrgan": "Real-ESRGAN",
                    "basicvsr": "BasicVSR++", "rvrt": "RVRT/VRT", "rife": "RIFE",
                    "vhs_decode": "vhs-decode"}.get(key, key),
                    "optional", info.get("note", "nicht integriert"))
        except Exception as exc:
            add("Restaurierung", "Provider", "unavailable", str(exc))

        return json.dumps({"groups": [{"category": c, "items": items} for c, items in groups.items()]})

    def play_sound(self) -> str:
        threading.Thread(target=play_completion_sound, daemon=True).start()
        return json.dumps({"ok": True})


    # ── Ordner-Dialog ─────────────────────────────────────────────────
    def open_folder_dialog(self) -> str:
        if self.window:
            try:
                import webview as wv
                result = self.window.create_file_dialog(wv.FOLDER_DIALOG)
                if result and result[0]:
                    return json.dumps({"folder": result[0]})
            except Exception as e:
                return json.dumps({"error": str(e)})
        return json.dumps({"error": "Abgebrochen"})

    def open_folder_for_batch(self) -> str:
        return self.open_folder_dialog()

    def open_output_folder(self, output_path: str = "") -> str:
        try:
            from src.utils.reveal import reveal_output
            reveal_output(Path(output_path) if output_path else self.settings.directories.output_dir)
            return json.dumps({"ok": True})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def clear_completed(self) -> str:
        try:
            self.pipeline.clear_completed()
            return json.dumps({"ok": True})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def detect_burners(self) -> str:
        try:
            import json as _json, platform
            from src.utils.subprocesses import run_powershell_hidden
            if platform.system() != "Windows":
                return json.dumps({"drives": [], "note": "Laufwerks-Erkennung läuft aktuell nur unter Windows."})
            ps = "Get-CimInstance Win32_CDROMDrive | ForEach-Object { [PSCustomObject]@{ Name=$_.Name; Drive=$_.Drive; MediaLoaded=$_.MediaLoaded; MediaType=$_.MediaType; DeviceID=$_.DeviceID; PNPDeviceID=$_.PNPDeviceID } } | ConvertTo-Json -Compress"
            out = run_powershell_hidden(ps, timeout=15)
            if out.returncode != 0:
                return json.dumps({"drives": [], "error": (out.stderr or "PowerShell-Laufwerkserkennung fehlgeschlagen").strip()})
            raw = (out.stdout or "").strip()
            if not raw:
                return json.dumps({"drives": [], "note": "Kein optisches Laufwerk gefunden."})
            data = _json.loads(raw)
            if isinstance(data, dict): data = [data]
            drives = []
            for d in data:
                name = d.get("Name") or "Optisches Laufwerk"
                letter = d.get("Drive")
                upper_name = name.upper()
                caps = ["CD", "DVD"]
                if any(token in upper_name for token in ("BD", "BLU-RAY", "BLURAY")):
                    caps.append("Blu-ray")
                if any(token in upper_name for token in ("RW", "WRITER")) or "WRITER" in str(d.get("MediaType") or "").upper():
                    caps.append("Brennen")
                media = self._async(self.disc.get_disc_info(letter)).result(timeout=25) if letter else {"present": False}
                drives.append({
                    "id": d.get("PNPDeviceID") or d.get("DeviceID") or letter,
                    "device_id": d.get("DeviceID"), "name": name, "letter": letter,
                    "media_loaded": bool(d.get("MediaLoaded")),
                    "media_type": d.get("MediaType"), "caps": caps, "media": media,
                })
            return json.dumps({"drives": drives})
        except subprocess.TimeoutExpired:
            return json.dumps({
                "drives": [],
                "error": "Zeitüberschreitung bei der Laufwerkserkennung.",
            })
        except Exception as e:
            return json.dumps({"drives": [], "error": str(e)})

    def get_disc_info(self, device: str) -> str:
        if not device:
            return json.dumps({"error": "Kein optisches Laufwerk ausgewählt."})
        try:
            info = self._async(self.disc.get_disc_info(device)).result(timeout=25)
            if isinstance(info, dict) and info.get("present"):
                import shutil
                from src.services.booktype import describe_media
                info = describe_media(info, tool_available=bool(shutil.which("dvd+rw-booktype")))
            return json.dumps(info)
        except Exception as exc:
            return json.dumps({"error": str(exc), "device": device})

    def list_target_media(self) -> str:
        """Zentrale Zielmedien-Registry für die UI (Brennen: Zielmedium-Auswahl).

        Fast eine reine Lesefunktion - gibt die bereits vorhandene
        ``TARGET_MEDIA``-Registry (``src/config/target_media.py``,
        P0-Kapazitätsplanung) als JSON weiter. "Custom" ist bewusst nicht
        enthalten (keine feste Kapazität) und wird von der UI separat
        angeboten.

        ``authoring_available`` meldet, ob RetroDisc die *Struktur* eines
        Ziels heute tatsächlich bauen kann - unabhängig von Laufwerk/Medium
        (das prüft ``check_target_medium`` separat). Für DVD_VIDEO war das
        schon immer der Fall (dvdauthor); für BDMV ist es das erst seit dem
        neuen ``src/services/bluray_authoring.py``-Pfad, und hängt nur an
        FFmpeg (kein zusätzliches externes Werkzeug nötig) - deshalb bleibt
        diese Methode ohne ``self`` aufrufbar (siehe
        ``test_list_target_media_bridge_method_matches_the_registry``).
        """
        import shutil
        from src.config.target_media import AuthoringFormat, TARGET_MEDIA
        ffmpeg_available = shutil.which("ffmpeg") is not None
        return json.dumps([
            {
                "id": m.id,
                "display_name": m.display_name,
                "authoring_format": m.authoring_format.value,
                "nominal_capacity_bytes": m.nominal_capacity_bytes,
                "usable_capacity_bytes": m.usable_capacity_bytes,
                "is_physical_bluray": m.is_physical_bluray,
                "requires_bdxl": m.requires_bdxl,
                "authoring_available": True if m.authoring_format is AuthoringFormat.DVD_VIDEO else ffmpeg_available,
            }
            for m in TARGET_MEDIA.values()
        ])

    def inspect_drive(self, device: str) -> str:
        """Report optical-drive capabilities (detection only)."""
        if not device:
            return json.dumps({"error": "Kein optisches Laufwerk ausgewählt."})
        try:
            caps = self._async(self.disc.inspect_drive(device)).result(timeout=25)
            return json.dumps(caps.to_dict())
        except Exception as exc:
            return json.dumps({"error": str(exc), "device": device})

    def get_disc_content(self, device: str) -> str:
        """Vollständiges DiscContent-Modell (Titel/Kapitel/Spuren/Main-Movie).

        Reine Analyse, keine Auswahl-UI: liefert die Grundlage, auf der eine
        spätere Titel-/Kapitel-/Audio-/Untertitelauswahl aufbauen kann.
        """
        from src.models.disc_content import DiscContentError
        if not device:
            return json.dumps({"error": "Kein optisches Laufwerk ausgewählt."})
        try:
            content = self._async(self.disc_analyzer.analyze(device)).result(timeout=60)
            return json.dumps(content.to_dict())
        except DiscContentError as exc:
            return json.dumps({"error": str(exc), "device": device})
        except Exception as exc:
            return json.dumps({"error": str(exc), "device": device})

    def plan_capacity(self, device: str, target_medium_id: str,
                      selected_title_indices_json: str = "[]",
                      selected_audio_indices_json: str = "[]",
                      selected_subtitle_indices_json: str = "[]",
                      custom_target_bytes: Optional[int] = None,
                      custom_authoring_format: str = "") -> str:
        """Analysiert die eingelegte Disc und plant VOR jeder Kodierung, ob und
        wie der ausgewählte Inhalt auf das Zielmedium passt.

        Leere Auswahllisten bedeuten "alle Titel/Spuren der Disc" - solange es
        noch keine eigene Auswahl-UI gibt (siehe P0_CAPACITY_PLANNING.md).
        """
        from src.config.target_media import AuthoringFormat
        from src.models.disc_content import DiscContentError
        if not device:
            return json.dumps({"error": "Kein optisches Laufwerk ausgewählt."})
        try:
            content = self._async(self.disc_analyzer.analyze(device)).result(timeout=60)
            title_indices = json.loads(selected_title_indices_json) or None
            audio_indices = json.loads(selected_audio_indices_json) or None
            subtitle_indices = json.loads(selected_subtitle_indices_json) or None

            titles = [t for t in content.titles if title_indices is None or t.index in title_indices]
            selected_audio = None
            if audio_indices is not None:
                selected_audio = [a for t in titles for a in t.audio_tracks if a.index in audio_indices]
            selected_subtitles = None
            if subtitle_indices is not None:
                selected_subtitles = [s for t in titles for s in t.subtitle_tracks if s.index in subtitle_indices]

            fmt = AuthoringFormat(custom_authoring_format) if custom_authoring_format else None
            plan = self.capacity_planner.plan(
                titles=titles, target_medium_id=target_medium_id,
                selected_audio_tracks=selected_audio, selected_subtitle_tracks=selected_subtitles,
                custom_target_bytes=custom_target_bytes, custom_authoring_format=fmt,
            )
            return json.dumps(plan.to_dict())
        except DiscContentError as exc:
            return json.dumps({"error": str(exc), "device": device})
        except Exception as exc:
            return json.dumps({"error": str(exc), "device": device})

    # ── Gemeinsame Queue-Hilfe ─────────────────────────────────────────
    def _submit_job(self, job, handler) -> str:
        """Stellt Job und dessen unverwechselbaren Handler sicher in die Queue."""
        if 'preset_name' in job.params:
            try:
                self._async(self._submit_conversion_job(job)).result(timeout=5)
                self._emit('job_queued', {'id': job.id, 'name': job.params.get('display_name', job.id), 'type': job.job_type.value})
                return json.dumps({'job_id': job.id, 'status': 'queued'})
            except Exception as exc:
                return json.dumps({'error': str(exc)})
        self._wire_job_progress(job)
        try:
            self._async(self.pipeline.submit(job, handler=handler)).result(timeout=5)
        except Exception as e:
            return json.dumps({"error": f"Job konnte nicht eingereiht werden: {e}"})
        if not self.pipeline._is_running:
            self._async(self.pipeline.start())
        self._emit("job_queued", {
            "id": job.id,
            "name": job.params.get("display_name", job.id),
            "type": job.job_type.value,
        })
        return json.dumps({"job_id": job.id, "status": "queued"})

    # ── DVD / ISO ──────────────────────────────────────────────────────
    def create_dvd(self, paths_json: str, title: str = "RetroDisc DVD",
                   standard: str = "PAL", aspect: str = "16:9",
                   burn: bool = False, device: str = "",
                   speed: Optional[int] = None, verify: Optional[bool] = None,
                   eject: Optional[bool] = None, book_type: str = "automatic") -> str:
        from src.models.media import Job, JobType
        try:
            raw = json.loads(paths_json) if isinstance(paths_json, str) else paths_json
            paths = [Path(p) for p in raw]
        except Exception:
            return json.dumps({"error": "Ungültige Pfad-Liste"})
        missing = [str(p) for p in paths if not p.is_file()]
        if not paths:
            return json.dumps({"error": "Keine Quelldateien ausgewählt."})
        if missing:
            return json.dumps({"error": f"Datei nicht gefunden: {missing[0]}"})

        job = Job(
            job_type=JobType.BURN_DVD,
            input_files=paths,
            params={
                "title": (title or "RetroDisc DVD").strip(),
                "standard": standard.strip().upper(),
                "aspect": aspect,
                "burn_to_disc": bool(burn),
                "only_iso": not bool(burn),
                "device": device or self.settings.burn.default_device,
                "burn_speed": int(speed) if speed not in (None, "") else self.settings.burn.default_speed,
                "verify_after_burn": self.settings.burn.verify_after_burn if verify is None else bool(verify),
                "eject_after_burn": self.settings.burn.eject_after_burn if eject is None else bool(eject),
                "book_type": book_type or "automatic",
                "display_name": f"{title or 'RetroDisc DVD'} -> {'Disc' if burn else 'ISO'}",
            },
        )

        async def _handler(j):
            from src.services.dvd_workflow import DVDProject
            project = DVDProject(
                title=j.params["title"],
                input_files=j.input_files,
                output_dir=self.settings.directories.output_dir,
                standard=j.params["standard"],
                aspect=j.params["aspect"],
                burn_to_disc=j.params["burn_to_disc"],
                only_iso=j.params["only_iso"],
                disc_device=j.params["device"] or self.settings.burn.default_device,
                burn_speed=j.params["burn_speed"],
                verify_after_burn=j.params["verify_after_burn"],
                eject_after_burn=j.params["eject_after_burn"],
                book_type=j.params["book_type"],
            )
            j.output_path = await self.dvd_workflow.run(project, job=j)

        return self._submit_job(job, _handler)

    def create_bluray(self, paths_json: str, title: str = "RetroDisc Blu-ray",
                      target_medium_id: str = "bd25",
                      burn: bool = False, device: str = "",
                      speed: Optional[int] = None, verify: Optional[bool] = None,
                      eject: Optional[bool] = None) -> str:
        """Erstellt eine echte BDMV-Struktur (siehe ``src.services.bluray_authoring``)
        und optional ein Blu-ray-ISO/eine gebrannte Disc daraus.

        Gilt für jedes ``AuthoringFormat.BDMV``-Zielmedium (physisches BD-25/
        50/BDXL-100/128 UND BDMV-auf-DVD-5/9) - nur das physische Zielmedium
        beim Brennen unterscheidet sich, siehe ``BlurayWorkflow``-Moduldoku.

        Prüft VOR dem Einreihen (Verteidigung in der Tiefe, nicht nur die
        UI-Anzeige) über ``inspect_drive`` + ``target_medium_capability_issue``,
        ob Laufwerk/Backend das gewählte Zielmedium tatsächlich unterstützen,
        falls gebrannt werden soll - keine Unterstützung vortäuschen.
        """
        from src.config.target_media import get_target_medium, target_medium_capability_issue
        from src.models.media import Job, JobType
        try:
            raw = json.loads(paths_json) if isinstance(paths_json, str) else paths_json
            paths = [Path(p) for p in raw]
        except Exception:
            return json.dumps({"error": "Ungültige Pfad-Liste"})
        missing = [str(p) for p in paths if not p.is_file()]
        if not paths:
            return json.dumps({"error": "Keine Quelldateien ausgewählt."})
        if missing:
            return json.dumps({"error": f"Datei nicht gefunden: {missing[0]}"})
        try:
            medium = get_target_medium(target_medium_id)
        except ValueError as exc:
            return json.dumps({"error": str(exc)})

        burn = bool(burn)
        resolved_device = device or self.settings.burn.default_device
        if burn:
            try:
                caps = self._async(self.disc.inspect_drive(resolved_device)).result(timeout=25)
            except Exception as exc:
                return json.dumps({"error": f"Laufwerksfähigkeiten konnten nicht geprüft werden: {exc}"})
            issue = target_medium_capability_issue(medium, caps)
            if issue:
                return json.dumps({"error": issue})

        job = Job(
            job_type=JobType.BURN_BLURAY,
            input_files=paths,
            params={
                "title": (title or "RetroDisc Blu-ray").strip(),
                "target_medium_id": medium.id,
                "burn_to_disc": burn,
                "only_iso": not burn,
                "device": resolved_device,
                "burn_speed": int(speed) if speed not in (None, "") else self.settings.burn.default_speed,
                "verify_after_burn": self.settings.burn.verify_after_burn if verify is None else bool(verify),
                "eject_after_burn": self.settings.burn.eject_after_burn if eject is None else bool(eject),
                "display_name": f"{title or 'RetroDisc Blu-ray'} -> {'Disc' if burn else 'ISO'}",
            },
        )

        async def _handler(j):
            from src.services.bluray_workflow import BlurayProject
            project = BlurayProject(
                title=j.params["title"],
                input_files=j.input_files,
                output_dir=self.settings.directories.output_dir,
                target_medium_id=j.params["target_medium_id"],
                burn_to_disc=j.params["burn_to_disc"],
                only_iso=j.params["only_iso"],
                disc_device=j.params["device"] or self.settings.burn.default_device,
                burn_speed=j.params["burn_speed"],
                verify_after_burn=j.params["verify_after_burn"],
                eject_after_burn=j.params["eject_after_burn"],
            )
            j.output_path = await self.bluray_workflow.run(project, job=j)

        return self._submit_job(job, _handler)

    def check_target_medium(self, device: str, target_medium_id: str) -> str:
        """Prüft ein Zielmedium gegen die tatsächlichen Laufwerksfähigkeiten.

        Reine Lesefunktion für die UI (Aktivieren/Deaktivieren einer
        Zielmedium-Option mit Begründung) - dieselbe Prüfung, die
        ``create_bluray`` vor dem Brennen ohnehin serverseitig durchsetzt.
        """
        from src.config.target_media import get_target_medium, target_medium_capability_issue
        try:
            medium = get_target_medium(target_medium_id)
        except ValueError as exc:
            return json.dumps({"available": False, "reason": str(exc)})
        caps = None
        if device:
            try:
                caps = self._async(self.disc.inspect_drive(device)).result(timeout=25)
            except Exception as exc:
                return json.dumps({"available": False, "reason": f"Laufwerksfähigkeiten konnten nicht geprüft werden: {exc}"})
        issue = target_medium_capability_issue(medium, caps)
        return json.dumps({"available": issue is None, "reason": issue})

    def burn_existing_iso(self, iso_path: str, device: str = "", disc_type: str = "bluray",
                          target_medium_id: str = "", speed: Optional[int] = None,
                          verify: Optional[bool] = None, eject: Optional[bool] = None) -> str:
        """Brennt eine bereits vorhandene, gültige ISO-Datei direkt - ohne
        erneutes Video-Encoding oder BDMV-/DVD-Authoring.

        Wichtiger, eigenständiger Anwendungsfall: der Nutzer hat schon ein
        fertiges Blu-ray-ISO (aus einem früheren RetroDisc-Lauf oder einem
        anderen Werkzeug) und will es nur noch brennen. Läuft über denselben
        kanonischen ``DiscTools.burn_iso`` wie jeder andere Brennweg in
        diesem Projekt - keine zweite Brennlogik.
        """
        from src.models.media import DiscType, Job, JobType
        from src.config.target_media import get_target_medium, target_medium_capability_issue
        path = Path(iso_path)
        if not path.is_file():
            return json.dumps({"error": f"ISO-Datei nicht gefunden: {iso_path}"})
        try:
            resolved_disc_type = DiscType(disc_type.strip().lower())
        except ValueError:
            return json.dumps({"error": f"Unbekannter Disc-Typ: {disc_type!r}"})
        resolved_device = device or self.settings.burn.default_device
        if not resolved_device:
            return json.dumps({"error": "Kein Ziellaufwerk ausgewählt."})

        if target_medium_id:
            try:
                medium = get_target_medium(target_medium_id)
            except ValueError as exc:
                return json.dumps({"error": str(exc)})
            try:
                caps = self._async(self.disc.inspect_drive(resolved_device)).result(timeout=25)
            except Exception as exc:
                return json.dumps({"error": f"Laufwerksfähigkeiten konnten nicht geprüft werden: {exc}"})
            issue = target_medium_capability_issue(medium, caps)
            if issue:
                return json.dumps({"error": issue})

        job = Job(
            job_type=JobType.BURN_BLURAY if resolved_disc_type == DiscType.BLURAY else JobType.BURN_DVD,
            output_path=path,
            params={
                "iso_path": str(path), "device": resolved_device, "disc_type": resolved_disc_type.value,
                "burn_speed": int(speed) if speed not in (None, "") else self.settings.burn.default_speed,
                "verify_after_burn": self.settings.burn.verify_after_burn if verify is None else bool(verify),
                "eject_after_burn": self.settings.burn.eject_after_burn if eject is None else bool(eject),
                "display_name": f"{path.name} -> Disc",
            },
        )

        async def _handler(j):
            from src.core.disc import DiscError
            from src.services.booktype import BookType
            from src.services.dvd_workflow import DVDWorkflow
            from src.services.verify import FAIL as VERIFY_FAIL
            outcome = await self.disc.burn_iso(
                Path(j.params["iso_path"]), device=j.params["device"], speed=j.params["burn_speed"],
                verify=j.params["verify_after_burn"], disc_type=resolved_disc_type, job=j,
                book_type=BookType.NATIVE,
            )
            j.params["burn_outcome"] = outcome.to_dict()
            if outcome.verify.status == VERIFY_FAIL:
                raise DiscError(f"Verifikation fehlgeschlagen: {outcome.verify.message}")
            if j.params["eject_after_burn"]:
                await DVDWorkflow()._eject(j.params["device"])

        return self._submit_job(job, _handler)

    def copy_disc(self, source: str, target: str, mode: str = "image",
                 book_type: str = "automatic") -> str:
        """Kopiert eine Disc ueber ein Abbild: einlesen, dann brennen.

        Setzt bewusst nur vorhandene Bausteine zusammen - ``DiscRipper`` fuer
        das Einlesen und ``DiscTools.burn_iso`` fuer das Schreiben. Weder der
        Rip- noch der Brennpfad wird dafuer veraendert.

        **Was das ist und was nicht.** ``DiscRipper.rip(..., "iso")`` liest das
        *gemountete Dateisystem* der Quelle und erzeugt daraus mit ``mkisofs``
        ein neues Abbild (siehe ``src/services/ripper.py``). Das Ergebnis ist
        eine **Dateisystem-Kopie**, kein sektorweiser 1:1-Klon: Strukturen
        ausserhalb des Dateisystems werden nicht uebernommen. Fuer eine
        ungeschuetzte DVD-Video-Disc bleibt ``VIDEO_TS`` vollstaendig erhalten
        und das Ergebnis ist abspielbar; als forensische Kopie taugt es nicht.

        ``mode="image"`` ist der einzige heute umgesetzte Weg; ein einzelnes
        Laufwerk genuegt dafuer. ``mode="onthefly"`` wird ausdruecklich
        abgewiesen: dafuer muesste direkt von Laufwerk zu Laufwerk gestreamt
        werden, und diesen Pfad gibt es im Backend nicht. Er wird nicht
        stillschweigend durch den Abbild-Weg ersetzt - das waere ein falsches
        Versprechen an den Nutzer.
        """
        from src.models.media import Job, JobType

        mode = (mode or "image").lower().strip()
        if mode not in {"image", "onthefly"}:
            return json.dumps({"error": f"Unbekannter Kopiermodus: {mode}"})
        if not source:
            return json.dumps({"error": "Kein Quelllaufwerk ausgewählt."})
        if not target:
            return json.dumps({"error": "Kein Ziellaufwerk ausgewählt."})
        if mode == "onthefly":
            if source == target:
                return json.dumps({
                    "error": "On-the-fly benötigt zwei verschiedene Laufwerke. "
                             "Quelle und Ziel sind dasselbe Laufwerk."
                })
            # Nicht stillschweigend auf den Abbild-Weg ausweichen: der Nutzer
            # hat ausdruecklich etwas anderes gewaehlt.
            return json.dumps({
                "error": "On-the-fly-Kopieren ist in dieser Version noch nicht "
                         "verfügbar. Bitte 'Über Abbild' wählen: die Disc wird "
                         "dabei zuerst eingelesen und danach gebrannt."
            })
        # Ueber ein Abbild ist auch ein einzelnes Laufwerk zulaessig: erst
        # einlesen, dann den Rohling im selben Laufwerk brennen.

        safe = source.replace(":", "").replace("\\", "").replace("/", "") or "disc"
        job = Job(
            job_type=JobType.RIP_DVD,
            params={"source": source, "target": target, "mode": mode,
                    "book_type": book_type or "automatic",
                    "display_name": f"Disc kopieren: {source} -> {target}"},
        )

        job.output_path = self.settings.directories.output_dir / f"Disc_{safe}_Copy_{job.id}.iso"

        async def _handler(j):
            from src.services.ripper import DiscRipper

            # Reserve exclusively at execution time, including against files
            # created after submission. Never truncate a pre-existing image.
            requested = j.output_path
            requested.parent.mkdir(parents=True, exist_ok=True)
            suffix = 0
            while True:
                candidate = requested if not suffix else requested.with_stem(f"{requested.stem}_{suffix}")
                try:
                    with candidate.open("xb"):
                        pass
                    break
                except FileExistsError:
                    suffix += 1
            j.output_path = candidate
            ripper = DiscRipper(self.ffmpeg, self.disc)
            try:
                image_path = await ripper.rip(
                    j.params["source"], j.output_path, "iso", job=j)
            except BaseException:
                candidate.unlink(missing_ok=True)
                raise
            j.output_path = image_path
            # Compare Windows drive aliases such as D:, d:/ and D:\.
            if source.strip().rstrip("\\/").casefold() == target.strip().rstrip("\\/").casefold():
                j._copy_media_ready = asyncio.Event()
                j.params["awaiting_copy_medium"] = True
                try:
                    j.update_progress(50, "Quelldisc entfernen, leeren Rohling einlegen und in der Queue bestätigen.")
                    await j._copy_media_ready.wait()
                finally:
                    j.params["awaiting_copy_medium"] = False
                    del j._copy_media_ready
            from src.core.disc import DiscError
            from src.models.media import DiscType
            from src.services.booktype import _as_book_type
            from src.services.ripper import RipError
            from src.services.verify import FAIL as VERIFY_FAIL
            # Blu-ray-Quelle erkennen, damit burn_iso Book Type korrekt als
            # NOT_APPLICABLE behandelt (siehe DiscTools._apply_book_type) -
            # ohne dies bliebe eine kopierte Blu-ray fälschlich als DVD
            # klassifiziert (burn_iso()-Default), obwohl growisofs den
            # eigentlichen Brennvorgang für beide Medienfamilien ohnehin
            # identisch ausführt.
            try:
                source_root = DiscRipper._root(j.params["source"])
                disc_type = DiscType.BLURAY if (source_root / "BDMV").is_dir() else DiscType.DVD
            except RipError:
                disc_type = DiscType.DVD
            outcome = await self.disc.burn_iso(
                image_path, device=j.params["target"], job=j, disc_type=disc_type,
                book_type=_as_book_type(j.params.get("book_type", "automatic")))
            j.params["burn_outcome"] = outcome.to_dict()
            if outcome.verify.status == VERIFY_FAIL:
                raise DiscError(f"Verifikation fehlgeschlagen: {outcome.verify.message}")

        return self._submit_job(job, _handler)

    async def _confirm_copy_medium(self, job_id: str) -> dict:
        from src.models.media import JobState

        job = self.pipeline.get_job(job_id)
        event = getattr(job, "_copy_media_ready", None)
        if not job or job.state != JobState.RUNNING or event is None or event.is_set():
            return {"error": "Dieser Kopierjob wartet nicht auf einen Medienwechsel."}
        try:
            info = await self.disc.get_disc_info(job.params["target"])
        except Exception as exc:
            return {"error": f"Medium konnte nicht geprüft werden: {exc}"}
        if info.get("error"):
            return {"error": str(info["error"])}
        if not info.get("present"):
            return {"error": "Kein Medium erkannt. Bitte einen leeren Rohling einlegen."}
        if not info.get("blank"):
            detail = " Wiederbeschreibbare Medien müssen vorher geleert werden." if info.get("rewritable") else ""
            return {"error": "Bitte die Quelldisc entfernen und einen leeren Rohling einlegen." + detail}
        # A filesystem-only fallback can label an empty mounted volume as
        # blank. Require a writable optical profile supported by burn_iso's
        # growisofs path; never treat an unknown profile or a ROM as a blank.
        profile = str(info.get("profile") or "").upper().split()
        writable_profiles = {"DVD-R", "DVD-RW", "DVD+R", "DVD+RW", "DVD-RAM", "BD-R", "BD-RE"}
        if not profile or profile[0] not in writable_profiles:
            return {"error": "Kein geeigneter beschreibbarer DVD-/Blu-ray-Rohling erkannt."}
        try:
            capacity = info.get("capacity_bytes")
            if capacity is not None and capacity < job.output_path.stat().st_size:
                return {"error": "Der Rohling ist zu klein für das kopierte Abbild."}
        except (OSError, TypeError) as exc:
            return {"error": f"Abbild oder Medienkapazität konnte nicht geprüft werden: {exc}"}
        # Cancellation or another confirmation may have completed during the probe.
        if job.state != JobState.RUNNING or getattr(job, "_copy_media_ready", None) is not event or event.is_set():
            return {"error": "Der Kopierjob wartet nicht mehr auf einen Medienwechsel."}
        event.set()
        return {"ok": True}

    def confirm_copy_medium(self, job_id: str) -> str:
        pending = self._async(self._confirm_copy_medium(job_id))
        try:
            return json.dumps(pending.result(timeout=30))
        except Exception as exc:
            # A timed-out check must never release the burn later in the background.
            pending.cancel()
            return json.dumps({"error": f"Medium konnte nicht geprüft werden: {exc}"})

    def rip_disc(self, device: str, output_format: str = "mkv_h265") -> str:
        """Rips an unprotected mounted DVD/Blu-ray or creates a filesystem ISO."""
        from src.models.media import Job, JobType
        output_format = (output_format or "mkv_h265").lower().strip()
        extensions = {"mp4_h264": ".mp4", "mkv_h265": ".mkv",
                      "mkv_copy": ".mkv", "iso": ".iso"}
        if output_format not in extensions:
            return json.dumps({"error": f"Nicht unterstütztes Rip-Format: {output_format}"})
        if not device:
            return json.dumps({"error": "Kein Disc-Laufwerk ausgewählt."})
        safe_device = device.replace(":", "").replace("\\", "").replace("/", "") or "disc"
        output = self.settings.directories.output_dir / f"Disc_{safe_device}_Rip{extensions[output_format]}"
        job = Job(
            job_type=JobType.RIP_DVD, output_path=output,
            params={"device": device, "format": output_format,
                    "display_name": f"Disc {device} -> {output.name}"},
        )

        async def _handler(j):
            from src.services.ripper import DiscRipper
            ripper = DiscRipper(self.ffmpeg, self.disc)
            j.output_path = await ripper.rip(
                j.params["device"], j.output_path, j.params["format"], job=j)

        return self._submit_job(job, _handler)

    # ── Vorschau-/Preview-Player ─────────────────────────────────────────
    # Nutzt player_source.py (DVD-IFO/Blu-ray-MPLS-Auflösung, keine
    # parallele Disc-Analyse) und player.py (mpv per JSON-IPC). Ein
    # DiscContent-Titel wird per (device, disc_type, title_index) referenziert
    # - genau die Auswahl, die die UI aus dem bereits geladenen
    # get_disc_content()-Ergebnis kennt; keine erneute Titelerkennung hier.

    async def _player_open(self, source: dict) -> dict:
        from src.models.media import DiscType
        from src.services import player_source
        from src.services.iso_mount import IsoMountError, mount
        from src.services.player import PlayerBackendError, PlayerError

        kind = source.get("kind")
        label = source.get("label") or ""
        mounted_this_call = False
        try:
            if kind == "file":
                path = Path(source["path"])
                if not path.is_file():
                    return {"error": f"Datei nicht gefunden: {path}"}
                segments = [path]
                label = label or path.name
                on_unload = None
            elif kind in ("dvd_title", "bluray_title"):
                device = source.get("device") or ""
                if not device:
                    return {"error": "Kein optisches Laufwerk ausgewählt."}
                root = Path(device.rstrip("\\/") + "/") if len(device) == 2 and device[1] == ":" else Path(device)
                disc_type = DiscType.BLURAY if kind == "bluray_title" else DiscType.DVD
                playback = player_source.resolve_title(root, disc_type, int(source["title_index"]))
                segments = playback.segments
                label = label or f"{device} - Titel {source['title_index']}"
                on_unload = None
            elif kind in ("dvd_iso", "bluray_iso"):
                iso_path = Path(source["path"])
                if not iso_path.is_file():
                    return {"error": f"ISO-Datei nicht gefunden: {iso_path}"}
                if self._player_mount is not None:
                    await self._player_mount.unmount()
                    self._player_mount = None
                mounted = await mount(iso_path)
                self._player_mount = mounted
                mounted_this_call = True
                disc_type = DiscType.BLURAY if kind == "bluray_iso" else DiscType.DVD
                playback = player_source.resolve_title(mounted.root, disc_type, int(source["title_index"]))
                segments = playback.segments
                label = label or f"{iso_path.name} - Titel {source['title_index']}"

                async def on_unload():
                    if self._player_mount is not None:
                        await self._player_mount.unmount()
                        self._player_mount = None
            else:
                return {"error": f"Unbekannte Quellenart: {kind!r}"}
        except player_source.PlaybackSourceError as exc:
            # Titelauflösung kann NACH einem bereits erfolgreichen ISO-Mount
            # scheitern (z. B. unbekannter Titel-Index) - ohne dieses Aushängen
            # bliebe das Abbild dauerhaft gemountet, obwohl nie wiedergegeben
            # wurde ("keine dauerhaften Mounts nach Beenden der Wiedergabe").
            if mounted_this_call and self._player_mount is not None:
                await self._player_mount.unmount()
                self._player_mount = None
            return {"error": str(exc)}
        except IsoMountError as exc:
            return {"error": str(exc)}

        try:
            state = await self.player.open(segments, label=label, on_unload=on_unload)
        except (PlayerBackendError, PlayerError) as exc:
            if mounted_this_call and self._player_mount is not None:
                await self._player_mount.unmount()
                self._player_mount = None
            return {"error": str(exc)}
        return state.to_dict()

    def player_open(self, source_json: str) -> str:
        try:
            source = json.loads(source_json)
        except (json.JSONDecodeError, TypeError):
            return json.dumps({"error": "Ungültige Player-Quelle."})
        result = self._async(self._player_open(source))
        try:
            return json.dumps(result.result(timeout=30))
        except Exception as exc:
            result.cancel()
            return json.dumps({"error": f"Wiedergabe konnte nicht gestartet werden: {exc}"})

    def _player_action(self, coro_factory, *, timeout: float = 10.0) -> str:
        """Gemeinsame Hülle für alle einfachen Transport-/Track-Aktionen:
        räumt bei einem Fehler nie die laufende Wiedergabe stillschweigend
        weg, meldet ihn nur strukturiert zurück."""
        from src.services.player import PlayerError
        pending = self._async(coro_factory())
        try:
            pending.result(timeout=timeout)
            return json.dumps({"ok": True})
        except PlayerError as exc:
            return json.dumps({"error": str(exc)})
        except Exception as exc:
            pending.cancel()
            return json.dumps({"error": str(exc)})

    def player_play(self) -> str: return self._player_action(self.player.play)
    def player_pause(self) -> str: return self._player_action(self.player.pause)
    def player_toggle_pause(self) -> str: return self._player_action(self.player.toggle_pause)
    def player_stop(self) -> str: return self._player_action(self.player.stop)
    def player_seek(self, seconds: float, relative: bool = False) -> str:
        return self._player_action(lambda: self.player.seek(seconds, relative=relative))
    def player_set_volume(self, percent: float) -> str:
        return self._player_action(lambda: self.player.set_volume(percent))
    def player_set_fullscreen(self, enabled: bool) -> str:
        return self._player_action(lambda: self.player.set_fullscreen(enabled))
    def player_set_audio_track(self, track_id: int) -> str:
        return self._player_action(lambda: self.player.set_audio_track(track_id))
    def player_set_subtitle_track(self, track_id: int) -> str:
        return self._player_action(lambda: self.player.set_subtitle_track(track_id))
    def player_disable_subtitles(self) -> str:
        return self._player_action(self.player.disable_subtitles)
    def player_set_chapter(self, index: int) -> str:
        return self._player_action(lambda: self.player.set_chapter(index))

    def player_get_state(self) -> str:
        try:
            state = self._async(self.player.get_state()).result(timeout=10)
            return json.dumps(state.to_dict())
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    def player_close(self) -> str:
        return self._player_action(self.player.close, timeout=15)

    def player_check_engine(self) -> str:
        """Meldet, ob das Wiedergabe-Backend (mpv) überhaupt verfügbar ist,
        plus die ehrliche DRM-Fähigkeitsübersicht (siehe drm_capabilities.py) -
        für die UI, bevor sie die Player-Steuerung überhaupt anbietet."""
        import shutil
        from src.services.drm_capabilities import describe_drm_support
        mpv_path = shutil.which("mpv")
        return json.dumps({
            "engine": "mpv",
            "available": mpv_path is not None,
            "path": mpv_path,
            "drm": describe_drm_support(),
        })

    # ── KI/Medienwerkzeuge ─────────────────────────────────────────────
    def create_highlights(self, input_path: str, duration_seconds: int = 300) -> str:
        from src.models.media import Job, JobType, HighlightConfig
        source = Path(input_path)
        if not source.is_file():
            return json.dumps({"error": f"Datei nicht gefunden: {source}"})
        output = self.settings.directories.output_dir / f"{source.stem}_highlights.mp4"
        job = Job(job_type=JobType.SMART_EDIT, input_files=[source], output_path=output,
                  params={"duration": max(10, int(duration_seconds)),
                          "display_name": f"Auto-Edit: {source.name}"})

        async def _handler(j):
            from src.services.smart_edit import SmartEdit
            editor = SmartEdit(ffmpeg=self.ffmpeg)
            cfg = HighlightConfig(target_duration_seconds=j.params["duration"])
            j.output_path = await editor.create_highlights(
                j.input_files[0], j.output_path, cfg, j)

        return self._submit_job(job, _handler)

    def generate_subtitles(self, input_path: str, language: str = "",
                           model: str = "base", fmt: str = "srt") -> str:
        from src.models.media import Job, JobType
        source = Path(input_path)
        if not source.is_file():
            return json.dumps({"error": f"Datei nicht gefunden: {source}"})
        fmt = fmt.lower()
        if fmt not in {"srt", "vtt", "ass", "txt", "tsv", "json"}:
            return json.dumps({"error": f"Nicht unterstütztes Untertitelformat: {fmt}"})
        output = self.settings.directories.output_dir / f"{source.stem}.{fmt}"
        job = Job(job_type=JobType.SUBTITLE_GENERATE, input_files=[source], output_path=output,
                  params={"model": model, "language": language or None, "format": fmt,
                          "display_name": f"Untertitel: {source.name}"})

        async def _handler(j):
            from src.services.subtitle import SubtitleGenerator
            gen = SubtitleGenerator(model=j.params["model"])
            j.output_path = await gen.generate(
                j.input_files[0], j.output_path,
                language=j.params["language"], format=j.params["format"], job=j)

        return self._submit_job(job, _handler)

    def upscale_video(self, input_path: str, scale: int = 4) -> str:
        from src.models.media import Job, JobType
        source = Path(input_path)
        if not source.is_file():
            return json.dumps({"error": f"Datei nicht gefunden: {source}"})
        scale = 2 if int(scale) == 2 else 4
        output = self.settings.directories.output_dir / f"{source.stem}_{scale}x.mp4"
        job = Job(job_type=JobType.UPSCALE, input_files=[source], output_path=output,
                  params={"scale": scale, "display_name": f"Upscale {scale}x: {source.name}"})

        async def _handler(j):
            from src.services.upscaler import VideoUpscaler
            up = VideoUpscaler(ffmpeg_path=self.settings.tools.ffmpeg)
            j.output_path = await up.upscale(
                j.input_files[0], j.output_path, scale=j.params["scale"], job=j)

        return self._submit_job(job, _handler)

    def interpolate_video(self, input_path: str, target_fps: float = 60.0) -> str:
        from src.models.media import Job, JobType
        source = Path(input_path)
        if not source.is_file():
            return json.dumps({"error": f"Datei nicht gefunden: {source}"})
        fps = min(240.0, max(1.0, float(target_fps)))
        output = self.settings.directories.output_dir / f"{source.stem}_{int(fps)}fps.mp4"
        job = Job(job_type=JobType.INTERPOLATE, input_files=[source], output_path=output,
                  params={"target_fps": fps,
                          "display_name": f"Interpolation {fps:g} fps: {source.name}"})

        async def _handler(j):
            from src.services.upscaler import VideoUpscaler
            up = VideoUpscaler(ffmpeg_path=self.settings.tools.ffmpeg)
            j.output_path = await up.interpolate(
                j.input_files[0], j.output_path,
                target_fps=j.params["target_fps"], job=j)

        return self._submit_job(job, _handler)

    def _restoration_service(self):
        from src.services.restoration import Restoration
        return Restoration(self.library,self.ffmpeg,self.settings.directories.output_dir,self.settings.directories.temp_dir)

    def restoration_analyze(self, path):
        future=None
        try:
            future=self._async(self._restoration_service().analyze(path))
            return future.result(timeout=120).model_dump_json()
        except Exception as exc:
            if future is not None:future.cancel()
            return json.dumps({'error':str(exc)})

    def restoration_process(self, plan_json, preview=True):
        from src.models.restoration import RestorationPlan
        from src.models.media import Job, JobType
        future=None
        try:
            plan=RestorationPlan.model_validate_json(plan_json)
            if preview:
                future=self._async(self._restoration_service().render(plan,preview=True))
                return future.result(timeout=180).model_dump_json()
            job=Job(job_type=JobType.RESTORE,input_files=[Path(plan.analysis.asset.path)],
                    params={'display_name':'Video restaurieren: '+plan.analysis.asset.title})
            async def handler(j):
                await self._restoration_service().render(plan,job=j)
            return self._submit_job(job,handler)
        except Exception as exc:
            if future is not None:future.cancel()
            return json.dumps({'error':str(exc)})

    def restoration_project(self, value, save=False):
        from src.models.restoration import RestorationPlan
        try:
            service=self._restoration_service()
            if save:
                plan=RestorationPlan.model_validate_json(value);service.save(plan)
            else:
                plan=service.load(value)
            return plan.model_dump_json()
        except Exception as exc:
            return json.dumps({'error':str(exc)})

    def restoration_play(self, project_id, index):
        try:
            plan=self._restoration_service().load(project_id)
            index=int(index)
            if index not in (0,1): raise ValueError('Ungültige Vorschau.')
            path=Path(plan.preview[index])
            if not path.is_file() or path.suffix.lower()!='.mp4':raise ValueError('Vorschau fehlt.')
            if sys.platform=='darwin':
                from src.utils.subprocesses import run_hidden
                run_hidden(['open',str(path)],check=True,timeout=10)
            elif sys.platform=='win32':
                os.startfile(str(path))
            else:
                from src.utils.subprocesses import run_hidden
                run_hidden(['xdg-open',str(path)],check=True,timeout=10)
            return json.dumps({'ok':True})
        except Exception as exc:
            return json.dumps({'error':str(exc)})

    def restoration_batch(self, paths_json, adaptive=False, preset="natural", size="original"):
        """Queue a restoration for several files/folders; one failure never stops the rest (Mission 7)."""
        from src.models.media import Job, JobType
        try:
            raw = json.loads(paths_json) if isinstance(paths_json, str) else paths_json
            paths = [Path(p) for p in raw]
            if not paths:
                return json.dumps({"error": "Keine Quellen ausgewählt."})
            service = self._restoration_service()
            sources = service.collect_sources(paths)
            if not sources:
                return json.dumps({"error": "Keine Videodateien in der Auswahl gefunden."})
            job = Job(job_type=JobType.RESTORE, input_files=sources,
                      params={"display_name": f"Batch-Restauration ({len(sources)} Dateien)", "batch_results": []})

            async def handler(j):
                def on_item(index, entry, total):
                    j.params["batch_results"].append(entry)
                    done = index + 1
                    j.update_progress(done / total * 100, f"Datei {done}/{total}: {entry['status']}")
                results = await service.batch(sources, adaptive=bool(adaptive), preset=preset,
                                              size=size, job=j, on_item=on_item)
                outputs = [r["output"] for r in results if r.get("output")]
                if outputs:
                    j.output_path = Path(outputs[-1])
                    j.params["output_paths"] = outputs
                j.params["batch_summary"] = {"total": len(results),
                    "done": sum(1 for r in results if r["status"] == "done"),
                    "errors": sum(1 for r in results if r["status"] == "error")}
            return self._submit_job(job, handler)
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    def restoration_archive(self, plan_json):
        """Mission 4/5: queue a lossless FFV1 preservation master + manifest for the analysed source."""
        from src.models.restoration import RestorationPlan
        from src.models.media import Job, JobType
        try:
            plan = RestorationPlan.model_validate_json(plan_json)
            service = self._restoration_service()
            job = Job(job_type=JobType.CONVERT, input_files=[Path(plan.analysis.asset.path)],
                      params={"display_name": f"Archivkopie: {plan.analysis.asset.title}"})

            async def handler(j):
                result = await service.archive(plan, job=j)
                archive = result.archives[-1] if result.archives else None
                if archive:
                    # Deliberately NOT in output_paths: the preservation master must
                    # not be promoted into Recent Media. The UI gets it via job_done.
                    j.params["archive"] = archive
            return self._submit_job(job, handler)
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    def _smart_editor_service(self):
        from src.services.smart_edit import SmartEditor
        dirs = self.settings.directories
        return SmartEditor(self.library, self.ffmpeg, dirs.output_dir, dirs.temp_dir)

    def smart_edit_capabilities(self):
        try:
            return json.dumps(self._async(self._smart_editor_service().capabilities()).result(timeout=8))
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    def smart_edit_short(self, source_path, target_duration=15, aspect_ratio="9:16",
                         silence_preset="natural", caption_style="modern", voice_preset="clear",
                         export_preset="youtube_shorts", remove_fillers=False):
        """Mission 10: turn one source into a short, then queue the render (LLM optional)."""
        from src.models.media import Job, JobType
        from src.models.smart_edit import (CaptionStyle, SilenceSettings, SmartEditProject,
                                            VoiceEnhanceSettings)
        try:
            source = Path(source_path)
            if not source.is_file():
                return json.dumps({"error": f"Quelle fehlt: {source}"})
            asset = self._async(self.library.asset(source)).result(timeout=60)
            project = SmartEditProject(source_assets=[asset], target_duration=float(target_duration),
                aspect_ratio=aspect_ratio, silence=SilenceSettings(preset=silence_preset),
                captions=CaptionStyle(style=caption_style), voice_enhance=VoiceEnhanceSettings(preset=voice_preset),
                export_preset=export_preset, remove_fillers=bool(remove_fillers),
                planner="ollama" if asset.transcript else "deterministic")
            editor = self._smart_editor_service()
            director = self._director_service() if asset.transcript else None
            job = Job(job_type=JobType.SMART_EDIT, input_files=[source],
                      params={"display_name": f"Short erstellen: {asset.title or source.name}"})

            async def handler(j):
                await editor.render_short(project, director=director, job=j)
            return self._submit_job(job, handler)
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    def smart_edit_project(self, value, save=False):
        from src.models.smart_edit import SmartEditProject
        try:
            service = self._smart_editor_service()
            if save:
                project = SmartEditProject.model_validate_json(value); service.save(project)
            else:
                project = service.load(value)
            return project.model_dump_json()
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    def _director_service(self):
        from src.services.director import Director
        from src.services.assistant import Assistant
        dirs = self.settings.directories
        return Director(self.library, self.ffmpeg,
            Assistant(model=self.settings.ai.ollama_model, host=self.settings.ai.ollama_host),
            dirs.output_dir, dirs.audio_dir, dirs.temp_dir)

    def director_capabilities(self):
        try:
            return json.dumps(self._async(self._director_service().capabilities()).result(timeout=8))
        except Exception as exc:
            return json.dumps({"error":str(exc)})

    def director_assets(self, paths_json="[]"):
        async def load():
            paths = json.loads(paths_json)
            if not paths:
                paths = [r["path"] for r in self.library.recent_outputs() if r["type"] == "video"][:3]
            if not isinstance(paths, list) or len(paths) > 20:
                raise ValueError("Bitte höchstens 20 Assets auswählen.")
            return [(await self.library.asset(path)).model_dump() for path in paths]
        try:
            return json.dumps(self._async(load()).result(timeout=60))
        except Exception as exc:
            return json.dumps({"error":str(exc)})

    def director_plan(self, prompt, paths_json, duration=0, model="", transcribe=False):
        future = None
        try:
            future = self._async(self._director_service().plan(prompt, json.loads(paths_json), float(duration),
                model=model, transcribe=bool(transcribe), whisper_model=self.settings.ai.whisper_model))
            return future.result(timeout=200).model_dump_json()
        except Exception as exc:
            if future is not None:
                future.cancel()
            return json.dumps({"error":str(exc)})

    def director_projects(self):
        return json.dumps(self._director_service().list_projects())

    def director_load(self, project_id):
        try:
            return self._director_service().load(project_id).model_dump_json()
        except Exception as exc:
            return json.dumps({"error":str(exc)})

    def director_suggestions(self, project_json):
        from src.models.director import ProductionProject
        from src.services.timeline import suggestions
        try:return json.dumps(suggestions(ProductionProject.model_validate_json(project_json)))
        except Exception as exc:return json.dumps({'error':str(exc)})

    def director_edit(self, project_json, operation, index=0, values_json="{}"):
        from src.models.director import ProductionProject
        from src.services.timeline import edit
        try:
            return edit(ProductionProject.model_validate_json(project_json),operation,int(index),json.loads(values_json)).model_dump_json()
        except Exception as exc:
            return json.dumps({'error':str(exc)})

    def timeline_waveform(self, asset_path):
        """Mission 35: cached real audio peaks for one source; UI slices per clip."""
        from src.services.waveform import Waveform
        try:
            service = Waveform(self.ffmpeg, self.library.db_path.parent / 'waveform-cache')
            return json.dumps(self._async(service.peaks(asset_path)).result(timeout=90))
        except Exception as exc:
            return json.dumps({'error': str(exc)})

    def director_save(self, project_json):
        from src.models.director import ProductionProject
        try:
            project = ProductionProject.model_validate_json(project_json)
            self._director_service().save(project)
            return json.dumps({"id":project.id})
        except Exception as exc:
            return json.dumps({"error":str(exc)})

    def director_translate(self, project_json, model, target_language='en'):
        from src.models.director import ProductionProject, DubbingPlan, DubbingCue
        from src.services.translation import LocalOllamaTranslationProvider
        from src.services.assistant import Assistant
        try:
            project=ProductionProject.model_validate_json(project_json)
            if not project.dubbing:
                asset=next((a for a in project.assets if a.kind=='video' and (a.transcript or {}).get('segments')),None)
                if not asset:
                    raise ValueError('Dubbing benötigt zeitmarkiertes Transkript oder einen manuell geprüften Dubbing-Plan.')
                project.dubbing=DubbingPlan(asset_id=asset.id,source_language=asset.transcript.get('language') or 'auto',
                    target_language=target_language,cues=[DubbingCue(start=s['start'],end=s['end'],source_text=s['text']) for s in asset.transcript['segments']])
            provider=LocalOllamaTranslationProvider(Assistant(model=model,host=self.settings.ai.ollama_host))
            return self._async(self._director_service().prepare_dubbing(project,provider)).result(timeout=100).model_dump_json()
        except Exception as exc:
            return json.dumps({'error':str(exc)})

    def director_render(self, project_json, encoder="auto"):
        from src.models.director import ProductionProject
        from src.models.media import Job, JobType
        try:
            project = ProductionProject.model_validate_json(project_json)
        except Exception as exc:
            return json.dumps({"error":str(exc)})
        job = Job(job_type=JobType.DIRECTOR_RENDER,
                  input_files=[Path(a.path) for a in project.assets],
                  params={"display_name":f"KI-Regisseur: {project.title}", "project_id":project.id})
        async def handler(j):
            service=self._director_service()
            render=service.render_dubbing if project.dubbing else service.render
            await render(project, encoder=encoder, job=j)
        return self._submit_job(job, handler)

    def run_assistant(self, prompt: str) -> str:
        prompt = (prompt or "").strip()
        if not prompt:
            return json.dumps({"error": "Bitte einen Befehl eingeben."})
        try:
            from src.services.assistant import Assistant
            assistant = Assistant(model=self.settings.ai.ollama_model,
                                  host=self.settings.ai.ollama_host)
            result = self._async(assistant.parse_command(prompt)).result(timeout=45)
            return json.dumps(result)
        except Exception as e:
            return json.dumps({"error": str(e)})

    # ── Bibliothek ─────────────────────────────────────────────────────
    def scan_library(self, folder: str) -> str:
        path = Path(folder)
        if not path.is_dir():
            return json.dumps({"error": f"Ordner nicht gefunden: {path}"})

        def _progress(current, total, name):
            self._emit("scan_progress", {"current": current, "total": total, "file": name})

        try:
            added = self._async(self.library.scan_folder(
                path, recursive=True, generate_thumbs=True,
                on_progress=_progress)).result(timeout=1800)
            return json.dumps({"added": added})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def search_library(self, query: str) -> str:
        try:
            return json.dumps(self.library.search(query or ""))
        except Exception as e:
            return json.dumps({"error": str(e)})

    def get_library(self, media_type: str = "", limit: int = 200) -> str:
        try:
            return json.dumps(self.library.get_all(
                media_type=media_type or None, limit=max(1, min(int(limit), 2000))))
        except Exception as e:
            return json.dumps({"error": str(e)})

    def get_library_stats(self) -> str:
        try:
            return json.dumps(self.library.get_stats())
        except Exception as e:
            return json.dumps({"error": str(e)})

    # ── Schneiden / Zusammenfügen / Batch ──────────────────────────────
    def trim_video(self, input_path: str, start: float, end: float,
                   output_path: str = "") -> str:
        from src.models.media import Job, JobType
        source = Path(input_path)
        if not source.is_file():
            return json.dumps({"error": f"Datei nicht gefunden: {source}"})
        start, end = float(start), float(end)
        if start < 0 or end <= start:
            return json.dumps({"error": "Ungültiger Schnittbereich."})
        output = Path(output_path) if output_path else (
            self.settings.directories.output_dir / f"{source.stem}_trim{source.suffix}")
        if not output.is_absolute():
            output = self.settings.directories.output_dir / output
        job = Job(job_type=JobType.TRIM, input_files=[source], output_path=output,
                  params={"start": start, "end": end,
                          "display_name": f"Trim: {source.name} [{start:g}-{end:g}s]"})

        async def _handler(j):
            j.output_path = await self.ffmpeg.trim(
                j.input_files[0], j.output_path,
                j.params["start"], j.params["end"], job=j)

        return self._submit_job(job, _handler)

    def preview_trim(self, input_path: str, start: float, end: float) -> str:
        """Creates a short temporary clip and opens it with the Windows default player."""
        try:
            source = Path(input_path)
            if not source.is_file():
                return json.dumps({"error": f"Datei nicht gefunden: {source}"})
            start, end = float(start), float(end)
            if start < 0 or end <= start:
                return json.dumps({"error": "Ungültiger Vorschau-Bereich."})
            preview_dir = self.settings.directories.temp_dir / "preview"
            preview_dir.mkdir(parents=True, exist_ok=True)
            preview = preview_dir / f"{source.stem}_preview.mp4"
            preview.unlink(missing_ok=True)
            result = self._async(
                self.ffmpeg.trim(source, preview, start, min(end, start + 20.0))
            ).result(timeout=180)
            if sys.platform == "darwin":
                from src.utils.subprocesses import run_hidden
                run_hidden(["open", str(result)], check=True, timeout=10)
            else:
                os.startfile(str(result))
            return json.dumps({"ok": True, "path": str(result)})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def merge_videos(self, paths_json: str, output_path: str = "") -> str:
        from src.models.media import Job, JobType
        try:
            raw = json.loads(paths_json) if isinstance(paths_json, str) else paths_json
            paths = [Path(p) for p in raw]
        except Exception:
            return json.dumps({"error": "Ungültige Pfad-Liste"})
        if len(paths) < 2:
            return json.dumps({"error": "Mindestens zwei Dateien erforderlich."})
        missing = [p for p in paths if not p.is_file()]
        if missing:
            return json.dumps({"error": f"Datei nicht gefunden: {missing[0]}"})
        output = Path(output_path) if output_path else Path("merged_output.mp4")
        if not output.is_absolute():
            output = self.settings.directories.output_dir / output
        job = Job(job_type=JobType.MERGE, input_files=paths, output_path=output,
                  params={"display_name": f"Merge: {len(paths)} Dateien"})

        async def _handler(j):
            j.output_path = await self.ffmpeg.merge(j.input_files, j.output_path, job=j)

        return self._submit_job(job, _handler)

    def convert_batch(self, paths_json: str, preset: str,
                      output_path: str = "", overwrite: bool = False, encoder: str = "auto") -> str:
        try:
            if isinstance(paths_json, str) and Path(paths_json).is_dir():
                supported = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm",
                             ".mpg", ".mpeg", ".vob", ".mp3", ".flac", ".wav",
                             ".aac", ".ogg", ".m4a"}
                paths = [str(p) for p in sorted(Path(paths_json).rglob("*"))
                         if p.is_file() and p.suffix.lower() in supported]
            else:
                raw = json.loads(paths_json) if isinstance(paths_json, str) else paths_json
                paths = [str(p) for p in raw]
        except Exception:
            return json.dumps({"error": "Ungültige Datei- oder Ordnerliste"})
        if not paths:
            return json.dumps({"error": "Keine unterstützten Mediendateien im Ordner gefunden."})
        ids, errors = [], []
        output_dir = Path(output_path) if output_path else None
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
        for path in paths:
            # Let the converter derive a unique filename unless an explicit
            # batch output directory was selected.
            item_output = None
            if output_dir:
                from src.config.presets import get_preset
                item_output = output_dir / (Path(path).stem + "." + get_preset(preset).container)
            result = json.loads(self.convert_file(
                path, preset, str(item_output) if item_output else None, overwrite, encoder))
            if result.get("job_id"):
                ids.append(result["job_id"])
            elif result.get("error"):
                errors.append({"path": path, "error": result["error"]})
        return json.dumps({"job_ids": ids, "count": len(ids), "errors": errors})

    def retry_job(self, job_id: str) -> str:
        try:
            if not getattr(self, 'conversion_queue', None):
                return json.dumps({'ok': False, 'error': 'Job nicht gefunden.'})
            ok = self._async(self.conversion_queue.retry(job_id)).result(timeout=5)
            return json.dumps({'ok': ok})
        except Exception as exc:
            return json.dumps({'error': str(exc)})

    def cancel_job(self, job_id: str) -> str:
        try:
            if getattr(self, 'conversion_queue', None):
                ok = self._async(self.conversion_queue.cancel(job_id)).result(timeout=5)
                if ok is not None:
                    return json.dumps({'ok': bool(ok)})
            ok = self._async(self.pipeline.cancel_job(job_id)).result(timeout=5)
            return json.dumps({"ok": bool(ok)})
        except Exception as e:
            return json.dumps({"error": str(e)})

    # ── Watch Folder ───────────────────────────────────────────────────
    def set_watch_folder(self, folder: str, preset: str,
                         action: str = "convert", enabled: bool = True) -> str:
        try:
            if self._watch and self._watch._running:
                self._async(self._watch.stop()).result(timeout=5)
            if not enabled:
                self._watch = None
                return json.dumps({"ok": True, "running": False})
            path = Path(folder)
            path.mkdir(parents=True, exist_ok=True)
            from src.services.watch_folder import WatchFolder, WatchRule
            extensions = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm",
                          ".mpg", ".mpeg", ".vob", ".mp3", ".flac", ".wav",
                          ".aac", ".ogg", ".m4a"}
            rule = WatchRule(f"Auto: {action}", extensions, action, preset, True)

            async def _submit_watched(file_path, matched_rule):
                from src.config.presets import get_preset
                from src.models.media import Job, JobType
                if matched_rule.action == "burn_dvd":
                    job = Job(
                        job_type=JobType.BURN_DVD, input_files=[file_path],
                        params={"display_name": f"Auto-DVD: {file_path.name}"},
                    )

                    async def handler(j):
                        from src.services.dvd_workflow import DVDProject
                        project = DVDProject(
                            title=file_path.stem, input_files=[file_path],
                            output_dir=self.settings.directories.output_dir,
                            standard=self.settings.conversion.dvd_standard,
                            burn_to_disc=True, only_iso=False,
                            disc_device=self.settings.burn.default_device,
                            burn_speed=self.settings.burn.default_speed,
                            verify_after_burn=self.settings.burn.verify_after_burn,
                            eject_after_burn=self.settings.burn.eject_after_burn,
                        )
                        j.output_path = await self.dvd_workflow.run(project, job=j)
                else:
                    preset_name = "mp3_320k" if matched_rule.action == "extract_audio" else (matched_rule.preset or "mp4_h264_1080p")
                    selected_preset = get_preset(preset_name)
                    job = Job(
                        job_type=JobType.CONVERT, input_files=[file_path], preset=selected_preset,
                        params={"display_name": f"Auto: {file_path.name} -> {selected_preset.display_name}",
                                "overwrite": False},
                    )

                    async def handler(j):
                        j.output_path = await self.converter.convert_file(
                            j.input_files[0], j.preset, job=j, overwrite=False)

                self._wire_job_progress(job)
                await self.pipeline.submit(job, handler=handler)
                if not self.pipeline._is_running:
                    asyncio.create_task(self.pipeline.start())
                self._emit("job_queued", {
                    "id": job.id,
                    "name": job.params["display_name"],
                    "type": job.job_type.value,
                })

            self._watch = WatchFolder(path, [rule], self.pipeline, submit_callback=_submit_watched)
            self._async(self._watch.start())
            return json.dumps({"ok": True, "folder": str(path),
                               "action": action, "running": True})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def get_watch_folders(self) -> str:
        watch = self._watch
        if not watch:
            return json.dumps([])
        return json.dumps([{
            "folder": str(watch.folder),
            "running": watch._running,
            "rules": [{"name": r.name, "action": r.action,
                       "preset": r.preset, "enabled": r.enabled} for r in watch.rules],
        }])


    def check_tools(self, *args):
        return self.get_tool_status()

    def shutdown(self):
        """Beendet Watcher, Queue, Datenbank und Async-Loop geordnet."""
        try:
            if self._watch and self._watch._running:
                self._async(self._watch.stop()).result(timeout=3)
            if self.pipeline._is_running or self.pipeline._running or self.pipeline._queue:
                self._async(self.pipeline.shutdown()).result(timeout=5)
        except Exception as e:
            log.warning("Backend-Cleanup unvollständig: %s", e)
        try:
            if getattr(self, 'conversion_queue', None):
                self._async(self.conversion_queue.shutdown()).result(timeout=15)
        except Exception as exc:
            log.warning('Persistente Queue konnte nicht vollständig beendet werden: %s', exc)
        try:
            # Beendet eine evtl. laufende mpv-Instanz und haengt einen evtl.
            # gemounteten Vorschau-ISO wieder aus - kein verwaister Prozess,
            # kein dauerhafter Mount nach dem Beenden (siehe player.py/iso_mount.py).
            if getattr(self, 'player', None):
                self._async(self.player.close()).result(timeout=10)
        except Exception as exc:
            log.warning('Player-Cleanup unvollständig: %s', exc)
        try:
            self.library.close()
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)

    # ── Splash fertig
    def splash_complete(self):
        """Wird vom Splash-Screen aufgerufen wenn er fertig ist."""
        log.info("Splash fertig - lade Haupt-UI")
        if self.window and not self._splash_transition_started:
            self._splash_transition_started = True
            ui_html = BUNDLE_DIR / "src" / "ui" / "app.html"
            html_content = ui_html.read_text(encoding="utf-8")

            def load_main_ui():
                try:
                    if self.window:
                        # Keep the main page on the same inline origin as the
                        # splash. Loading file:// here can make WebView2 lose
                        # the injected JS API.
                        self.window.load_html(html_content)
                except Exception as exc:
                    log.error("Haupt-UI konnte nicht geladen werden: %s", exc)

            # Return the API response before replacing the splash document.
            # Otherwise pywebview tries to resolve the JS promise after its
            # callback table has already been destroyed by the navigation.
            transition = threading.Timer(0.05, load_main_ui)
            transition.daemon = True
            transition.start()
        return json.dumps({"ok": True})


# ── Schlanke JavaScript-API ───────────────────────────────────────────
class RetroDiscApi:
    """Expose only callable API methods to PyWebView.

    PyWebView mirrors public attributes of js_api objects. The full
    RetroDiscBridge owns complex objects (window, settings, pipeline, ffmpeg)
    that can recurse through WebView2/WinForms and freeze the UI. This proxy
    keeps those internals private and forwards only explicit methods.
    """
    def __init__(self, bridge: RetroDiscBridge):
        self._bridge = bridge

    def open_file_dialog(self): return self._bridge.open_file_dialog()
    def open_tool_dialog(self): return self._bridge.open_tool_dialog()
    def open_folder_dialog(self): return self._bridge.open_folder_dialog()
    def open_folder_for_batch(self): return self._bridge.open_folder_for_batch()
    def open_output_folder(self, output_path=""): return self._bridge.open_output_folder(output_path)
    def probe_file(self, path): return self._bridge.probe_file(path)
    def get_mediainfo(self, path): return self._bridge.probe_file(path)
    def convert_file(self, input_path, preset_name, output_path=None, overwrite=False, encoder="auto"): return self._bridge.convert_file(input_path, preset_name, output_path, overwrite, encoder)
    def convert_batch(self, *args): return self._bridge.convert_batch(*args)
    def get_presets(self, category=None): return self._bridge.get_presets(category)
    def get_encoder_options(self): return self._bridge.get_encoder_options()
    def get_recent_media(self): return self._bridge.get_recent_media()
    def download_url(self, url, format="best", audio_only=False, subtitles=False): return self._bridge.download_url(url, format, audio_only, subtitles)
    def search_media(self, query, sources="[]", max_results=15): return self._bridge.search_media(query, sources, max_results)
    def get_queue(self): return self._bridge.get_queue()
    def clear_completed(self): return self._bridge.clear_completed()
    def get_platform_info(self): return self._bridge.get_platform_info()
    def get_path_status(self): return self._bridge.get_path_status()
    def get_settings(self): return self._bridge.get_settings()
    def save_settings(self, data): return self._bridge.save_settings(data)
    def get_tool_status(self): return self._bridge.get_tool_status()
    def diagnostics(self): return self._bridge.diagnostics()
    def check_tools(self): return self._bridge.check_tools()
    def play_sound(self): return self._bridge.play_sound()
    def detect_burners(self): return self._bridge.detect_burners()
    def get_disc_info(self, *args): return self._bridge.get_disc_info(*args)
    def list_target_media(self): return self._bridge.list_target_media()
    def inspect_drive(self, device): return self._bridge.inspect_drive(device)
    def get_disc_content(self, device): return self._bridge.get_disc_content(device)
    def plan_capacity(self, *args): return self._bridge.plan_capacity(*args)
    def create_dvd(self, *args): return self._bridge.create_dvd(*args)
    def create_bluray(self, *args): return self._bridge.create_bluray(*args)
    def check_target_medium(self, device, target_medium_id): return self._bridge.check_target_medium(device, target_medium_id)
    def burn_existing_iso(self, *args): return self._bridge.burn_existing_iso(*args)
    def copy_disc(self, *args): return self._bridge.copy_disc(*args)
    def confirm_copy_medium(self, job_id): return self._bridge.confirm_copy_medium(job_id)
    def rip_disc(self, *args): return self._bridge.rip_disc(*args)
    def player_open(self, source_json): return self._bridge.player_open(source_json)
    def player_play(self): return self._bridge.player_play()
    def player_pause(self): return self._bridge.player_pause()
    def player_toggle_pause(self): return self._bridge.player_toggle_pause()
    def player_stop(self): return self._bridge.player_stop()
    def player_seek(self, seconds, relative=False): return self._bridge.player_seek(seconds, relative)
    def player_set_volume(self, percent): return self._bridge.player_set_volume(percent)
    def player_set_fullscreen(self, enabled): return self._bridge.player_set_fullscreen(enabled)
    def player_set_audio_track(self, track_id): return self._bridge.player_set_audio_track(track_id)
    def player_set_subtitle_track(self, track_id): return self._bridge.player_set_subtitle_track(track_id)
    def player_disable_subtitles(self): return self._bridge.player_disable_subtitles()
    def player_set_chapter(self, index): return self._bridge.player_set_chapter(index)
    def player_get_state(self): return self._bridge.player_get_state()
    def player_close(self): return self._bridge.player_close()
    def player_check_engine(self): return self._bridge.player_check_engine()
    def create_highlights(self, *args): return self._bridge.create_highlights(*args)
    def generate_subtitles(self, *args): return self._bridge.generate_subtitles(*args)
    def upscale_video(self, *args): return self._bridge.upscale_video(*args)
    def interpolate_video(self, *args): return self._bridge.interpolate_video(*args)
    def restoration_analyze(self,path): return self._bridge.restoration_analyze(path)
    def restoration_process(self,plan_json,preview=True): return self._bridge.restoration_process(plan_json,preview)
    def restoration_project(self,value,save=False): return self._bridge.restoration_project(value,save)
    def restoration_play(self,project_id,index): return self._bridge.restoration_play(project_id,index)
    def restoration_batch(self,paths_json,adaptive=False,preset="natural",size="original"): return self._bridge.restoration_batch(paths_json,adaptive,preset,size)
    def restoration_archive(self,plan_json): return self._bridge.restoration_archive(plan_json)
    def smart_edit_capabilities(self): return self._bridge.smart_edit_capabilities()
    def smart_edit_short(self,source_path,target_duration=15,aspect_ratio="9:16",silence_preset="natural",caption_style="modern",voice_preset="clear",export_preset="youtube_shorts",remove_fillers=False): return self._bridge.smart_edit_short(source_path,target_duration,aspect_ratio,silence_preset,caption_style,voice_preset,export_preset,remove_fillers)
    def smart_edit_project(self,value,save=False): return self._bridge.smart_edit_project(value,save)
    def director_capabilities(self): return self._bridge.director_capabilities()
    def director_assets(self, paths_json="[]"): return self._bridge.director_assets(paths_json)
    def director_plan(self, prompt, paths_json, duration=0, model="", transcribe=False): return self._bridge.director_plan(prompt, paths_json, duration, model, transcribe)
    def director_projects(self): return self._bridge.director_projects()
    def director_load(self, project_id): return self._bridge.director_load(project_id)
    def director_suggestions(self, project_json): return self._bridge.director_suggestions(project_json)
    def director_edit(self, project_json, operation, index=0, values_json="{}"):
        return self._bridge.director_edit(project_json,operation,index,values_json)
    def timeline_waveform(self, asset_path): return self._bridge.timeline_waveform(asset_path)
    def director_save(self, project_json): return self._bridge.director_save(project_json)
    def director_translate(self, project_json, model, target_language='en'): return self._bridge.director_translate(project_json,model,target_language)
    def director_render(self, project_json, encoder="auto"): return self._bridge.director_render(project_json, encoder)
    def run_assistant(self, *args): return self._bridge.run_assistant(*args)
    def scan_library(self, *args): return self._bridge.scan_library(*args)
    def search_library(self, *args): return self._bridge.search_library(*args)
    def get_library(self, *args): return self._bridge.get_library(*args)
    def get_library_stats(self, *args): return self._bridge.get_library_stats(*args)
    def trim_video(self, *args): return self._bridge.trim_video(*args)
    def preview_trim(self, *args): return self._bridge.preview_trim(*args)
    def merge_videos(self, *args): return self._bridge.merge_videos(*args)
    def set_watch_folder(self, *args): return self._bridge.set_watch_folder(*args)
    def get_watch_folders(self, *args): return self._bridge.get_watch_folders(*args)

    def retry_job(self, job_id): return self._bridge.retry_job(job_id)
    def cancel_job(self, *args): return self._bridge.cancel_job(*args)
    def splash_complete(self): return self._bridge.splash_complete()


# ── Download-Splash (zeigt Fortschritt beim ersten Start) ─────────────
def get_splash_url() -> str:
    """Return the local startup page URL without WebView2's HTML-size limit."""
    return (BUNDLE_DIR / "src" / "ui" / "splash.html").resolve().as_uri()


def show_download_splash(missing_tools: list) -> None:
    """Zeigt einen Splash mit Download-Fortschritt für fehlende Tools."""
    if sys.platform == "darwin":
        log.error("Fehlende macOS-Tools: %s. Native Tools im PATH oder vendor/ bereitstellen; "
                  "der automatische Download enthält nur Windows-Binaries.", ", ".join(missing_tools))
        return
    try:
        import webview

        progress_data = {"tool": "", "pct": 0, "done": False}

        def do_download():
            TOOL_URLS = {
                "ffmpeg": (
                    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
                    "ffmpeg-master-latest-win64-gpl.zip",
                    TOOLS_DIR / "ffmpeg.exe",
                ),
                "ytdlp": (
                    "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe",
                    TOOLS_DIR / "yt-dlp.exe",
                ),
            }

            for tool in missing_tools:
                if tool not in TOOL_URLS:
                    continue
                url, target = TOOL_URLS[tool]

                def on_progress(name, pct):
                    progress_data["tool"] = name
                    progress_data["pct"] = pct
                    if w.get_elements("#progbar"):
                        w.evaluate_js(
                            f"document.getElementById('progbar').style.width='{pct:.0f}%';"
                            f"document.getElementById('statusText').textContent='Lade {name}: {pct:.0f}%';"
                        )

                try:
                    download_tool(tool, url, target, on_progress)
                except Exception as e:
                    log.error(f"Download fehlgeschlagen: {tool} - {e}")

            progress_data["done"] = True
            if w:
                w.evaluate_js(
                    "document.getElementById('statusText').textContent='Fertig! RetroDisc wird gestartet...';"
                    "document.getElementById('progbar').style.width='100%';"
                )
                import time; time.sleep(1.5)
                w.destroy()

        w = webview.create_window(
            "RetroDisc - Ersteinrichtung",
            url=get_splash_url(),
            width=800, height=620,
            resizable=False,
            on_top=True,
        )

        threading.Thread(target=do_download, daemon=True).start()
        webview.start()

    except Exception as e:
        log.warning(f"Splash fehlgeschlagen: {e} - fahre ohne fort")


# ── Haupt-App ─────────────────────────────────────────────────────────
#: Nur mit diesem Argument laeuft der Acceptance-Selbsttest statt der App.
ACCEPTANCE_FLAG = "--acceptance-selftest"


def block_webview_history_navigation(window) -> bool:
    """Verhindert, dass die WebView-History den Nutzer aus der UI navigiert.

    RetroDisc ist eine Desktop-Anwendung, keine Website. Die seitlichen
    Maustasten (XButton1/XButton2) loesen in Chromium und damit in WebView2
    aber Vor-/Zurueck-Navigation aus. Weil der Splash ueber ``load_html``
    ersetzt wird, existiert ein History-Eintrag: Maus-Zurueck landet auf dem
    Splash-Dokument, in dem die Anwendung nicht mehr existiert.

    pywebview 6.2.1 schaltet ``IsSwipeNavigationEnabled`` und (ausserhalb des
    Debugmodus) die Browser-Tastenkuerzel bereits ab - die Maustasten deckt
    keine dieser Einstellungen ab.

    Gegriffen wird deshalb an ``NavigationStarting``, dem zuverlaessigen
    WebView2-Hook: ``NavigationKind == BackOrForward`` identifiziert genau die
    History-Navigation und wird abgebrochen. Die eigene ``load_html``-
    Navigation der Anwendung ist ``NewDocument`` und laeuft unveraendert
    weiter. Es werden bewusst keine History-Eintraege manipuliert.

    Gibt True zurueck, wenn der Hook haengt. Schlaegt etwas fehl - anderes
    Backend, andere SDK-Version, macOS - bleibt es bei der JavaScript-Ebene
    in ``app.html``; die Anwendung laeuft dann normal weiter.
    """
    try:
        from webview.platforms.winforms import BrowserView
    except Exception as exc:  # pragma: no cover - nur auf Nicht-Windows
        log.info("WebView2-Navigationssperre nicht verfuegbar: %s", exc)
        return False

    form = BrowserView.instances.get(getattr(window, "uid", None))
    control = getattr(form, "webview", None)
    if control is None:
        log.info("WebView2-Navigationssperre: kein Control gefunden")
        return False

    def _on_navigation_starting(sender, args):
        try:
            if str(getattr(args, "NavigationKind", "")) == "BackOrForward":
                args.Cancel = True
                log.info("History-Navigation der WebView unterbunden")
        except Exception:
            # Im Zweifel nicht blockieren: eine kaputte Pruefung darf die
            # Anwendung nicht daran hindern, ihre eigene UI zu laden.
            pass

    try:
        control.NavigationStarting += _on_navigation_starting
    except Exception as exc:
        log.info("WebView2-Navigationssperre konnte nicht gesetzt werden: %s", exc)
        return False

    log.info("WebView2-Navigationssperre aktiv (BackOrForward wird abgebrochen)")
    return True


def main():
    # Schmaler, ausschliesslich ueber dieses Argument aktivierbarer Hook. Ohne
    # das Argument wird der Zweig nie betreten und src.acceptance nie
    # importiert - der normale Produktbetrieb bleibt unveraendert.
    if ACCEPTANCE_FLAG in sys.argv:
        from src.acceptance import run_from_argv
        raise SystemExit(run_from_argv(sys.argv))

    log.info("=" * 50)
    log.info("RetroDisc startet")
    log.info(f"  APPDATA: {APPDATA}")
    log.info(f"  TOOLS:   {TOOLS_DIR}")
    log.info(f"  BUNDLE:  {BUNDLE_DIR}")
    log.info("=" * 50)

    # PyWebView importieren
    try:
        import webview
    except ImportError:
        log.error("PyWebView nicht gefunden!")
        import webbrowser
        html = BUNDLE_DIR / "src" / "ui" / "app.html"
        webbrowser.open(f"file:///{html}")
        input("RetroDisc läuft im Browser. Enter zum Beenden...")
        return

    # Fehlende Tools ermitteln
    tools = check_tools()
    missing = [t for t in ("ffmpeg", "ytdlp") if t not in tools]

    if missing:
        log.info(f"Fehlende Tools: {missing} - starte Download-Splash")
        show_download_splash(missing)

    # Settings
    from src.config.settings import AppSettings
    settings = AppSettings.load()
    settings.ensure_directories()

    # Bridge erstellen
    bridge = RetroDiscBridge()
    js_api = RetroDiscApi(bridge)

    # Main window. It always starts with the bundled branding splash and the
    # JS bridge swaps in the application UI after the short startup sequence.
    # Load HTML inline instead of file:// + http_server.
    # On Windows/WebView2, file:// + http_server can put the injected
    # pywebview bridge on a different origin, leaving window.pywebview missing
    # and making the launcher buttons look clickable but do nothing.
    from src.utils.platform_ui import native_window_options
    ui_html = BUNDLE_DIR / "src" / "ui" / "app.html"
    try:
        window = webview.create_window(
            title="RetroDisc 1.0",
            url=get_splash_url(),
            js_api=js_api,
            width=900,
            height=640,
            min_size=(860, 560),
            background_color="#3A6EA5",
            text_select=False,
            **native_window_options(),
        )
    except Exception as e:
        log.warning(f"Inline HTML load failed ({e}), falling back to file URL")
        window = webview.create_window(
            title="RetroDisc 1.0",
            url=f"file:///{ui_html}",
            js_api=js_api,
            width=900,
            height=640,
            min_size=(860, 560),
            background_color="#3A6EA5",
            text_select=False,
            **native_window_options(),
        )
    bridge.window = window

    # Maus-Zurueck/-Vorwaerts duerfen die WebView-History nie bewegen.
    # Der Hook haengt sich an, sobald das Control existiert.
    window.events.shown += lambda: block_webview_history_navigation(window)

    debug = os.environ.get("RETRODISC_DEBUG", "0") == "1"
    log.info(f"Starte Fenster (debug={debug})")
    try:
        if '--webview-check' in sys.argv:
            from src.utils.package_check import webview_check
            report=sys.argv[sys.argv.index('--webview-check')+1]
            webview.start(lambda:webview_check(window,report),debug=debug)
        else:
            webview.start(debug=debug)
    finally:
        bridge.shutdown()
    log.info("RetroDisc beendet.")


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    if '--package-check' in sys.argv:
        import argparse
        from src.utils.package_check import run
        parser=argparse.ArgumentParser()
        parser.add_argument('--package-check',required=True)
        parser.add_argument('--model')
        parser.add_argument('--audio')
        args=parser.parse_args()
        raise SystemExit(run(args.package_check,args.model,args.audio))
    main()
