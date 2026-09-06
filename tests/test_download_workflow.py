"""URL -> real yt-dlp download -> FFmpeg MP4 -> durable bridge/UI result."""
import asyncio
import functools
import json
import re
import shutil
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from src.config.settings import AppSettings, DirectorySettings, ensure_writable_directory
from src.core.downloader import Downloader
from src.core.ffmpeg import FFmpeg
from src.core.pipeline import Pipeline
from src.models.media import Job, JobType
from src.services.converter import Converter
from src.services.download_workflow import run_download_workflow
from src.services.job_history import JobHistory
from src.utils.subprocesses import run_hidden
from retrodisc_launcher import RetroDiscBridge

ROOT = Path(__file__).resolve().parents[1]
STEPS = ["Quelle erkannt", "Download läuft", "Download abgeschlossen", "Verarbeitung läuft", "Video erstellt", "Fertig"]


#: WinError 4551 - "Eine Anwendungssteuerungsrichtlinie hat diese Datei
#: blockiert". Smart App Control entscheidet je Datei; die vendorten Binaries
#: sind unsigniert und werden auf dem Entwicklungsrechner nicht gestartet.
_POLICY_BLOCKED = 4551


def require_runnable_vendor_tools(*tools: Path) -> None:
    """Trennt "Werkzeug von der Richtlinie blockiert" von "Code kaputt".

    Ohne diese Unterscheidung ist die Suite dauerhaft rot, und eine echte
    Regression waere in dem Rauschen nicht mehr zu sehen. Uebersprungen wird
    **ausschliesslich** der Richtlinienblock (WinError 4551) und nur, wenn die
    Datei tatsaechlich vorhanden ist. Jeder andere Fehlschlag - fehlendes
    Werkzeug, Absturz, falscher Exitcode - bleibt ein Fehlschlag.

    Die Richtlinie wird nicht umgangen und nicht veraendert. Der Grund steht
    im Skip-Text, damit ein gruener Lauf niemanden glauben laesst, die echte
    Medienstrecke sei gefahren worden.
    """
    for tool in tools:
        try:
            run_hidden([str(tool), "-version"], capture_output=True, timeout=15)
        except OSError as exc:
            if getattr(exc, "winerror", None) == _POLICY_BLOCKED:
                pytest.skip(
                    f"{tool.name} wird von einer Anwendungssteuerungsrichtlinie "
                    f"blockiert (WinError {_POLICY_BLOCKED}). Die echte "
                    "Medienstrecke ist auf diesem Host nicht fahrbar; siehe "
                    "docs/RELEASE_STATUS.md, Blocker B1."
                )
            raise


def make_job(root):
    job = Job(job_type=JobType.DOWNLOAD, params={"url": "https://example.invalid/test", "format": "best",
              "audio_only": False, "audio_format": "mp3", "subtitles": False})
    job.params["download_dir"] = str(root / "Downloads" / job.id)
    return job


def bridge_view(history, pipeline):
    bridge = object.__new__(RetroDiscBridge)
    bridge.job_history, bridge.pipeline = history, pipeline
    return bridge


def test_profile_relative_onefile_and_permissions(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "Benutzer_日本")
    monkeypatch.setattr("sys._MEIPASS", str(tmp_path / "_MEI123"), raising=False)
    monkeypatch.chdir(tmp_path)
    settings = AppSettings(directories={"download_dir": "Downloads"})
    settings.ensure_directories()
    assert settings.directories.download_dir == Path.home() / "RetroDisc" / "Downloads"
    assert settings.directories.output_dir.is_dir()
    assert settings.directories.temp_dir.is_dir()
    assert (Path.home() / "RetroDisc" / "Logs").is_dir()
    bad = tmp_path / "file"
    bad.write_text("occupied")
    with pytest.raises(OSError, match="Ordner nicht beschreibbar"):
        ensure_writable_directory(bad)
    with pytest.raises(ValueError):
        DirectorySettings(output_dir="")
    with pytest.raises(ValueError):
        DirectorySettings(output_dir="C:relative")


def test_legacy_defaults_migrate_custom_paths_survive(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    config = tmp_path / "settings.json"
    AppSettings(directories={"download_dir": tmp_path / "Downloads" / "RetroDisc",
                            "output_dir": tmp_path / "custom"}).save(config)
    loaded = AppSettings.load(config)
    assert loaded.directories.download_dir == tmp_path / "RetroDisc" / "Downloads"
    assert loaded.directories.output_dir == tmp_path / "custom"


@pytest.mark.asyncio
async def test_failed_processing_preserves_download_and_restart_error(tmp_path):
    job = make_job(tmp_path)
    source = Path(job.params["download_dir"]) / "Film.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"retained original")
    dl = SimpleNamespace(output_dir=source.parent, download=AsyncMock(return_value=source))
    converter = SimpleNamespace(output_dir=tmp_path / "Videos", convert_file=AsyncMock(side_effect=OSError("Datentraeger voll")))
    history = JobHistory(tmp_path / "jobs.sqlite3")
    pipeline = Pipeline(play_sound=False)
    pipeline.history = history
    await pipeline.submit(job, lambda j: run_download_workflow(j, dl, converter, history))
    await pipeline._execute_job(job)
    row = JobHistory(history.path).recent()[0]
    assert row["state"] == "failed" and "voll" in row["error"]
    assert "Fertig" not in row["steps"]
    assert source.read_bytes() == b"retained original"


@pytest.mark.asyncio
async def test_restart_interrupted_and_queued_cancel(tmp_path):
    history = JobHistory(tmp_path / "jobs.sqlite3")
    job = make_job(tmp_path)
    UUID(job.id)
    job.mark_running()
    history.save(job)
    assert JobHistory(history.path).recent()[0]["state"] == "interrupted"
    pipeline = Pipeline(play_sound=False)
    pipeline.history = history
    queued = make_job(tmp_path)
    await pipeline.submit(queued)
    await pipeline.cancel_job(queued.id)
    assert next(r for r in history.recent() if r["id"] == queued.id)["state"] == "cancelled"


@pytest.mark.asyncio
async def test_complete_real_download_processing_restart_and_ui(tmp_path, monkeypatch):
    # Local HTTP keeps this test deterministic and independent of video platforms.
    www = tmp_path / "http"
    www.mkdir()
    source = www / "Film.mp4"
    ffmpeg = ROOT / "vendor" / "ffmpeg.exe"
    ffprobe = ROOT / "vendor" / "ffprobe.exe"
    ytdlp = ROOT / "vendor" / "yt-dlp.exe"
    assert all(p.is_file() for p in (ffmpeg, ffprobe, ytdlp))
    require_runnable_vendor_tools(ffmpeg, ffprobe, ytdlp)
    made = run_hidden([str(ffmpeg), "-y", "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=10",
                       "-t", "0.5", "-c:v", "libx264", str(source)], capture_output=True)
    assert made.returncode == 0
    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, *_args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(www)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        job = make_job(tmp_path)
        job.params["url"] = f"http://127.0.0.1:{server.server_port}/Film.mp4"
        history = JobHistory(tmp_path / "jobs.sqlite3")
        pipeline = Pipeline(play_sound=False)
        pipeline.history = history
        dl = Downloader(str(ytdlp), Path(job.params["download_dir"]), str(ffmpeg))
        converter = Converter(FFmpeg(str(ffmpeg), str(ffprobe)), tmp_path / "Videos")
        progress = []
        job.on_progress = lambda value, text: progress.append(value)
        await pipeline.submit(job, lambda j: run_download_workflow(j, dl, converter, history))
        await pipeline._execute_job(job)
        assert job.state.value == "done", job.error_message
        assert job.params["steps"] == STEPS
        assert progress == sorted(progress)
        assert job.output_path.parent == tmp_path / "Videos"
        assert job.output_path.suffix == ".mp4"
        assert any(dl.output_dir.glob("*.mp4"))
        assert not list(dl.output_dir.glob(".retrodisc-dl-*"))
        media = await converter.ffmpeg.probe(job.output_path)
        assert media.video_streams[0].codec == "h264"
        # Fresh bridge + fresh DB connection emulate the restart read path.
        bridge = bridge_view(JobHistory(history.path), Pipeline(play_sound=False))
        rows = json.loads(bridge.get_queue())
        assert rows[0]["state"] == "done"
        assert rows[0]["download"] == str(dl.output_dir)
        assert rows[0]["output"] == str(job.output_path)
        opened = []
        monkeypatch.setattr("os.startfile", lambda path: opened.append(path))
        assert json.loads(bridge.open_job_folder(job.id, "download"))["ok"]
        assert json.loads(bridge.open_job_folder(job.id, "output"))["ok"]
        assert opened == [str(dl.output_dir), str(job.output_path.parent)]
        assert "error" in json.loads(bridge.open_job_folder(job.id, "unknown"))
        # Execute the shipped renderer and buttons with the actual persisted record.
        ui = (ROOT / "src/ui/app.html").read_text(encoding="utf-8")
        def function(name):
            return re.search(r"(?:async )?function " + name + r"\([^)]*\)\s*\{.*?^\}", ui, re.S | re.M)[0]
        helpers = "\n".join(line for line in ui.splitlines() if line.startswith(("function escHtml(", "function escAttr(")))
        code = "const S={jobs:" + json.dumps(rows) + "}; const node={};const document={getElementById:()=>node};let calls=[];const api=()=>({open_job_folder:async(id,kind)=>{calls.push([id,kind]);return '{}'}});const setStat=()=>{};\n"
        code += helpers + "\n" + function("renderJobs") + "\n" + function("openJobFolder")
        code += "\n(async()=>{renderJobs();await openJobFolder(S.jobs[0].id,'download');await openJobFolder(S.jobs[0].id,'output');console.log(JSON.stringify({html:node.innerHTML,calls}));})();"
        rendered = run_hidden([shutil.which("node"), "-e", code], capture_output=True, text=True, encoding="utf-8")
        assert rendered.returncode == 0, rendered.stderr
        result = json.loads(rendered.stdout)
        assert str(dl.output_dir) in result["html"]
        assert str(job.output_path) in result["html"]
        assert result["html"].count("Ordner öffnen") == 2
        assert all(step in result["html"] for step in STEPS)
        assert result["calls"] == [[job.id, "download"], [job.id, "output"]]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
