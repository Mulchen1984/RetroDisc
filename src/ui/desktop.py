"""RetroDisc Desktop Bridge — Vollständige PyWebView ↔ Python Verbindung."""

from __future__ import annotations

import asyncio
import json
import os
import threading
import structlog
from pathlib import Path
from typing import Optional

from src.config.settings import AppSettings
from src.config.presets import get_preset, ALL_PRESETS, get_presets_by_category
from src.core.ffmpeg import FFmpeg, FFmpegNotFoundError
from src.core.downloader import Downloader
from src.core.disc import DiscTools
from src.core.pipeline import Pipeline
from src.models.media import Job, JobType
from src.services.converter import Converter
from src.services.search import MediaSearch
from src.services.library import MediaLibrary
from src.services.dvd_workflow import DVDWorkflow, DVDProject
from src.utils.sound import play_completion_sound

log = structlog.get_logger()


class RetroDiscAPI:
    """JavaScript ↔ Python Bridge für PyWebView."""

    def __init__(self, window=None):
        self.window = window
        self.settings = AppSettings.load()
        self.settings.ensure_directories()

        self.ffmpeg = FFmpeg(
            ffmpeg_path=self.settings.tools.ffmpeg,
            ffprobe_path=self.settings.tools.ffprobe,
        )
        self.downloader = Downloader(
            ytdlp_path=self.settings.tools.ytdlp,
            output_dir=self.settings.directories.download_dir,
        )
        self.disc = DiscTools()
        self.converter = Converter(ffmpeg=self.ffmpeg,
                                   output_dir=self.settings.directories.output_dir)
        self.search_engine = MediaSearch(downloader=self.downloader)
        self.dvd_workflow = DVDWorkflow(ffmpeg=self.ffmpeg, disc_tools=self.disc,
                                        temp_dir=self.settings.directories.temp_dir)
        self.library = MediaLibrary(ffmpeg=self.ffmpeg)
        self.library.open()

        self.pipeline = Pipeline(
            max_concurrent=self.settings.conversion.max_concurrent_jobs,
            play_sound=self.settings.sound.play_on_complete,
        )
        self._register_handlers()
        self.pipeline.on_job_complete = self._on_job_complete
        self.pipeline.on_job_failed   = self._on_job_failed
        self.pipeline.on_queue_empty  = self._on_queue_empty

        self._loop = asyncio.new_event_loop()
        self._bg = threading.Thread(target=self._run_loop, daemon=True)
        self._bg.start()

        self._run_async(self.pipeline.start())
        self._run_async(self._startup_check())

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _run_async(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def _emit(self, event: str, data: dict = None):
        if not self.window:
            return
        payload = json.dumps({"event": event, "data": data or {}})
        try:
            self.window.evaluate_js(
                f"window.onBackendEvent && window.onBackendEvent({payload})")
        except Exception:
            pass

    def _pcb(self, job: Job):
        self._emit("job_progress", {
            "id": job.id, "progress": round(job.progress, 1),
            "status": job.progress_text,
            "name": job.params.get("display_name", job.id),
        })

    def _on_job_complete(self, job: Job):
        self._emit("job_done", {
            "id": job.id, "name": job.params.get("display_name", job.id),
            "elapsed": round(job.elapsed_seconds, 1),
            "output": str(job.output_path) if job.output_path else None,
        })

    def _on_job_failed(self, job: Job):
        self._emit("job_failed", {
            "id": job.id, "name": job.params.get("display_name", job.id),
            "error": job.error_message or "Unbekannter Fehler",
        })

    def _on_queue_empty(self):
        self._emit("queue_empty", {})

    def _submit(self, job: Job) -> str:
        self._run_async(self.pipeline.submit(job))
        self._emit("job_queued", {
            "id": job.id,
            "name": job.params.get("display_name", job.id),
            "type": job.job_type.value,
        })
        return json.dumps({"job_id": job.id, "status": "queued"})

    def _register_handlers(self):
        async def h_convert(job):
            job.on_progress = lambda p, t: self._pcb(job)
            result = await self.converter.convert_file(
                input_path=job.input_files[0],
                preset=job.params.get("preset", "mp4_h264_1080p"),
                output_path=job.output_path, job=job)
            job.output_path = result

        async def h_download(job):
            job.on_progress = lambda p, t: self._pcb(job)
            result = await self.downloader.download(
                url=job.params["url"],
                format=job.params.get("format", "best"),
                extract_audio=job.params.get("audio_only", False),
                subtitles=job.params.get("subtitles", False),
                job=job)
            job.output_path = result
            # Nach-Download-Aktion
            after = job.params.get("after_action", "save")
            if after == "burn_dvd" and result:
                j2 = Job(job_type=JobType.BURN_DVD, input_files=[result],
                         params={"title": result.stem, "only_iso": True,
                                 "display_name": f"{result.stem} → DVD"})
                await self.pipeline.submit(j2)

        async def h_dvd(job):
            job.on_progress = lambda p, t: self._pcb(job)
            project = DVDProject(
                title=job.params.get("title", "RetroDisc"),
                input_files=job.input_files,
                output_dir=self.settings.directories.output_dir,
                standard=job.params.get("standard", "PAL"),
                aspect=job.params.get("aspect", "16:9"),
                burn_to_disc=job.params.get("burn_to_disc", False),
                only_iso=job.params.get("only_iso", True),
            )
            job.output_path = await self.dvd_workflow.run(project, job=job)

        async def h_smart_edit(job):
            from src.services.smart_edit import SmartEdit
            from src.models.media import HighlightConfig
            job.on_progress = lambda p, t: self._pcb(job)
            editor = SmartEdit(ffmpeg=self.ffmpeg)
            cfg = HighlightConfig(target_duration_seconds=job.params.get("duration", 300))
            job.output_path = await editor.create_highlights(
                job.input_files[0], job.output_path, cfg, job)

        async def h_subtitle(job):
            from src.services.subtitle import SubtitleGenerator
            job.on_progress = lambda p, t: self._pcb(job)
            gen = SubtitleGenerator(model=job.params.get("model", "base"))
            job.output_path = await gen.generate(
                job.input_files[0], job.output_path,
                language=job.params.get("language"),
                format=job.params.get("format", "srt"), job=job)

        async def h_upscale(job):
            from src.services.upscaler import VideoUpscaler
            job.on_progress = lambda p, t: self._pcb(job)
            up = VideoUpscaler()
            job.output_path = await up.upscale(
                job.input_files[0], job.output_path,
                scale=job.params.get("scale", 4), job=job)

        async def h_interpolate(job):
            from src.services.upscaler import VideoUpscaler
            job.on_progress = lambda p, t: self._pcb(job)
            up = VideoUpscaler()
            job.output_path = await up.interpolate(
                job.input_files[0], job.output_path,
                target_fps=job.params.get("target_fps", 60.0), job=job)

        self.pipeline.register_handler(JobType.CONVERT.value,           h_convert)
        self.pipeline.register_handler(JobType.DOWNLOAD.value,          h_download)
        self.pipeline.register_handler(JobType.MEDIATHEK_DOWNLOAD.value,h_download)
        self.pipeline.register_handler(JobType.BURN_DVD.value,          h_dvd)
        self.pipeline.register_handler(JobType.SMART_EDIT.value,        h_smart_edit)
        self.pipeline.register_handler(JobType.SUBTITLE_GENERATE.value, h_subtitle)
        self.pipeline.register_handler(JobType.UPSCALE.value,           h_upscale)
        self.pipeline.register_handler(JobType.INTERPOLATE.value,       h_interpolate)

    async def _startup_check(self):
        tools = {}
        try:
            v = await self.ffmpeg.validate()
            tools["ffmpeg"]  = {"ok": True, "version": v.get("ffmpeg",  "?")}
            tools["ffprobe"] = {"ok": True, "version": v.get("ffprobe", "?")}
        except FFmpegNotFoundError as e:
            tools["ffmpeg"] = tools["ffprobe"] = {"ok": False, "error": str(e)}
        try:
            v = await self.downloader.validate()
            tools["ytdlp"] = {"ok": True, "version": v}
        except Exception as e:
            tools["ytdlp"] = {"ok": False, "error": str(e)}
        self._emit("tools_ready", tools)

    # ── PUBLIC API ────────────────────────────────────────────────────

    def open_file_dialog(self) -> str:
        if not self.window:
            return json.dumps({"files": []})
        result = self.window.create_file_dialog(
            dialog_type=10, allow_multiple=True,
            file_types=("Medien (*.mp4;*.mkv;*.avi;*.mp3;*.flac;*.wav;*.iso)",
                        "Alle Dateien (*.*)"))
        if not result:
            return json.dumps({"files": []})
        files = []
        for path in result:
            try:
                m = self._run_async(self.ffmpeg.probe(path)).result(timeout=10)
                files.append({
                    "path": str(m.path), "name": m.path.name,
                    "type": m.media_type.value, "size": m.file_size_formatted,
                    "duration": m.duration_formatted, "resolution": m.resolution,
                })
            except Exception as e:
                files.append({"path": path, "name": Path(path).name,
                               "type": "unknown", "error": str(e)})
        return json.dumps({"files": files})

    def open_folder_dialog(self) -> str:
        if not self.window:
            return json.dumps({"folder": None})
        result = self.window.create_file_dialog(dialog_type=50)
        return json.dumps({"folder": result[0] if result else None})

    def probe_file(self, path: str) -> str:
        try:
            m = self._run_async(self.ffmpeg.probe(path)).result(timeout=15)
            return json.dumps({
                "path": str(m.path), "name": m.path.name,
                "type": m.media_type.value, "container": m.container,
                "duration": m.duration_seconds, "duration_fmt": m.duration_formatted,
                "size": m.file_size_bytes, "size_fmt": m.file_size_formatted,
                "resolution": m.resolution,
                "fps":    m.video_streams[0].fps    if m.video_streams else None,
                "codec_v":m.video_streams[0].codec  if m.video_streams else None,
                "codec_a":m.audio_streams[0].codec  if m.audio_streams else None,
                "has_subs": len(m.subtitle_streams) > 0,
                "title": m.title, "artist": m.artist,
            })
        except Exception as e:
            return json.dumps({"error": str(e)})

    def convert_file(self, input_path: str, preset: str,
                     output_path: Optional[str] = None) -> str:
        try:
            p = get_preset(preset)
        except ValueError as e:
            return json.dumps({"error": str(e)})
        inp = Path(input_path)
        out = Path(output_path) if output_path else (
            self.settings.directories.output_dir / f"{inp.stem}_{preset}.{p.container}")
        job = Job(job_type=JobType.CONVERT, input_files=[inp], output_path=out,
                  params={"preset": preset,
                          "display_name": f"{inp.name} → {p.container.upper()}"})
        return self._submit(job)

    def convert_batch(self, paths_json: str, preset: str) -> str:
        try:
            paths = json.loads(paths_json)
        except Exception:
            return json.dumps({"error": "Ungültige Pfad-Liste"})
        ids = [json.loads(self.convert_file(p, preset)).get("job_id") for p in paths]
        return json.dumps({"job_ids": [i for i in ids if i], "count": len(paths)})

    def get_presets(self, category: str = "") -> str:
        items = ALL_PRESETS if not category else get_presets_by_category(category)
        return json.dumps([{
            "id": p.name, "name": p.display_name, "category": p.category,
            "container": p.container, "description": p.description,
        } for p in items])

    def create_dvd(self, paths_json: str, title: str = "RetroDisc DVD",
                   standard: str = "PAL", aspect: str = "16:9",
                   burn: bool = False) -> str:
        try:
            paths = [Path(p) for p in json.loads(paths_json)]
        except Exception:
            return json.dumps({"error": "Ungültige Pfad-Liste"})
        job = Job(job_type=JobType.BURN_DVD, input_files=paths,
                  params={"title": title, "standard": standard, "aspect": aspect,
                          "burn_to_disc": burn, "only_iso": not burn,
                          "display_name": f"{title} → {'Brennen' if burn else 'ISO'}"})
        return self._submit(job)

    def download_url(self, url: str, format: str = "best",
                     audio_only: bool = False, after_action: str = "save",
                     subtitles: bool = False) -> str:
        short = (url[:52] + "...") if len(url) > 52 else url
        job = Job(job_type=JobType.DOWNLOAD,
                  params={"url": url, "format": "bestaudio" if audio_only else format,
                          "audio_only": audio_only, "subtitles": subtitles,
                          "after_action": after_action,
                          "display_name": f"⬇ {short}"})
        return self._submit(job)

    def search_media(self, query: str, sources: str = "[]",
                     max_results: int = 15) -> str:
        src = json.loads(sources) if sources != "[]" else None
        try:
            results = self._run_async(
                self.search_engine.search(query, sources=src,
                                          max_results=max_results)).result(timeout=20)
            return json.dumps([{
                "title": r.title, "url": r.url, "source": r.source,
                "duration_fmt": self._fmt_dur(r.duration_seconds),
                "thumbnail": r.thumbnail_url, "quality": r.quality,
            } for r in results])
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _fmt_dur(self, s) -> str:
        if not s: return ""
        h, r = divmod(int(s), 3600); m, sec = divmod(r, 60)
        return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"

    def create_highlights(self, input_path: str, duration_seconds: int = 300) -> str:
        inp = Path(input_path)
        job = Job(job_type=JobType.SMART_EDIT, input_files=[inp],
                  output_path=inp.with_stem(inp.stem + "_highlights"),
                  params={"duration": duration_seconds,
                          "display_name": f"🎬 Auto-Edit: {inp.name}"})
        return self._submit(job)

    def generate_subtitles(self, input_path: str, language: str = "",
                           model: str = "base", fmt: str = "srt") -> str:
        inp = Path(input_path)
        job = Job(job_type=JobType.SUBTITLE_GENERATE, input_files=[inp],
                  output_path=inp.with_suffix(f".{fmt}"),
                  params={"model": model, "language": language or None, "format": fmt,
                          "display_name": f"💬 Untertitel: {inp.name}"})
        return self._submit(job)

    def upscale_video(self, input_path: str, scale: int = 4) -> str:
        inp = Path(input_path)
        job = Job(job_type=JobType.UPSCALE, input_files=[inp],
                  output_path=inp.with_stem(f"{inp.stem}_{scale}x"),
                  params={"scale": scale,
                          "display_name": f"🔭 Upscale {scale}x: {inp.name}"})
        return self._submit(job)

    def interpolate_video(self, input_path: str, target_fps: float = 60.0) -> str:
        inp = Path(input_path)
        job = Job(job_type=JobType.INTERPOLATE, input_files=[inp],
                  output_path=inp.with_stem(f"{inp.stem}_{int(target_fps)}fps"),
                  params={"target_fps": target_fps,
                          "display_name": f"🎞 {target_fps}fps: {inp.name}"})
        return self._submit(job)

    def run_assistant(self, prompt: str) -> str:
        try:
            return self._run_async(self._do_assistant(prompt)).result(timeout=30)
        except Exception as e:
            return json.dumps({"error": str(e)})

    async def _do_assistant(self, prompt: str) -> str:
        from src.services.assistant import Assistant
        ass = Assistant(model=self.settings.ai.ollama_model,
                        host=self.settings.ai.ollama_host)
        result = await ass.parse_command(prompt)
        return json.dumps(result)

    def get_queue(self) -> str:
        jobs = []
        for j in list(self.pipeline._queue):
            jobs.append({"id": j.id, "name": j.params.get("display_name", j.id),
                         "state": "pending", "progress": 0})
        for j in self.pipeline._running:
            jobs.append({"id": j.id, "name": j.params.get("display_name", j.id),
                         "state": "running", "progress": j.progress,
                         "status": j.progress_text})
        for j in self.pipeline.completed_jobs[-20:]:
            jobs.append({"id": j.id, "name": j.params.get("display_name", j.id),
                         "state": j.state.value, "progress": j.progress,
                         "output": str(j.output_path) if j.output_path else None,
                         "error": j.error_message})
        return json.dumps(jobs)

    def cancel_job(self, job_id: str) -> str:
        ok = self._run_async(self.pipeline.cancel_job(job_id)).result(timeout=5)
        return json.dumps({"ok": ok})

    def clear_completed(self) -> str:
        self.pipeline.clear_completed()
        return json.dumps({"ok": True})

    def open_output_folder(self) -> str:
        try:
            import subprocess, sys
            folder = str(self.settings.directories.output_dir)
            if sys.platform == "win32":
                subprocess.Popen(["explorer", folder])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
            return json.dumps({"ok": True})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def play_sound(self) -> str:
        try:
            play_completion_sound()
            return json.dumps({"ok": True})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def scan_library(self, folder: str) -> str:
        def _prog(cur, total, name):
            self._emit("scan_progress", {"current": cur, "total": total, "file": name})
        try:
            added = self._run_async(
                self.library.scan_folder(folder, on_progress=_prog)
            ).result(timeout=300)
            return json.dumps({"added": added})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def get_library(self, media_type: str = "", limit: int = 200) -> str:
        return json.dumps(self.library.get_all(media_type=media_type or None, limit=limit))

    def search_library(self, query: str) -> str:
        return json.dumps(self.library.search(query))

    def get_library_stats(self) -> str:
        return json.dumps(self.library.get_stats())

    def get_settings(self) -> str:
        return self.settings.model_dump_json()

    def save_settings(self, settings_json: str) -> str:
        try:
            self.settings = AppSettings.model_validate(json.loads(settings_json))
            self.settings.save()
            self.ffmpeg.ffmpeg_path  = self.settings.tools.ffmpeg
            self.ffmpeg.ffprobe_path = self.settings.tools.ffprobe
            self.downloader.ytdlp_path = self.settings.tools.ytdlp
            return json.dumps({"ok": True})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def check_tools(self) -> str:
        try:
            from src.bootstrap import ToolBootstrap
            b = ToolBootstrap(
                tools_dir=Path(os.environ.get("RETRODISC_TOOLS", "tools")))
            return json.dumps(b.get_status_report())
        except Exception as e:
            return json.dumps({"error": str(e)})

    def splash_complete(self):
        log.info("Splash abgeschlossen — App bereit")

    # ── Video-Bearbeitung ─────────────────────────────────────────────

    def trim_video(self, input_path: str, start: float,
                   end: float, output_path: str = "") -> str:
        """Schneidet ein Video auf Start/End-Zeit."""
        from src.models.media import Job, JobType
        inp = Path(input_path)
        out = Path(output_path) if output_path else \
              inp.parent / f"{inp.stem}_trim{inp.suffix}"
        job = Job(job_type=JobType.CONVERT,
                  input_files=[inp], output_path=out,
                  params={"display_name": f"Trim: {inp.name} [{start:.1f}s–{end:.1f}s]"})
        async def _h(j):
            r = await self.ffmpeg.trim(j.input_files[0], j.output_path, start, end, j)
            j.output_path = r
        self.pipeline.register_handler(JobType.CONVERT.value + "_trim", _h)
        job.job_type = JobType.CONVERT
        self._submit(job)
        return json.dumps({"job_id": job.id, "output": str(out)})

    def merge_videos(self, paths_json: str,
                     output_path: str = "") -> str:
        """Fügt mehrere Videos zusammen."""
        from src.models.media import Job, JobType
        paths = [Path(p) for p in json.loads(paths_json)]
        if not paths:
            return json.dumps({"error": "Keine Dateien"})
        out = Path(output_path) if output_path else \
              paths[0].parent / f"merged_{paths[0].stem}.mp4"
        job = Job(job_type=JobType.MERGE,
                  input_files=paths, output_path=out,
                  params={"display_name": f"Merge: {len(paths)} Dateien"})
        async def _h(j):
            r = await self.ffmpeg.merge(j.input_files, j.output_path, j)
            j.output_path = r
        self.pipeline.register_handler(JobType.MERGE.value, _h)
        self._submit(job)
        return json.dumps({"job_id": job.id, "output": str(out)})

    # ── DVD-Menü Templates ────────────────────────────────────────────

    def get_dvd_menu_templates(self) -> str:
        """Gibt verfügbare DVD-Menü-Templates zurück."""
        templates = [
            {"id": "classic",   "name": "Klassisch",
             "desc": "Schwarzer Hintergrund, weiße Schrift",
             "preview": "🎬"},
            {"id": "cinema",    "name": "Cinema",
             "desc": "Roter Vorhang, goldene Titelschrift",
             "preview": "🎭"},
            {"id": "nature",    "name": "Natur",
             "desc": "Grüner Hintergrund, organische Formen",
             "preview": "🌿"},
            {"id": "retro",     "name": "Retro",
             "desc": "VHS-Look, scanlines, orangener Akzent",
             "preview": "📼"},
            {"id": "minimal",   "name": "Minimal",
             "desc": "Weißer Hintergrund, klare Typografie",
             "preview": "◻"},
            {"id": "family",    "name": "Familie",
             "desc": "Bunte Farben, freundliche Schrift",
             "preview": "👨‍👩‍👧‍👦"},
            {"id": "concert",   "name": "Konzert",
             "desc": "Dunkler Hintergrund, Spotlight-Effekt",
             "preview": "🎸"},
            {"id": "holiday",   "name": "Urlaub",
             "desc": "Blauer Himmel, Sonnen-Motiv",
             "preview": "🌅"},
        ]
        return json.dumps(templates)

    def set_dvd_menu(self, template_id: str, title: str,
                     chapters: str = "[]") -> str:
        """Setzt DVD-Menü-Konfiguration."""
        try:
            config = {
                "template": template_id,
                "title": title,
                "chapters": json.loads(chapters),
            }
            self.settings.save()
            return json.dumps({"ok": True, "config": config})
        except Exception as e:
            return json.dumps({"error": str(e)})

    # ── Watch Folder ──────────────────────────────────────────────────

    def set_watch_folder(self, folder: str, preset: str,
                         action: str = "convert", enabled: bool = True) -> str:
        """Konfiguriert einen Watch-Folder."""
        try:
            from src.services.watch_folder import WatchFolder, WatchRule
            from src.services.library import MediaLibrary
            ALL_VIDEO = {".mp4", ".mkv", ".avi", ".mov", ".wmv",
                         ".flv", ".webm", ".mpg", ".vob"}
            ALL_AUDIO = {".mp3", ".flac", ".wav", ".aac", ".ogg", ".m4a"}
            rule = WatchRule(
                name=f"Auto: {action}",
                extensions=ALL_VIDEO | ALL_AUDIO,
                action=action,
                preset=preset,
                enabled=enabled,
            )
            self._watch = WatchFolder(folder, [rule], self.pipeline)
            if enabled:
                import threading
                t = threading.Thread(
                    target=lambda: asyncio.run_coroutine_threadsafe(
                        self._watch.start(), self._loop
                    ).result(),
                    daemon=True,
                )
                t.start()
            return json.dumps({"ok": True, "folder": folder, "action": action})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def get_watch_folders(self) -> str:
        """Gibt konfigurierte Watch-Folder zurück."""
        try:
            wf = getattr(self, '_watch', None)
            if wf:
                return json.dumps([{
                    "folder": str(wf.folder),
                    "running": wf._running,
                    "rules": [{"name": r.name, "action": r.action,
                               "preset": r.preset} for r in wf.rules],
                }])
            return json.dumps([])
        except Exception as e:
            return json.dumps({"error": str(e)})

    # ── Mediainfo für Datei ───────────────────────────────────────────

    def get_mediainfo(self, path: str) -> str:
        """Gibt detaillierte Mediainfo einer Datei zurück."""
        future = self._run_async(self.ffmpeg.probe(path))
        try:
            m = future.result(timeout=10)
            return json.dumps({
                "path": str(m.path),
                "name": m.path.name,
                "type": m.media_type.value,
                "container": m.container,
                "duration": m.duration_seconds,
                "duration_fmt": m.duration_formatted,
                "size": m.file_size_bytes,
                "size_fmt": m.file_size_formatted,
                "resolution": m.resolution,
                "video_streams": [
                    {"codec": v.codec, "width": v.width,
                     "height": v.height, "fps": v.fps,
                     "bitrate": v.bitrate}
                    for v in m.video_streams
                ],
                "audio_streams": [
                    {"codec": a.codec, "channels": a.channels,
                     "sample_rate": a.sample_rate,
                     "language": a.language, "bitrate": a.bitrate}
                    for a in m.audio_streams
                ],
                "subtitle_streams": [
                    {"codec": s.codec, "language": s.language}
                    for s in m.subtitle_streams
                ],
                "title": m.title,
                "artist": m.artist,
                "album": m.album,
            })
        except Exception as e:
            return json.dumps({"error": str(e)})

    # ── Batch Convert mit Ordner-Dialog ───────────────────────────────

    def open_folder_for_batch(self) -> str:
        """Öffnet Ordner-Dialog für Batch-Konvertierung."""
        if self.window:
            result = self.window.create_file_dialog(
                webview.FOLDER_DIALOG
            )
            if result and result[0]:
                return json.dumps({"folder": result[0]})
        return json.dumps({"error": "Abgebrochen"})


    # ── Video-Bearbeitung ─────────────────────────────────────────────

    def trim_video(self, input_path: str, start: float,
                   end: float, output_path: str = "") -> str:
        from src.models.media import Job, JobType
        inp = Path(input_path)
        out = Path(output_path) if output_path else \
              inp.parent / f"{inp.stem}_trim{inp.suffix}"
        job = Job(job_type=JobType.CONVERT,
                  input_files=[inp], output_path=out,
                  params={"display_name": f"Trim: {inp.name}"})
        async def _h(j):
            r = await self.ffmpeg.trim(j.input_files[0], j.output_path,
                                       start, end, j)
            j.output_path = r
        self.pipeline.register_handler("trim_" + job.id, _h)
        job.job_type = JobType.CONVERT
        self._submit(job)
        return json.dumps({"job_id": job.id, "output": str(out)})

    def merge_videos(self, paths_json: str, output_path: str = "") -> str:
        from src.models.media import Job, JobType
        paths = [Path(p) for p in json.loads(paths_json)]
        if not paths:
            return json.dumps({"error": "Keine Dateien"})
        out = Path(output_path) if output_path else \
              paths[0].parent / f"merged_{paths[0].stem}.mp4"
        job = Job(job_type=JobType.MERGE, input_files=paths, output_path=out,
                  params={"display_name": f"Merge: {len(paths)} Dateien"})
        async def _h(j):
            r = await self.ffmpeg.merge(j.input_files, j.output_path, j)
            j.output_path = r
        self.pipeline.register_handler(JobType.MERGE.value, _h)
        self._submit(job)
        return json.dumps({"job_id": job.id, "output": str(out)})

    def get_dvd_menu_templates(self) -> str:
        templates = [
            {"id":"classic", "name":"Klassisch",
             "desc":"Schwarzer Hintergrund, weiße Schrift", "preview":"🎬"},
            {"id":"cinema",  "name":"Cinema",
             "desc":"Roter Vorhang, goldene Titelschrift",  "preview":"🎭"},
            {"id":"retro",   "name":"Retro",
             "desc":"VHS-Look, Scanlines, oranger Akzent",  "preview":"📼"},
            {"id":"minimal", "name":"Minimal",
             "desc":"Weißer Hintergrund, klare Schrift",    "preview":"◻"},
            {"id":"family",  "name":"Familie",
             "desc":"Bunte Farben, freundliche Schrift",    "preview":"👨‍👩‍👧"},
            {"id":"concert", "name":"Konzert",
             "desc":"Dunkler Hintergrund, Spotlight",       "preview":"🎸"},
            {"id":"nature",  "name":"Natur",
             "desc":"Grüner Hintergrund, organisch",        "preview":"🌿"},
            {"id":"holiday", "name":"Urlaub",
             "desc":"Blauer Himmel, Sonnen-Motiv",          "preview":"🌅"},
        ]
        return json.dumps(templates)

    def set_dvd_menu(self, template_id: str, title: str,
                     chapters: str = "[]") -> str:
        try:
            return json.dumps({"ok": True, "template": template_id,
                               "title": title})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def set_watch_folder(self, folder: str, preset: str,
                         action: str = "convert", enabled: bool = True) -> str:
        try:
            from src.services.watch_folder import WatchFolder, WatchRule
            ALL_EXT = {".mp4",".mkv",".avi",".mov",".wmv",".flv",
                       ".webm",".mpg",".mp3",".flac",".wav",".aac"}
            rule = WatchRule(name=f"Auto:{action}", extensions=ALL_EXT,
                             action=action, preset=preset, enabled=enabled)
            self._watch = WatchFolder(folder, [rule], self.pipeline)
            if enabled:
                import threading
                threading.Thread(
                    target=lambda: asyncio.run_coroutine_threadsafe(
                        self._watch.start(), self._loop).result(),
                    daemon=True).start()
            return json.dumps({"ok": True, "folder": folder})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def get_watch_folders(self) -> str:
        wf = getattr(self, '_watch', None)
        if wf:
            return json.dumps([{"folder": str(wf.folder),
                                 "running": wf._running}])
        return json.dumps([])

    def get_mediainfo(self, path: str) -> str:
        future = self._run_async(self.ffmpeg.probe(path))
        try:
            m = future.result(timeout=10)
            return json.dumps({
                "name": m.path.name, "type": m.media_type.value,
                "container": m.container,
                "duration_fmt": m.duration_formatted,
                "size_fmt": m.file_size_formatted,
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

    def open_folder_for_batch(self) -> str:
        if self.window:
            import webview as wv
            result = self.window.create_file_dialog(wv.FOLDER_DIALOG)
            if result and result[0]:
                return json.dumps({"folder": result[0]})
        return json.dumps({"error": "Abgebrochen"})

