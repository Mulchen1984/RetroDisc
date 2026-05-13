"""
RetroDisc — Cross-Platform Portable Launcher
=============================================
Läuft auf:
  Windows 10/11  (x64)
  macOS          (Intel + Apple Silicon M1/M2/M3)
  Linux          (x64, ARM)

Portable-Modus: Alle Daten liegen neben der EXE/App.
Kein Installer, kein Registry-Eintrag, USB-stick-fähig.
"""

import sys
import os
import platform
import logging
import threading
import asyncio
import json
import struct
import wave
import math
from pathlib import Path


# ── Plattform erkennen ────────────────────────────────────────────
SYSTEM  = platform.system()          # "Windows" / "Darwin" / "Linux"
MACHINE = platform.machine().lower() # "x86_64" / "arm64" / "amd64"
IS_WIN  = SYSTEM == "Windows"
IS_MAC  = SYSTEM == "Darwin"
IS_LIN  = SYSTEM == "Linux"
IS_ARM  = "arm" in MACHINE or "aarch" in MACHINE  # M1/M2 = arm64

# ── Pfade ─────────────────────────────────────────────────────────
if getattr(sys, "frozen", False):
    # Läuft als kompilierte App (PyInstaller)
    BASE_DIR   = Path(sys.executable).parent
    BUNDLE_DIR = Path(sys._MEIPASS)
    sys.path.insert(0, str(BUNDLE_DIR))
    PORTABLE   = True
else:
    BASE_DIR   = Path(__file__).parent
    BUNDLE_DIR = BASE_DIR
    PORTABLE   = False

# Portable: Daten neben der EXE/App
DATA_DIR = BASE_DIR / "RetroDisc_Data"
DATA_DIR.mkdir(exist_ok=True)

TOOLS_DIR = DATA_DIR / "tools"
TOOLS_DIR.mkdir(exist_ok=True)
LOG_DIR   = DATA_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

# ── Logging ───────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "retrodisc.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("retrodisc")
log.info(f"System: {SYSTEM} {MACHINE} | Portable: {PORTABLE}")
log.info(f"BASE: {BASE_DIR}")


# ── Tool-Namen je Plattform ───────────────────────────────────────
def tool_name(base: str) -> str:
    """Gibt den plattformspezifischen Tool-Namen zurück."""
    if IS_WIN:
        return base + ".exe"
    return base  # macOS/Linux: kein .exe


TOOL_NAMES = {
    "ffmpeg":  tool_name("ffmpeg"),
    "ffprobe": tool_name("ffprobe"),
    "ytdlp":   tool_name("yt-dlp"),
}

# Download-URLs je Plattform
TOOL_URLS = {
    "Windows": {
        "ffmpeg": (
            "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
            "ffmpeg-master-latest-win64-gpl.zip",
            "zip",
            "ffmpeg-master-latest-win64-gpl/bin/ffmpeg.exe",
        ),
        "ffprobe": (
            "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
            "ffmpeg-master-latest-win64-gpl.zip",
            "zip",
            "ffmpeg-master-latest-win64-gpl/bin/ffprobe.exe",
        ),
        "ytdlp": (
            "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe",
            "direct", None,
        ),
    },
    "Darwin": {  # macOS
        "ffmpeg": (
            "https://evermeet.cx/ffmpeg/getrelease/ffmpeg/zip",
            "zip", "ffmpeg",
        ),
        "ffprobe": (
            "https://evermeet.cx/ffmpeg/getrelease/ffprobe/zip",
            "zip", "ffprobe",
        ),
        "ytdlp": (
            "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_macos",
            "direct", None,
        ),
    },
    "Linux": {
        "ffmpeg": (
            "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
            "ffmpeg-master-latest-linux64-gpl.tar.xz",
            "tarxz",
            "ffmpeg-master-latest-linux64-gpl/bin/ffmpeg",
        ),
        "ffprobe": (
            "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
            "ffmpeg-master-latest-linux64-gpl.tar.xz",
            "tarxz",
            "ffmpeg-master-latest-linux64-gpl/bin/ffprobe",
        ),
        "ytdlp": (
            "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp",
            "direct", None,
        ),
    },
}


# ── Tool-Erkennung ────────────────────────────────────────────────
def find_tools() -> dict[str, str]:
    """
    Sucht Tools in dieser Reihenfolge:
    1. vendor/ im Bundle (eingebaut)
    2. RetroDisc_Data/tools/ (portable, neben der EXE)
    3. System-PATH
    """
    import shutil
    tools = {}

    for key, exe in TOOL_NAMES.items():
        # 1. Bundle vendor/
        p = BUNDLE_DIR / "vendor" / exe
        if p.exists():
            tools[key] = str(p)
            log.info(f"Tool (Bundle): {key} → {p.name}")
            continue

        # 2. Portable tools/ Ordner
        p = TOOLS_DIR / exe
        if p.exists():
            tools[key] = str(p)
            log.info(f"Tool (Portable): {key} → {p.name}")
            continue

        # 3. System PATH
        found = shutil.which(exe) or shutil.which(exe.replace(".exe", ""))
        if found:
            tools[key] = found
            log.info(f"Tool (PATH): {key} → {found}")

    return tools


def download_missing_tools(missing: list[str], on_progress=None) -> None:
    """Lädt fehlende Tools herunter."""
    import urllib.request, zipfile, tarfile, stat

    urls = TOOL_URLS.get(SYSTEM, TOOL_URLS["Linux"])

    # Für macOS: FFmpeg + FFprobe kommen einzeln
    # Für Windows: aus demselben ZIP
    downloaded_zips = {}  # cache für ZIP-Downloads

    for tool in missing:
        if tool not in urls:
            continue

        url, fmt, zip_path = urls[tool]
        target = TOOLS_DIR / TOOL_NAMES[tool]
        log.info(f"Lade {tool} von {url[:60]}...")

        try:
            if fmt == "direct":
                # Direkter Download
                _download_file(url, target, tool, on_progress)
                # Ausführbar machen (macOS/Linux)
                if not IS_WIN:
                    target.chmod(target.stat().st_mode | stat.S_IEXEC)

            elif fmt == "zip":
                if url not in downloaded_zips:
                    zip_file = TOOLS_DIR / "_tmp_bundle.zip"
                    _download_file(url, zip_file, f"{tool}-Bundle", on_progress)
                    downloaded_zips[url] = zip_file

                zip_file = downloaded_zips[url]
                with zipfile.ZipFile(zip_file) as zf:
                    # Suche nach der Datei im ZIP
                    target_name = Path(zip_path).name if zip_path else tool
                    for member in zf.namelist():
                        if Path(member).name == target_name:
                            with zf.open(member) as src, open(target, "wb") as dst:
                                import shutil
                                shutil.copyfileobj(src, dst)
                            if not IS_WIN:
                                target.chmod(target.stat().st_mode | stat.S_IEXEC)
                            log.info(f"{tool} extrahiert: {target}")
                            break

            elif fmt == "tarxz":
                tmp = TOOLS_DIR / "_tmp_bundle.tar.xz"
                _download_file(url, tmp, f"{tool}-Bundle", on_progress)
                with tarfile.open(tmp) as tf:
                    target_name = Path(zip_path).name if zip_path else tool
                    for member in tf.getmembers():
                        if Path(member.name).name == target_name:
                            f_obj = tf.extractfile(member)
                            if f_obj:
                                target.write_bytes(f_obj.read())
                                target.chmod(target.stat().st_mode | stat.S_IEXEC)
                                log.info(f"{tool} extrahiert: {target}")
                            break
                tmp.unlink(missing_ok=True)

        except Exception as e:
            log.error(f"Download {tool} fehlgeschlagen: {e}")

    # Temp-ZIPs aufräumen
    for zip_file in downloaded_zips.values():
        zip_file.unlink(missing_ok=True)


def _download_file(url: str, target: Path, label: str, on_progress=None) -> None:
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "RetroDisc/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        done = 0
        with open(target, "wb") as f:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if on_progress and total:
                    on_progress(label, done / total * 100)
    log.info(f"{label} geladen: {done/1024/1024:.1f} MB")


# ── Fertig-Sound ──────────────────────────────────────────────────
def play_completion_sound():
    """Spielt den RetroDisc-Jingle — plattformübergreifend."""
    try:
        sr, dur = 44100, 1.2
        notes = [(880,.0,.18),(1108,.14,.18),(1318,.28,.18),(1760,.42,.5)]
        samples = [0.0] * int(sr * dur)
        for freq, start, d in notes:
            s0 = int(start * sr)
            for i in range(int(d * sr)):
                if s0 + i >= len(samples): break
                t = i / sr
                v = math.sin(2*math.pi*freq*t)*.7 + math.sin(4*math.pi*freq*t)*.2
                e = min(t/.02, 1.0) * max(0, 1-(t/d)**1.5) * .3
                samples[s0+i] += v * e

        mx = max(abs(s) for s in samples) or 1.0
        ints = [int(max(-1, min(1, s/mx)) * 32000) for s in samples]
        wav = DATA_DIR / "complete.wav"
        with wave.open(str(wav), "w") as wf:
            wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sr)
            wf.writeframes(struct.pack(f"<{len(ints)}h", *ints))

        try:
            import sounddevice as sd, soundfile as sf
            data, rate = sf.read(str(wav))
            sd.play(data, rate)
            return
        except ImportError:
            pass

        if IS_WIN:
            try:
                import winsound
                winsound.PlaySound(str(wav), winsound.SND_FILENAME | winsound.SND_ASYNC)
                return
            except Exception:
                pass

        if IS_MAC:
            os.system(f'afplay "{wav}" &')
            return

        if IS_LIN:
            os.system(f'aplay "{wav}" 2>/dev/null &')

    except Exception as e:
        log.debug(f"Sound-Fehler: {e}")


# ── Python ↔ JavaScript Bridge ────────────────────────────────────
class RetroDiscBridge:
    """Alle public Methoden sind aus JavaScript via pywebview.api aufrufbar."""

    def __init__(self, window=None):
        self.window = window
        self._loop = asyncio.new_event_loop()
        threading.Thread(
            target=lambda: self._loop.run_forever(),
            daemon=True,
        ).start()

        # Settings
        from src.config.settings import AppSettings
        self.settings = AppSettings.load(DATA_DIR / "settings.json")

        # Tools aus Portable-Ordner eintragen
        tool_paths = find_tools()
        if "ffmpeg"  in tool_paths: self.settings.tools.ffmpeg  = tool_paths["ffmpeg"]
        if "ffprobe" in tool_paths: self.settings.tools.ffprobe = tool_paths["ffprobe"]
        if "ytdlp"   in tool_paths: self.settings.tools.ytdlp   = tool_paths["ytdlp"]

        # Output-Ordner neben der App
        self.settings.directories.output_dir   = DATA_DIR / "Output"
        self.settings.directories.download_dir = DATA_DIR / "Downloads"
        self.settings.directories.temp_dir     = DATA_DIR / "Temp"
        self.settings.ensure_directories()

        # Core-Dienste
        from src.core.ffmpeg    import FFmpeg
        from src.core.pipeline  import Pipeline
        from src.core.downloader import Downloader
        from src.services.converter import Converter
        from src.services.search    import MediaSearch

        self.ffmpeg = FFmpeg(
            self.settings.tools.ffmpeg,
            self.settings.tools.ffprobe,
        )
        self.pipeline = Pipeline(
            max_concurrent=self.settings.conversion.max_concurrent_jobs,
            play_sound=False,
        )
        self.pipeline.on_job_complete = self._on_complete
        self.pipeline.on_job_failed   = self._on_failed

        self.downloader = Downloader(
            ytdlp_path=self.settings.tools.ytdlp,
            output_dir=self.settings.directories.download_dir,
        )
        self.converter = Converter(
            ffmpeg=self.ffmpeg,
            output_dir=self.settings.directories.output_dir,
        )
        self.search = MediaSearch(downloader=self.downloader)
        log.info("Bridge bereit")

    def _run_async(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def _emit(self, event: str, data: dict):
        if self.window:
            payload = json.dumps({"event": event, "data": data})
            try:
                self.window.evaluate_js(
                    f"window.onPythonEvent && window.onPythonEvent({payload})"
                )
            except Exception:
                pass

    def _on_complete(self, job):
        self._emit("job_complete", {
            "id": job.id,
            "name": job.params.get("display_name", job.id),
            "output": str(job.output_path) if job.output_path else None,
        })
        if self.settings.sound.play_on_complete:
            threading.Thread(target=play_completion_sound, daemon=True).start()

    def _on_failed(self, job):
        self._emit("job_failed", {"id": job.id, "error": job.error_message})

    def _submit(self, job):
        self._run_async(self.pipeline.submit(job))
        if not self.pipeline._is_running:
            self._run_async(self.pipeline.start())

    # ── Datei-Dialog ─────────────────────────────────────────────
    def open_file_dialog(self) -> str:
        if self.window:
            result = self.window.create_file_dialog(
                10,
                file_types=(
                    "Mediendateien (*.mp4;*.mkv;*.avi;*.mov;*.mp3;"
                    "*.flac;*.wav;*.iso;*.vob;*.m4v;*.wmv)",
                    "Alle Dateien (*.*)",
                )
            )
            if result and result[0]:
                return self.get_mediainfo(result[0])
        return json.dumps({"error": "Abgebrochen"})

    def open_folder_dialog(self) -> str:
        if self.window:
            import webview as wv
            result = self.window.create_file_dialog(wv.FOLDER_DIALOG)
            if result and result[0]:
                return json.dumps({"folder": result[0]})
        return json.dumps({"error": "Abgebrochen"})

    def open_folder_for_batch(self) -> str:
        return self.open_folder_dialog()

    # ── MediaInfo ─────────────────────────────────────────────────
    def get_mediainfo(self, path: str) -> str:
        future = self._run_async(self.ffmpeg.probe(path))
        try:
            m = future.result(timeout=15)
            return json.dumps({
                "path": str(m.path), "name": m.path.name,
                "type": m.media_type.value, "container": m.container,
                "duration": m.duration_seconds,
                "duration_fmt": m.duration_formatted,
                "size": m.file_size_bytes, "size_fmt": m.file_size_formatted,
                "resolution": m.resolution,
                "video": [{"codec": v.codec, "width": v.width,
                           "height": v.height, "fps": v.fps}
                          for v in m.video_streams],
                "audio": [{"codec": a.codec, "channels": a.channels,
                           "sample_rate": a.sample_rate,
                           "language": a.language or ""}
                          for a in m.audio_streams],
                "subs": [{"codec": s.codec, "lang": s.language or ""}
                         for s in m.subtitle_streams],
                "title": m.title or "", "artist": m.artist or "",
                "album": m.album or "",
            })
        except Exception as e:
            return json.dumps({"error": str(e)})

    def probe_file(self, path: str) -> str:
        return self.get_mediainfo(path)

    # ── Konvertierung ─────────────────────────────────────────────
    def convert_file(self, input_path: str, preset_name: str,
                     output_path: str = "") -> str:
        from src.config.presets import get_preset
        from src.models.media import Job, JobType
        try:
            preset = get_preset(preset_name)
        except ValueError as e:
            return json.dumps({"error": str(e)})
        inp = Path(input_path)
        out = Path(output_path) if output_path else None
        job = Job(
            job_type=JobType.CONVERT, input_files=[inp], output_path=out,
            params={"display_name": f"{inp.name} → {preset.display_name}"},
        )
        async def _h(j):
            r = await self.converter.convert_file(
                j.input_files[0], preset, j.output_path, job=j)
            j.output_path = r
        self.pipeline.register_handler(JobType.CONVERT.value, _h)
        self._submit(job)
        self._emit("job_queued", {"id": job.id, "name": job.params["display_name"]})
        return json.dumps({"job_id": job.id, "status": "queued"})

    def convert_batch(self, folder: str, preset_name: str) -> str:
        from src.models.media import Job, JobType
        job = Job(
            job_type=JobType.CONVERT,
            input_files=[Path(folder)],
            params={"display_name": f"Batch: {Path(folder).name} → {preset_name}"},
        )
        async def _h(j):
            await self.converter.batch_convert(
                j.input_files[0], preset_name,
                output_dir=self.settings.directories.output_dir, job=j)
        self.pipeline.register_handler("batch_" + job.id, _h)
        job.job_type = JobType.CONVERT
        self._submit(job)
        return json.dumps({"job_id": job.id})

    def get_presets(self, category: str = "") -> str:
        from src.config.presets import ALL_PRESETS, get_presets_by_category
        lst = get_presets_by_category(category) if category else ALL_PRESETS
        return json.dumps([{"id": p.name, "name": p.display_name,
                            "category": p.category, "container": p.container}
                           for p in lst])

    # ── DVD-Workflow ──────────────────────────────────────────────
    def create_dvd(self, paths_json: str, title: str = "RetroDisc DVD",
                   standard: str = "PAL", aspect: str = "16:9",
                   burn: bool = False) -> str:
        from src.models.media import Job, JobType
        from src.services.dvd_workflow import DVDWorkflow, DVDProject
        paths = [Path(p) for p in json.loads(paths_json)]
        project = DVDProject(
            title=title, input_files=paths,
            output_dir=self.settings.directories.output_dir,
            standard=standard, aspect=aspect, burn_to_disc=burn,
        )
        job = Job(
            job_type=JobType.BURN_DVD,
            input_files=paths,
            params={"display_name": f"DVD: {title}"},
        )
        wf = DVDWorkflow(ffmpeg=self.ffmpeg)
        async def _h(j):
            iso = await wf.run(project, job=j)
            j.output_path = iso
        self.pipeline.register_handler(JobType.BURN_DVD.value, _h)
        self._submit(job)
        return json.dumps({"job_id": job.id})

    def get_dvd_menu_templates(self) -> str:
        return json.dumps([
            {"id":"classic","name":"Klassisch","desc":"Schwarz/Weiß","preview":"🎬"},
            {"id":"cinema", "name":"Cinema",   "desc":"Roter Vorhang","preview":"🎭"},
            {"id":"retro",  "name":"Retro",    "desc":"VHS-Look",     "preview":"📼"},
            {"id":"minimal","name":"Minimal",  "desc":"Klar/Weiß",    "preview":"◻"},
            {"id":"family", "name":"Familie",  "desc":"Bunt/Freundlich","preview":"👨‍👩‍👧"},
            {"id":"concert","name":"Konzert",  "desc":"Dunkler BG",   "preview":"🎸"},
            {"id":"nature", "name":"Natur",    "desc":"Grün/Organisch","preview":"🌿"},
            {"id":"holiday","name":"Urlaub",   "desc":"Blauer Himmel","preview":"🌅"},
        ])

    def set_dvd_menu(self, template_id: str, title: str,
                     chapters: str = "[]") -> str:
        return json.dumps({"ok": True, "template": template_id, "title": title})

    # ── Download ──────────────────────────────────────────────────
    def download_url(self, url: str, format: str = "best",
                     audio_only: bool = False,
                     after_action: str = "save") -> str:
        from src.models.media import Job, JobType
        job = Job(
            job_type=JobType.DOWNLOAD,
            params={"url": url, "format": format,
                    "audio_only": audio_only,
                    "display_name": f"Download: {url[:50]}"},
        )
        async def _h(j):
            r = await self.downloader.download(
                url=j.params["url"], format=j.params["format"],
                extract_audio=j.params["audio_only"], job=j)
            j.output_path = r
        self.pipeline.register_handler(JobType.DOWNLOAD.value, _h)
        self._submit(job)
        return json.dumps({"job_id": job.id})

    # ── Suche ─────────────────────────────────────────────────────
    def search_media(self, query: str, sources: str = "[]",
                     max_results: int = 15) -> str:
        future = self._run_async(
            self.search.search(query, max_results=max_results)
        )
        try:
            results = future.result(timeout=20)
            return json.dumps([{"title": r.title, "url": r.url,
                                 "source": r.source,
                                 "duration": r.duration_seconds,
                                 "quality": r.quality,
                                 "channel": r.channel}
                                for r in results])
        except Exception as e:
            return json.dumps({"error": str(e)})

    # ── AI Features ───────────────────────────────────────────────
    def create_highlights(self, input_path: str,
                          duration_seconds: int = 300) -> str:
        from src.models.media import Job, JobType, HighlightConfig
        from src.services.smart_edit import SmartEdit
        inp = Path(input_path)
        out = inp.with_stem(inp.stem + "_highlights")
        config = HighlightConfig(target_duration_seconds=duration_seconds)
        editor = SmartEdit(ffmpeg=self.ffmpeg)
        job = Job(
            job_type=JobType.SMART_EDIT, input_files=[inp], output_path=out,
            params={"display_name": f"KI Auto-Edit: {inp.name}"},
        )
        async def _h(j):
            await editor.create_highlights(
                j.input_files[0], j.output_path, config, j)
        self.pipeline.register_handler(JobType.SMART_EDIT.value, _h)
        self._submit(job)
        return json.dumps({"job_id": job.id})

    def generate_subtitles(self, input_path: str, language: str = "",
                           model: str = "base", format: str = "srt") -> str:
        from src.models.media import Job, JobType
        from src.services.subtitle import SubtitleGenerator
        inp = Path(input_path)
        out = inp.with_suffix(f".{format}")
        gen = SubtitleGenerator(model=model)
        job = Job(
            job_type=JobType.SUBTITLE_GENERATE,
            input_files=[inp], output_path=out,
            params={"display_name": f"Untertitel ({model}): {inp.name}"},
        )
        async def _h(j):
            await gen.generate(
                j.input_files[0], j.output_path,
                language=language or None, format=format, job=j)
        self.pipeline.register_handler(JobType.SUBTITLE_GENERATE.value, _h)
        self._submit(job)
        return json.dumps({"job_id": job.id})

    def upscale_video(self, input_path: str, scale: int = 4) -> str:
        from src.models.media import Job, JobType
        from src.services.upscaler import VideoUpscaler
        inp = Path(input_path)
        out = inp.with_stem(f"{inp.stem}_{scale}x")
        upsc = VideoUpscaler()
        job = Job(
            job_type=JobType.UPSCALE, input_files=[inp], output_path=out,
            params={"display_name": f"Upscale {scale}x: {inp.name}"},
        )
        async def _h(j):
            await upsc.upscale(j.input_files[0], j.output_path, scale=scale, job=j)
        self.pipeline.register_handler(JobType.UPSCALE.value, _h)
        self._submit(job)
        return json.dumps({"job_id": job.id})

    def interpolate_video(self, input_path: str,
                          target_fps: float = 60.0) -> str:
        from src.models.media import Job, JobType
        from src.services.upscaler import VideoUpscaler
        inp = Path(input_path)
        out = inp.with_stem(f"{inp.stem}_{int(target_fps)}fps")
        upsc = VideoUpscaler()
        job = Job(
            job_type=JobType.INTERPOLATE, input_files=[inp], output_path=out,
            params={"display_name": f"{target_fps}fps: {inp.name}"},
        )
        async def _h(j):
            await upsc.interpolate(
                j.input_files[0], j.output_path, target_fps, job=j)
        self.pipeline.register_handler(JobType.INTERPOLATE.value, _h)
        self._submit(job)
        return json.dumps({"job_id": job.id})

    def run_assistant(self, command: str) -> str:
        from src.services.assistant import Assistant
        asst = Assistant(
            model=self.settings.ai.ollama_model,
            host=self.settings.ai.ollama_host,
        )
        future = self._run_async(asst.parse_command(command))
        try:
            result = future.result(timeout=30)
            return json.dumps(result)
        except Exception as e:
            return json.dumps({"action": "error", "message": str(e)})

    # ── Bearbeitung ───────────────────────────────────────────────
    def trim_video(self, input_path: str, start: float,
                   end: float, output_path: str = "") -> str:
        from src.models.media import Job, JobType
        inp = Path(input_path)
        out = Path(output_path) if output_path else \
              inp.with_stem(f"{inp.stem}_trim")
        job = Job(
            job_type=JobType.CONVERT, input_files=[inp], output_path=out,
            params={"display_name": f"Trim: {inp.name}"},
        )
        async def _h(j):
            r = await self.ffmpeg.trim(
                j.input_files[0], j.output_path, start, end, j)
            j.output_path = r
        self.pipeline.register_handler("trim_" + job.id, _h)
        job.job_type = JobType.CONVERT
        self._submit(job)
        return json.dumps({"job_id": job.id, "output": str(out)})

    def merge_videos(self, paths_json: str,
                     output_path: str = "") -> str:
        from src.models.media import Job, JobType
        paths = [Path(p) for p in json.loads(paths_json)]
        if not paths:
            return json.dumps({"error": "Keine Dateien"})
        out = Path(output_path) if output_path else \
              paths[0].with_stem("merged_output")
        job = Job(
            job_type=JobType.MERGE, input_files=paths, output_path=out,
            params={"display_name": f"Merge: {len(paths)} Dateien"},
        )
        async def _h(j):
            r = await self.ffmpeg.merge(j.input_files, j.output_path, j)
            j.output_path = r
        self.pipeline.register_handler(JobType.MERGE.value, _h)
        self._submit(job)
        return json.dumps({"job_id": job.id})

    # ── Watch Folder ──────────────────────────────────────────────
    def set_watch_folder(self, folder: str, preset: str,
                         action: str = "convert",
                         enabled: bool = True) -> str:
        try:
            from src.services.watch_folder import WatchFolder, WatchRule
            ALL_EXT = {".mp4",".mkv",".avi",".mov",".wmv",".flv",
                       ".webm",".mpg",".mp3",".flac",".wav",".aac"}
            rule = WatchRule(
                name=f"Auto:{action}", extensions=ALL_EXT,
                action=action, preset=preset, enabled=enabled)
            self._watch = WatchFolder(folder, [rule], self.pipeline)
            if enabled:
                threading.Thread(
                    target=lambda: asyncio.run_coroutine_threadsafe(
                        self._watch.start(), self._loop).result(),
                    daemon=True).start()
            return json.dumps({"ok": True, "folder": folder})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def get_watch_folders(self) -> str:
        wf = getattr(self, "_watch", None)
        if wf:
            return json.dumps([{"folder": str(wf.folder),
                                 "running": wf._running}])
        return json.dumps([])

    # ── Library ───────────────────────────────────────────────────
    def scan_library(self, folder: str) -> str:
        from src.services.library import MediaLibrary
        lib = MediaLibrary(
            db_path=DATA_DIR / "library.db",
            thumb_dir=DATA_DIR / "thumbs",
            ffmpeg=self.ffmpeg,
        )
        lib.open()
        future = self._run_async(
            lib.scan_folder(folder, recursive=True, generate_thumbs=True)
        )
        try:
            n = future.result(timeout=300)
            lib.close()
            return json.dumps({"added": n})
        except Exception as e:
            lib.close()
            return json.dumps({"error": str(e)})

    def get_library(self, media_type: str = "",
                    limit: int = 200) -> str:
        from src.services.library import MediaLibrary
        lib = MediaLibrary(DATA_DIR/"library.db", DATA_DIR/"thumbs")
        lib.open()
        items = lib.get_all(media_type=media_type or None, limit=limit)
        lib.close()
        return json.dumps(items)

    def search_library(self, query: str) -> str:
        from src.services.library import MediaLibrary
        lib = MediaLibrary(DATA_DIR/"library.db", DATA_DIR/"thumbs")
        lib.open()
        items = lib.search(query)
        lib.close()
        return json.dumps(items)

    def get_library_stats(self) -> str:
        from src.services.library import MediaLibrary
        lib = MediaLibrary(DATA_DIR/"library.db", DATA_DIR/"thumbs")
        lib.open()
        stats = lib.get_stats()
        lib.close()
        return json.dumps(stats)

    # ── Queue ─────────────────────────────────────────────────────
    def get_queue(self) -> str:
        jobs = []
        for j in list(self.pipeline._queue) + self.pipeline._running:
            jobs.append({"id": j.id,
                         "name": j.params.get("display_name", j.id),
                         "state": j.state.value, "progress": j.progress})
        for j in self.pipeline.completed_jobs[-20:]:
            jobs.append({"id": j.id,
                         "name": j.params.get("display_name", j.id),
                         "state": j.state.value, "progress": j.progress})
        return json.dumps(jobs)

    def cancel_job(self, job_id: str) -> str:
        future = self._run_async(self.pipeline.cancel_job(job_id))
        ok = future.result(timeout=5)
        return json.dumps({"ok": ok})

    def clear_completed(self) -> str:
        self.pipeline.clear_completed()
        return json.dumps({"ok": True})

    def open_output_folder(self) -> str:
        path = str(self.settings.directories.output_dir)
        if IS_WIN:   os.startfile(path)
        elif IS_MAC: os.system(f'open "{path}"')
        else:        os.system(f'xdg-open "{path}"')
        return json.dumps({"ok": True})

    # ── Settings ──────────────────────────────────────────────────
    def get_settings(self) -> str:
        return self.settings.model_dump_json()

    def save_settings(self, data: str) -> str:
        try:
            from src.config.settings import AppSettings
            self.settings = AppSettings.model_validate_json(data)
            self.settings.save(DATA_DIR / "settings.json")
            self.ffmpeg.ffmpeg_path  = self.settings.tools.ffmpeg
            self.ffmpeg.ffprobe_path = self.settings.tools.ffprobe
            self.downloader.ytdlp_path = self.settings.tools.ytdlp
            return json.dumps({"ok": True})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def check_tools(self) -> str:
        tools = find_tools()
        status = {}
        for name in ("ffmpeg", "ffprobe", "ytdlp"):
            status[name] = {
                "available": name in tools,
                "path": tools.get(name, ""),
            }
        return json.dumps(status)

    def play_sound(self) -> str:
        threading.Thread(target=play_completion_sound, daemon=True).start()
        return json.dumps({"ok": True})

    def splash_complete(self):
        log.info("Splash fertig")


# ── Download-Splash ───────────────────────────────────────────────
def run_download_splash(missing: list) -> None:
    """Zeigt Splash während fehlende Tools geladen werden."""
    try:
        import webview
        splash_html = BUNDLE_DIR / "src" / "ui" / "splash.html"
        url = str(splash_html) if splash_html.exists() else \
              "data:text/html,<h2 style='font-family:Tahoma;padding:20px'>Lade Tools...</h2>"

        w = [None]

        def do_dl():
            def progress(label, pct):
                if w[0]:
                    try:
                        w[0].evaluate_js(
                            f"document.getElementById('progbar') && "
                            f"(document.getElementById('progbar').style.width='{pct:.0f}%');"
                            f"document.getElementById('statusText') && "
                            f"(document.getElementById('statusText').textContent='{label}: {pct:.0f}%');"
                        )
                    except Exception:
                        pass

            download_missing_tools(missing, progress)

            if w[0]:
                try:
                    w[0].evaluate_js(
                        "document.getElementById('statusText') && "
                        "(document.getElementById('statusText').textContent='Fertig! RetroDisc startet...');"
                        "document.getElementById('progbar') && "
                        "(document.getElementById('progbar').style.width='100%');"
                    )
                except Exception:
                    pass
            import time; time.sleep(1.5)
            if w[0]:
                try: w[0].destroy()
                except Exception: pass

        win = webview.create_window(
            "RetroDisc — Ersteinrichtung",
            url=url, width=420, height=280,
            resizable=False, on_top=True,
        )
        w[0] = win
        threading.Thread(target=do_dl, daemon=True).start()
        webview.start()

    except Exception as e:
        log.warning(f"Splash-Fehler: {e} — lade Tools direkt")
        download_missing_tools(missing)


# ── Hauptprogramm ─────────────────────────────────────────────────
def main():
    log.info("=" * 50)
    log.info(f"RetroDisc startet | {SYSTEM} {MACHINE}")
    log.info(f"Portable: {PORTABLE} | BASE: {BASE_DIR}")
    log.info("=" * 50)

    try:
        import webview
    except ImportError:
        log.error("PyWebView fehlt — öffne im Browser")
        import webbrowser
        html = BUNDLE_DIR / "src" / "ui" / "app.html"
        webbrowser.open(f"file:///{html}")
        input("Enter zum Beenden...")
        return

    # Fehlende Tools prüfen und laden
    tools = find_tools()
    missing = [t for t in ("ffmpeg", "ytdlp") if t not in tools]
    if missing:
        log.info(f"Fehlende Tools: {missing}")
        run_download_splash(missing)

    # Settings + Bridge
    bridge = RetroDiscBridge()

    # UI-Datei
    ui_html = BUNDLE_DIR / "src" / "ui" / "app.html"
    if not ui_html.exists():
        log.error(f"UI nicht gefunden: {ui_html}")
        sys.exit(1)

    # Fenstergröße je Plattform
    width, height = 1280, 820
    if IS_MAC:
        width, height = 1200, 780  # macOS hat Menüleiste

    window = webview.create_window(
        title="RetroDisc 1.0",
        url=f"file:///{ui_html}",
        js_api=bridge,
        width=width, height=height,
        min_size=(960, 640),
        background_color="#3A6EA5",
        text_select=False,
    )
    bridge.window = window

    debug = os.environ.get("RETRODISC_DEBUG", "0") == "1"
    log.info(f"Starte Fenster (debug={debug})")

    webview.start(debug=debug, http_server=True)
    log.info("RetroDisc beendet.")


if __name__ == "__main__":
    main()
