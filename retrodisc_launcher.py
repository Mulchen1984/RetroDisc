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
from pathlib import Path


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
        )
        self.converter = Converter(
            ffmpeg=self.ffmpeg,
            output_dir=self.settings.directories.output_dir,
        )
        self.search = MediaSearch(downloader=self.downloader)

        log.info("Bridge initialisiert")

    def _async(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def _emit(self, event: str, data: dict):
        if self.window:
            payload = json.dumps({"event": event, "data": data})
            self.window.evaluate_js(f"window.onPythonEvent && window.onPythonEvent({payload})")

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

    # ── Datei-Dialog ──────────────────────────────────────────────────
    def open_file_dialog(self) -> str:
        if self.window:
            result = self.window.create_file_dialog(
                10,  # OPEN_DIALOG
                file_types=(
                    "Mediendateien (*.mp4;*.mkv;*.avi;*.mov;*.mp3;*.flac;*.wav;*.iso;*.vob)",
                    "Alle Dateien (*.*)",
                )
            )
            if result and result[0]:
                return self.probe_file(result[0])
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
                "size_formatted": m.file_size_formatted,
                "resolution": m.resolution,
                "video_codec": m.video_streams[0].codec if m.video_streams else None,
                "audio_codec": m.audio_streams[0].codec if m.audio_streams else None,
            })
        except Exception as e:
            return json.dumps({"error": str(e)})

    # ── Konvertierung ─────────────────────────────────────────────────
    def convert_file(self, input_path: str, preset_name: str,
                     output_path: str = None) -> str:
        from src.config.presets import get_preset
        from src.models.media import Job, JobType

        try:
            preset = get_preset(preset_name)
        except ValueError as e:
            return json.dumps({"error": str(e)})

        job = Job(
            job_type=JobType.CONVERT,
            input_files=[Path(input_path)],
            output_path=Path(output_path) if output_path else None,
            params={"display_name": f"{Path(input_path).name} -> {preset.display_name}"},
        )

        async def _handler(j):
            result = await self.converter.convert_file(
                Path(input_path), preset, j.output_path, job=j
            )
            j.output_path = result

        self.pipeline.register_handler(JobType.CONVERT.value, _handler)
        self._async(self.pipeline.submit(job))
        if not self.pipeline._is_running:
            self._async(self.pipeline.start())

        self._emit("job_queued", {"id": job.id,
                                  "name": job.params["display_name"]})
        return json.dumps({"job_id": job.id, "status": "queued"})

    def get_presets(self, category: str = None) -> str:
        from src.config.presets import ALL_PRESETS, get_presets_by_category
        presets = ALL_PRESETS if not category else get_presets_by_category(category)
        return json.dumps([{
            "id": p.name, "name": p.display_name,
            "category": p.category, "container": p.container,
        } for p in presets])

    # ── Download ──────────────────────────────────────────────────────
    def download_url(self, url: str, audio_only: bool = False,
                     format: str = "best") -> str:
        from src.models.media import Job, JobType

        job = Job(
            job_type=JobType.DOWNLOAD,
            params={"url": url, "audio_only": audio_only, "format": format,
                    "display_name": f"Download: {url[:50]}"},
        )

        async def _handler(j):
            result = await self.downloader.download(
                url=j.params["url"],
                format=j.params["format"],
                extract_audio=j.params["audio_only"],
                job=j,
            )
            j.output_path = result

        self.pipeline.register_handler(JobType.DOWNLOAD.value, _handler)
        self._async(self.pipeline.submit(job))
        if not self.pipeline._is_running:
            self._async(self.pipeline.start())

        return json.dumps({"job_id": job.id, "status": "queued"})

    # ── Suche ─────────────────────────────────────────────────────────
    def search_media(self, query: str, max_results: int = 15) -> str:
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

    def save_settings(self, data: str) -> str:
        try:
            from src.config.settings import AppSettings
            self.settings = AppSettings.model_validate_json(data)
            self.settings.save()
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

    # ── Splash fertig ─────────────────────────────────────────────────
    def splash_complete(self):
        """Wird vom Splash-Screen aufgerufen wenn er fertig ist."""
        log.info("Splash fertig - lade Haupt-UI")
        if self.window:
            ui_html = BUNDLE_DIR / "src" / "ui" / "app.html"
            self.window.load_url(f"file:///{ui_html}")


# ── Download-Splash (zeigt Fortschritt beim ersten Start) ─────────────
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

        splash_html = (BUNDLE_DIR / "src" / "ui" / "splash.html")
        if splash_html.exists():
            url = f"file:///{splash_html}"
        else:
            url = "data:text/html,<h2 style='font-family:Arial;padding:20px'>Lade Tools...</h2>"

        w = webview.create_window(
            "RetroDisc - Ersteinrichtung",
            url=url,
            width=440, height=300,
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

    # Haupt-Fenster
    ui_html = BUNDLE_DIR / "src" / "ui" / "app.html"
    window = webview.create_window(
        title="RetroDisc 1.0",
        url=f"file:///{ui_html}",
        js_api=bridge,
        width=1280,
        height=820,
        min_size=(960, 640),
        background_color="#d4d0c8",
        text_select=False,
    )
    bridge.window = window

    log.info("Starte Fenster...")
    webview.start(
        debug=os.environ.get("RETRODISC_DEBUG", "0") == "1",
        http_server=True,
    )
    log.info("RetroDisc beendet.")


if __name__ == "__main__":
    main()
