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
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "retrodisc.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
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

    for name, exes in [
        ("ffmpeg",  ["ffmpeg.exe",  "ffmpeg"]),
        ("ffprobe", ["ffprobe.exe", "ffprobe"]),
        ("ytdlp",   ["yt-dlp.exe",  "yt-dlp"]),
    ]:
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

        if "ffmpeg" in tool_paths:
            self.settings.tools.ffmpeg = tool_paths["ffmpeg"]
        if "ffprobe" in tool_paths:
            self.settings.tools.ffprobe = tool_paths["ffprobe"]
        if "ytdlp" in tool_paths:
            self.settings.tools.ytdlp = tool_paths["ytdlp"]

        self.settings.ensure_directories()

        # Core-Module
        from src.core.ffmpeg import FFmpeg
        from src.core.pipeline import Pipeline
        from src.core.downloader import Downloader
        from src.services.converter import Converter
        from src.services.search import MediaSearch
        from src.core.disc import DiscTools
        from src.services.dvd_workflow import DVDWorkflow
        from src.services.library import MediaLibrary

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
        self.disc = DiscTools(
            dvdauthor_path=str(dvd_bin / "dvdauthor.exe") if (dvd_bin / "dvdauthor.exe").is_file() else self.settings.tools.dvdauthor,
            mkisofs_path=str(dvd_bin / "mkisofs.exe") if (dvd_bin / "mkisofs.exe").is_file() else self.settings.tools.mkisofs,
            growisofs_path=str(dvd_bin / "growisofs.exe") if (dvd_bin / "growisofs.exe").is_file() else self.settings.tools.growisofs,
            cdrecord_path=self.settings.tools.cdrecord,
            mediainfo_path=str(dvd_bin / "dvd+rw-mediainfo.exe") if (dvd_bin / "dvd+rw-mediainfo.exe").is_file() else None,
        )
        self.dvd_workflow = DVDWorkflow(
            ffmpeg=self.ffmpeg,
            disc_tools=self.disc,
            temp_dir=self.settings.directories.temp_dir,
        )
        self.library = MediaLibrary(ffmpeg=self.ffmpeg)
        self.library.open()
        self._watch = None

        log.info("Bridge initialisiert")

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
        self._emit("job_done", {
            "id": job.id,
            "name": job.params.get("display_name", job.id),
            "type": job.job_type.value,
            "output": str(job.output_path) if job.output_path else None,
            "elapsed": round(job.elapsed_seconds, 1),
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
                    "Mediendateien (*.mp4;*.mkv;*.avi;*.mov;*.mp3;*.flac;*.wav;*.iso;*.vob)",
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
                     output_path: str = None, overwrite: bool = False) -> str:
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
                    "overwrite": bool(overwrite)},
        )
        async def _handler(j):
            result = await self.converter.convert_file(
                j.input_files[0], j.preset, j.output_path, job=j,
                overwrite=j.params["overwrite"],
            )
            j.output_path = result

        return self._submit_job(job, _handler)

    def get_presets(self, category: str = None) -> str:
        from src.config.presets import ALL_PRESETS, get_presets_by_category
        presets = ALL_PRESETS if not category else get_presets_by_category(category)
        return json.dumps([{
            "id": p.name, "name": p.display_name,
            "category": p.category, "container": p.container,
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
            result = await self.downloader.download(
                url=j.params["url"],
                format=j.params["format"],
                extract_audio=j.params["audio_only"],
                audio_format=j.params["audio_format"],
                subtitles=j.params["subtitles"],
                job=j,
            )
            j.output_path = result

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
                         "progress": j.progress})
        for j in self.pipeline.completed_jobs[-20:]:
            jobs.append({"id": j.id,
                         "name": j.params.get("display_name", j.id),
                         "state": j.state.value,
                         "progress": j.progress})
        return json.dumps(jobs)

    # ── Settings ──────────────────────────────────────────────────────
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

    def _apply_runtime_settings(self) -> None:
        """Apply persisted paths/directories to already-created services."""
        tools = self.settings.tools
        directories = self.settings.directories
        self.ffmpeg.ffmpeg_path = tools.ffmpeg
        self.ffmpeg.ffprobe_path = tools.ffprobe
        self.converter.output_dir = directories.output_dir
        self.downloader.ytdlp_path = tools.ytdlp
        self.downloader.ffmpeg_path = tools.ffmpeg
        self.downloader.output_dir = directories.download_dir
        self.disc.dvdauthor = tools.dvdauthor
        self.disc.mkisofs = tools.mkisofs
        self.disc.growisofs = tools.growisofs
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
            new_settings.save()
            self.settings = new_settings
            self._apply_runtime_settings()
            return json.dumps({"ok": True})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def get_tool_status(self) -> str:
        tools = check_tools()
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

    def open_output_folder(self) -> str:
        try:
            import os
            path = self.settings.directories.output_dir
            os.startfile(str(path))
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
            return json.dumps(info)
        except Exception as exc:
            return json.dumps({"error": str(exc), "device": device})

    # ── Gemeinsame Queue-Hilfe ─────────────────────────────────────────
    def _submit_job(self, job, handler) -> str:
        """Stellt Job und dessen unverwechselbaren Handler sicher in die Queue."""
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
                   eject: Optional[bool] = None) -> str:
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
            )
            j.output_path = await self.dvd_workflow.run(project, job=j)

        return self._submit_job(job, _handler)

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
            JobType.RIP_DVD, output_path=output,
            params={"device": device, "format": output_format,
                    "display_name": f"Disc {device} -> {output.name}"},
        )

        async def _handler(j):
            from src.services.ripper import DiscRipper
            ripper = DiscRipper(self.ffmpeg, self.disc)
            j.output_path = await ripper.rip(
                j.params["device"], j.output_path, j.params["format"], job=j)

        return self._submit_job(job, _handler)

    # ── KI/Medienwerkzeuge ─────────────────────────────────────────────
    def create_highlights(self, input_path: str, duration_seconds: int = 300) -> str:
        from src.models.media import Job, JobType, HighlightConfig
        source = Path(input_path)
        if not source.is_file():
            return json.dumps({"error": f"Datei nicht gefunden: {source}"})
        output = self.settings.directories.output_dir / f"{source.stem}_highlights.mp4"
        job = Job(JobType.SMART_EDIT, input_files=[source], output_path=output,
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
        job = Job(JobType.SUBTITLE_GENERATE, input_files=[source], output_path=output,
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
        job = Job(JobType.UPSCALE, input_files=[source], output_path=output,
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
        job = Job(JobType.INTERPOLATE, input_files=[source], output_path=output,
                  params={"target_fps": fps,
                          "display_name": f"Interpolation {fps:g} fps: {source.name}"})

        async def _handler(j):
            from src.services.upscaler import VideoUpscaler
            up = VideoUpscaler(ffmpeg_path=self.settings.tools.ffmpeg)
            j.output_path = await up.interpolate(
                j.input_files[0], j.output_path,
                target_fps=j.params["target_fps"], job=j)

        return self._submit_job(job, _handler)

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
        job = Job(JobType.TRIM, input_files=[source], output_path=output,
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
            preview_dir = Path.home() / ".retrodisc" / "preview"
            preview_dir.mkdir(parents=True, exist_ok=True)
            preview = preview_dir / f"{source.stem}_preview.mp4"
            preview.unlink(missing_ok=True)
            result = self._async(
                self.ffmpeg.trim(source, preview, start, min(end, start + 20.0))
            ).result(timeout=180)
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
        job = Job(JobType.MERGE, input_files=paths, output_path=output,
                  params={"display_name": f"Merge: {len(paths)} Dateien"})

        async def _handler(j):
            j.output_path = await self.ffmpeg.merge(j.input_files, j.output_path, job=j)

        return self._submit_job(job, _handler)

    def convert_batch(self, paths_json: str, preset: str,
                      output_path: str = "", overwrite: bool = False) -> str:
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
                path, preset, str(item_output) if item_output else None, overwrite))
            if result.get("job_id"):
                ids.append(result["job_id"])
            elif result.get("error"):
                errors.append({"path": path, "error": result["error"]})
        return json.dumps({"job_ids": ids, "count": len(ids), "errors": errors})

    def cancel_job(self, job_id: str) -> str:
        try:
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
                        JobType.BURN_DVD, input_files=[file_path],
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
                        JobType.CONVERT, input_files=[file_path], preset=selected_preset,
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
    def open_output_folder(self): return self._bridge.open_output_folder()
    def probe_file(self, path): return self._bridge.probe_file(path)
    def get_mediainfo(self, path): return self._bridge.probe_file(path)
    def convert_file(self, input_path, preset_name, output_path=None, overwrite=False): return self._bridge.convert_file(input_path, preset_name, output_path, overwrite)
    def convert_batch(self, *args): return self._bridge.convert_batch(*args)
    def get_presets(self, category=None): return self._bridge.get_presets(category)
    def download_url(self, url, format="best", audio_only=False, subtitles=False): return self._bridge.download_url(url, format, audio_only, subtitles)
    def search_media(self, query, sources="[]", max_results=15): return self._bridge.search_media(query, sources, max_results)
    def get_queue(self): return self._bridge.get_queue()
    def clear_completed(self): return self._bridge.clear_completed()
    def get_settings(self): return self._bridge.get_settings()
    def save_settings(self, data): return self._bridge.save_settings(data)
    def get_tool_status(self): return self._bridge.get_tool_status()
    def check_tools(self): return self._bridge.check_tools()
    def play_sound(self): return self._bridge.play_sound()
    def detect_burners(self): return self._bridge.detect_burners()
    def get_disc_info(self, *args): return self._bridge.get_disc_info(*args)
    def create_dvd(self, *args): return self._bridge.create_dvd(*args)
    def rip_disc(self, *args): return self._bridge.rip_disc(*args)
    def create_highlights(self, *args): return self._bridge.create_highlights(*args)
    def generate_subtitles(self, *args): return self._bridge.generate_subtitles(*args)
    def upscale_video(self, *args): return self._bridge.upscale_video(*args)
    def interpolate_video(self, *args): return self._bridge.interpolate_video(*args)
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

    def cancel_job(self, *args): return self._bridge.cancel_job(*args)
    def splash_complete(self): return self._bridge.splash_complete()


# ── Download-Splash (zeigt Fortschritt beim ersten Start) ─────────────
def get_splash_url() -> str:
    """Return the local startup page URL without WebView2's HTML-size limit."""
    return (BUNDLE_DIR / "src" / "ui" / "splash.html").resolve().as_uri()


def show_download_splash(missing_tools: list) -> None:
    """Zeigt einen Splash mit Download-Fortschritt für fehlende Tools."""
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
def main():
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
        )
    bridge.window = window

    debug = os.environ.get("RETRODISC_DEBUG", "0") == "1"
    log.info(f"Starte Fenster (debug={debug})")
    try:
        webview.start(debug=debug)
    finally:
        bridge.shutdown()
    log.info("RetroDisc beendet.")


if __name__ == "__main__":
    main()
