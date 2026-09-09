"""macOS download chaining, platform defaults, and opt-in real tool smoke."""
import asyncio
import functools
import json
import os
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.config.settings import AppSettings, DirectorySettings
from src.core.downloader import Downloader
from src.core.ffmpeg import FFmpeg
from retrodisc_launcher import RetroDiscBridge, check_tools


@pytest.mark.parametrize("system,video,download", [
    ("Darwin", "Movies", "Movies"),
    ("Windows", "Videos", "Downloads"),
    ("Linux", "Videos", "Downloads"),
])
def test_media_defaults(monkeypatch, system, video, download):
    monkeypatch.setattr("src.config.settings.platform.system", lambda: system)
    dirs = DirectorySettings()
    assert dirs.output_dir == Path.home() / video / "RetroDisc"
    assert dirs.download_dir == Path.home() / download / "RetroDisc"
    assert dirs.temp_dir == dirs.output_dir / "_temp"
    if system == "Darwin":
        assert dirs.audio_dir == Path.home() / "Music" / "RetroDisc"
    assert DirectorySettings(download_dir="custom").download_dir == Path("custom")


def capture_download(bridge, url, audio_only=False):
    captured = []
    bridge._submit_job = lambda job, handler: (captured.append((job, handler)) or '{}')
    bridge.download_url(url, audio_only=audio_only)
    return captured[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("system", ["darwin", "win32"])
async def test_chaining_preserves_video_on_audio_failure(tmp_path, monkeypatch, system):
    monkeypatch.setattr(sys, "platform", system)
    bridge = object.__new__(RetroDiscBridge)
    bridge.settings = AppSettings(directories=DirectorySettings(audio_dir=tmp_path))
    video = tmp_path / "video.mp4"
    video.write_bytes(b"original")
    bridge.downloader = SimpleNamespace(validate_url=lambda url: url, download=AsyncMock(return_value=video))
    bridge.ffmpeg = SimpleNamespace(extract_audio=AsyncMock(side_effect=RuntimeError("audio failed")))
    job, handler = capture_download(bridge, "https://example.invalid/video")
    if system == "darwin":
        with pytest.raises(RuntimeError, match="audio failed"):
            await handler(job)
        assert job.params["output_paths"] == [str(video)]
    else:
        await handler(job)
        bridge.ffmpeg.extract_audio.assert_not_called()
        assert "output_paths" not in job.params
    assert job.output_path == video
    assert video.read_bytes() == b"original"


@pytest.mark.skipif(sys.platform != "darwin" or os.environ.get("RETRODISC_REAL_MEDIA_TEST") != "1",
                    reason="opt-in macOS test with installed yt-dlp/ffmpeg")
def test_real_macos_download_and_audio(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    tools = check_tools()
    assert {"ffmpeg", "ffprobe", "ytdlp"} <= tools.keys()
    bridge = object.__new__(RetroDiscBridge)
    bridge.settings = AppSettings()
    bridge.ffmpeg = FFmpeg(tools["ffmpeg"], tools["ffprobe"])
    bridge.downloader = Downloader(tools["ytdlp"], bridge.settings.directories.download_dir, tools["ffmpeg"])
    fixtures = Path(__file__).parent / "fixtures"
    server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(SimpleHTTPRequestHandler, directory=str(fixtures)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    async def run():
        job, handler = capture_download(bridge, f"http://127.0.0.1:{server.server_port}/test_video.mp4")
        await asyncio.wait_for(handler(job), timeout=60)
        video, audio = map(Path, job.params["output_paths"])
        assert video.parent == tmp_path / "Movies" / "RetroDisc"
        assert audio.parent == tmp_path / "Music" / "RetroDisc"
        assert (await bridge.ffmpeg.probe(video)).video_streams
        media = await bridge.ffmpeg.probe(audio)
        assert media.audio_streams and not media.video_streams
        original = await bridge.ffmpeg.probe(fixtures / "test_video.mp4")
        assert media.duration_seconds == pytest.approx(original.duration_seconds, abs=0.1)
        assert video.is_file() and video.stat().st_size > 0
        bridge.pipeline = SimpleNamespace(_queue=[], _running=[], completed_jobs=[job])
        assert json.loads(bridge.get_queue())[0]["output_paths"] == [str(video), str(audio)]
        print(f"\nVIDEO={video}\nAUDIO={audio}")
        audio_job, audio_handler = capture_download(bridge, f"http://127.0.0.1:{server.server_port}/test_video.mp4", audio_only=True)
        await asyncio.wait_for(audio_handler(audio_job), timeout=60)
        assert audio_job.output_path.parent == tmp_path / "Music" / "RetroDisc"
        assert len(audio_job.params["output_paths"]) == 1
        assert video.is_file() and audio.is_file()
    try:
        asyncio.run(run())
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_macos_tool_detection_ignores_windows_binaries(tmp_path, monkeypatch):
    import retrodisc_launcher as launcher
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(launcher, "BUNDLE_DIR", tmp_path)
    monkeypatch.setattr(launcher, "TOOLS_DIR", tmp_path / "tools")
    (tmp_path / "vendor").mkdir()
    for name in ("ffmpeg", "ffprobe", "yt-dlp"):
        (tmp_path / "vendor" / f"{name}.exe").write_bytes(b"windows")
    monkeypatch.setattr("shutil.which", lambda name: f"/detected/{name}")
    assert check_tools() == {"ffmpeg": "/detected/ffmpeg", "ffprobe": "/detected/ffprobe", "ytdlp": "/detected/yt-dlp"}
