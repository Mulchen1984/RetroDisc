"""Regressionen fuer robuste, abbrechbare Media-Subprozesse."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.core.downloader import Downloader
from src.core.ffmpeg import FFmpeg
from src.services.upscaler import UpscalerError, VideoUpscaler
from src.utils.subprocesses import (
    communicate_with_job,
    create_hidden_subprocess,
    iter_stream_records,
    run_hidden,
    terminate_process,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.asyncio
@pytest.mark.parametrize("method_name", ("upscale", "interpolate"))
async def test_upscaler_rejects_same_input_and_output_without_deleting_source(
    tmp_path, method_name
):
    source = tmp_path / "source.mp4"
    original = b"source-media-must-survive"
    source.write_bytes(original)
    upscaler = VideoUpscaler(
        realesrgan_path="missing-realesrgan",
        rife_path="missing-rife",
        ffmpeg_path="missing-ffmpeg",
    )

    with pytest.raises(UpscalerError, match="identisch"):
        await getattr(upscaler, method_name)(source, source)

    assert source.read_bytes() == original


@pytest.mark.asyncio
async def test_cr_only_stream_over_64k_is_split_into_bounded_records():
    """CR-Progress darf weder das StreamReader-Limit noch RAM unbounded fuellen."""
    reader = asyncio.StreamReader()
    progress_records = [f"frame={number}".encode() for number in range(10_000)]
    payload = b"\r".join(progress_records) + b"\r"
    assert len(payload) > 64 * 1024
    assert b"\n" not in payload
    reader.feed_data(payload)
    reader.feed_eof()

    records = [record async for record in iter_stream_records(
        reader, chunk_size=257, max_record_bytes=128
    )]

    assert records == progress_records
    assert max(map(len, records)) <= 128


@pytest.mark.parametrize(
    "rel_path",
    ("src/core/ffmpeg.py", "src/services/upscaler.py"),
)
def test_long_media_progress_streams_do_not_use_readline(rel_path):
    source = (PROJECT_ROOT / rel_path).read_text(encoding="utf-8")

    assert ".stderr.readline()" not in source
    assert "iter_stream_records(" in source


def test_download_command_explicitly_restores_progress_with_after_move_print(tmp_path):
    downloader = Downloader(
        ytdlp_path="yt-dlp",
        output_dir=tmp_path,
        ffmpeg_path="ffmpeg",
    )

    cmd = downloader._build_download_command(
        url="https://example.invalid/video",
        format="720p",
        output_template=None,
        extract_audio=False,
        audio_format="mp3",
        audio_quality="320k",
        subtitles=False,
        subtitle_langs="de,en",
    )

    assert "--progress" in cmd
    print_index = cmd.index("--print")
    assert cmd[print_index + 1].startswith("after_move:__RETRODISC_FILE__:")


class _ExplodingReader:
    async def read(self, _size: int) -> bytes:
        raise RuntimeError("simulierter Reader-Abbruch")


class _FakeProcess:
    def __init__(self) -> None:
        self.stderr = _ExplodingReader()
        self.returncode = None
        self.terminated = False
        self.waited = False

    def terminate(self) -> None:
        self.terminated = True

    async def wait(self) -> int:
        self.waited = True
        self.returncode = -15
        return self.returncode


class _FakeDownloadProcess(_FakeProcess):
    def __init__(self) -> None:
        super().__init__()
        self.stdout = _ExplodingReader()


@pytest.mark.asyncio
@pytest.mark.parametrize("preexisting", (False, True))
async def test_ffmpeg_reader_failure_reaps_child_and_only_removes_staging_output(
    tmp_path, preexisting
):
    input_path = tmp_path / "input.mp4"
    output_path = tmp_path / "partial.mp4"
    input_path.write_bytes(b"input")
    if preexisting:
        output_path.write_bytes(b"existing-output-must-survive")
    process = _FakeProcess()
    job = SimpleNamespace(_process=None, update_progress=lambda *_args: None)
    ffmpeg = FFmpeg(ffmpeg_path="ffmpeg", ffprobe_path="ffprobe")
    launched_output = None

    async def fake_create(*cmd, **_kwargs):
        nonlocal launched_output
        launched_output = Path(cmd[-1])
        launched_output.write_bytes(b"new-partial-output")
        return process

    with patch(
        "src.core.ffmpeg.create_hidden_subprocess",
        new=fake_create,
    ), patch.object(
        ffmpeg,
        "probe",
        new=AsyncMock(return_value=SimpleNamespace(duration_seconds=10.0)),
    ):
        with pytest.raises(RuntimeError, match="Reader-Abbruch"):
            await ffmpeg.convert(
                input_path,
                output_path,
                video_codec="libx264",
                job=job,
                overwrite=True,
            )

    assert process.terminated
    assert process.waited
    assert process.returncode == -15
    assert job._process is None
    assert launched_output is not None
    assert launched_output != output_path
    assert not launched_output.exists()
    if preexisting:
        assert output_path.read_bytes() == b"existing-output-must-survive"
    else:
        assert not output_path.exists()


@pytest.mark.asyncio
async def test_download_failure_removes_only_new_partial_files(tmp_path):
    existing_partial = tmp_path / "older-download.mp4.part"
    existing_partial.write_bytes(b"resume-data")
    new_partial = tmp_path / "current-download.mp4.part"
    process = _FakeDownloadProcess()
    downloader = Downloader(
        ytdlp_path="yt-dlp", output_dir=tmp_path, ffmpeg_path="ffmpeg"
    )

    async def fake_create(*_cmd, **_kwargs):
        new_partial.write_bytes(b"new-partial-data")
        return process

    with patch("src.core.downloader.create_hidden_subprocess", new=fake_create):
        with pytest.raises(RuntimeError, match="Reader-Abbruch"):
            await downloader.download("https://example.invalid/video")

    assert process.terminated
    assert process.waited
    assert existing_partial.read_bytes() == b"resume-data"
    assert not new_partial.exists()


class _FinishedProcess:
    def __init__(self, stdout: bytes = b"", stderr: bytes = b"") -> None:
        self.stdout = asyncio.StreamReader()
        self.stderr = asyncio.StreamReader()
        self.stdout.feed_data(stdout)
        self.stdout.feed_eof()
        self.stderr.feed_data(stderr)
        self.stderr.feed_eof()
        self.returncode = 0

    async def wait(self) -> int:
        return self.returncode

    def communicate(self):
        raise AssertionError("unbounded communicate() must not be used")


@pytest.mark.asyncio
async def test_ffmpeg_success_atomically_replaces_existing_output(tmp_path):
    input_path = tmp_path / "input.mp4"
    output_path = tmp_path / "output.mp4"
    input_path.write_bytes(b"input")
    output_path.write_bytes(b"old-complete-output")
    process = _FinishedProcess(stderr=b"frame=1\rtime=00:00:01.00\r")
    launched_output = None
    ffmpeg = FFmpeg(ffmpeg_path="ffmpeg", ffprobe_path="ffprobe")

    async def fake_create(*cmd, **_kwargs):
        nonlocal launched_output
        launched_output = Path(cmd[-1])
        launched_output.write_bytes(b"new-complete-output")
        return process

    with patch("src.core.ffmpeg.create_hidden_subprocess", new=fake_create):
        result = await ffmpeg.convert(
            input_path, output_path, video_codec="libx264", overwrite=True
        )

    assert result == output_path
    assert output_path.read_bytes() == b"new-complete-output"
    assert launched_output is not None and launched_output != output_path
    assert not launched_output.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("returncode", (0, 1))
async def test_upscaler_filter_publishes_only_successful_staging_output(
    tmp_path, returncode
):
    input_path = tmp_path / "input.mp4"
    output_path = tmp_path / "output.mp4"
    input_path.write_bytes(b"input")
    output_path.write_bytes(b"old-complete-output")
    process = _FinishedProcess(stderr=b"filter diagnostics")
    process.returncode = returncode
    launched_output = None
    upscaler = VideoUpscaler(ffmpeg_path="ffmpeg")

    async def fake_create(*cmd, **_kwargs):
        nonlocal launched_output
        launched_output = Path(cmd[-1])
        launched_output.write_bytes(b"new-output")
        return process

    with patch("src.services.upscaler.create_hidden_subprocess", new=fake_create):
        if returncode:
            with pytest.raises(UpscalerError, match="filter diagnostics"):
                await upscaler._ffmpeg_filter(
                    input_path, output_path, "scale=iw*2:ih*2", None, "start"
                )
        else:
            assert await upscaler._ffmpeg_filter(
                input_path, output_path, "scale=iw*2:ih*2", None, "start"
            ) == output_path

    assert launched_output is not None and launched_output != output_path
    assert not launched_output.exists()
    assert output_path.read_bytes() == (
        b"old-complete-output" if returncode else b"new-output"
    )


@pytest.mark.asyncio
async def test_bounded_communicate_drains_large_streams_without_calling_communicate():
    stdout = b"A" * 200_000 + b"stdout-tail"
    stderr = b"B" * 180_000 + b"stderr-tail"
    process = _FinishedProcess(stdout=stdout, stderr=stderr)
    job = SimpleNamespace(_process=None)

    captured_stdout, captured_stderr = await communicate_with_job(
        process, job, max_output_bytes=128
    )

    assert len(captured_stdout) == 128
    assert len(captured_stderr) == 128
    assert captured_stdout.endswith(b"stdout-tail")
    assert captured_stderr.endswith(b"stderr-tail")
    assert job._process is None


class _WindowsProcess:
    pid = 4242

    def __init__(self) -> None:
        self.returncode = None
        self.waited = False

    async def wait(self) -> int:
        self.waited = True
        self.returncode = 1
        return self.returncode

    def kill(self) -> None:
        raise AssertionError("taskkill success must not need root-only kill")


@pytest.mark.asyncio
@pytest.mark.skipif(os.name != "nt", reason="Windows process-tree contract")
async def test_windows_termination_uses_hidden_taskkill_tree_and_reaps_root():
    process = _WindowsProcess()
    completed = subprocess.CompletedProcess([], 0, b"", b"")

    with patch("src.utils.subprocesses.run_hidden", return_value=completed) as runner:
        await terminate_process(process)

    runner.assert_called_once_with(
        ["taskkill", "/PID", "4242", "/T", "/F"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert process.waited


def _windows_pid_is_running(pid: int) -> bool:
    import ctypes

    synchronize = 0x00100000
    wait_timeout = 258
    handle = ctypes.windll.kernel32.OpenProcess(synchronize, False, pid)
    if not handle:
        return False
    try:
        return ctypes.windll.kernel32.WaitForSingleObject(handle, 0) == wait_timeout
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


@pytest.mark.asyncio
@pytest.mark.skipif(os.name != "nt", reason="Windows process-tree integration")
async def test_windows_termination_actually_kills_spawned_descendant(tmp_path):
    child_pid_file = tmp_path / "child.pid"
    child_code = "import time; time.sleep(30)"
    parent_code = (
        "import pathlib, subprocess, sys, time; "
        f"child=subprocess.Popen([sys.executable, '-c', {child_code!r}], "
        "creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)); "
        f"pathlib.Path({str(child_pid_file)!r}).write_text(str(child.pid)); "
        "time.sleep(30)"
    )
    process = await create_hidden_subprocess(sys.executable, "-c", parent_code)
    child_pid = None
    try:
        for _ in range(200):
            if child_pid_file.exists():
                child_pid = int(child_pid_file.read_text())
                break
            await asyncio.sleep(0.01)
        assert child_pid is not None and _windows_pid_is_running(child_pid)

        await terminate_process(process, timeout=5)

        for _ in range(200):
            if not _windows_pid_is_running(child_pid):
                break
            await asyncio.sleep(0.01)
        assert process.returncode is not None
        assert not _windows_pid_is_running(child_pid)
    finally:
        if process.returncode is None:
            await terminate_process(process, timeout=5)
        if child_pid is not None and _windows_pid_is_running(child_pid):
            await asyncio.to_thread(
                run_hidden,
                ["taskkill", "/PID", str(child_pid), "/T", "/F"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
