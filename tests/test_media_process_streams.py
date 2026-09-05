"""Regressionen fuer robuste, abbrechbare Media-Subprozesse."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.core.downloader import DownloadError, Downloader
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


def _work_dir_from_cmd(cmd: tuple) -> Path:
    """Extract the private per-call download directory from a yt-dlp argv."""
    parts = [str(c) for c in cmd]
    return Path(parts[parts.index("-o") + 1]).parent


@pytest.mark.asyncio
async def test_download_failure_cleans_only_its_own_work_dir(tmp_path):
    # A parallel download's partial, sitting directly in the shared output dir …
    other_partial = tmp_path / "parallel-download.mp4.part"
    other_partial.write_bytes(b"resume-data")
    # … and another parallel job's private work area with its own partial.
    other_work = tmp_path / ".retrodisc-dl-parallel"
    other_work.mkdir()
    (other_work / "clip.mp4.part").write_bytes(b"other-job-partial")

    process = _FakeDownloadProcess()
    downloader = Downloader(
        ytdlp_path="yt-dlp", output_dir=tmp_path, ffmpeg_path="ffmpeg"
    )
    seen: dict = {}

    async def fake_create(*cmd, **_kwargs):
        work_dir = _work_dir_from_cmd(cmd)
        seen["work_dir"] = work_dir
        (work_dir / "current.mp4.part").write_bytes(b"this-job-partial")
        return process

    with patch("src.core.downloader.create_hidden_subprocess", new=fake_create):
        with pytest.raises(RuntimeError, match="Reader-Abbruch"):
            await downloader.download("https://example.invalid/video")

    assert process.terminated
    assert process.waited
    # This call owns exactly one work dir and removes only that.
    assert not seen["work_dir"].exists()
    # Nothing that belongs to other downloads is scanned or deleted.
    assert other_partial.read_bytes() == b"resume-data"
    assert (other_work / "clip.mp4.part").read_bytes() == b"other-job-partial"


@pytest.mark.asyncio
async def test_successful_download_publishes_media_and_sidecars_from_work_dir(tmp_path):
    downloader = Downloader(
        ytdlp_path="yt-dlp", output_dir=tmp_path, ffmpeg_path="ffmpeg"
    )

    async def fake_create(*cmd, **_kwargs):
        work_dir = _work_dir_from_cmd(cmd)
        media = work_dir / "Great Video [abc123].mp4"
        media.write_bytes(b"downloaded-media")
        (work_dir / "Great Video [abc123].de.srt").write_text(
            "1\n00:00:00,0 --> 00:00:01,0\nhallo\n", encoding="utf-8"
        )
        (work_dir / "Great Video [abc123].mp4.part").write_bytes(b"leftover")
        return _FinishedProcess(
            stdout=f"[download] 100%\n__RETRODISC_FILE__:{media}\n".encode()
        )

    with patch("src.core.downloader.create_hidden_subprocess", new=fake_create):
        result = await downloader.download("https://example.invalid/v")

    assert result == tmp_path / "Great Video [abc123].mp4"
    assert result.read_bytes() == b"downloaded-media"
    assert (tmp_path / "Great Video [abc123].de.srt").is_file()
    # The transient .part file is never published, the work dir is gone.
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "Great Video [abc123].de.srt",
        "Great Video [abc123].mp4",
    ]


@pytest.mark.asyncio
async def test_download_never_overwrites_an_existing_output_file(tmp_path):
    existing = tmp_path / "Clip [x].mp4"
    existing.write_bytes(b"do-not-touch")
    downloader = Downloader(
        ytdlp_path="yt-dlp", output_dir=tmp_path, ffmpeg_path="ffmpeg"
    )

    async def fake_create(*cmd, **_kwargs):
        work_dir = _work_dir_from_cmd(cmd)
        media = work_dir / "Clip [x].mp4"
        media.write_bytes(b"fresh-download")
        return _FinishedProcess(stdout=f"__RETRODISC_FILE__:{media}\n".encode())

    with patch("src.core.downloader.create_hidden_subprocess", new=fake_create):
        result = await downloader.download("https://example.invalid/v")

    assert existing.read_bytes() == b"do-not-touch"
    assert result == tmp_path / "Clip [x] (1).mp4"
    assert result.read_bytes() == b"fresh-download"


@pytest.mark.asyncio
async def test_parallel_downloads_do_not_touch_each_others_files(tmp_path):
    downloader = Downloader(
        ytdlp_path="yt-dlp", output_dir=tmp_path, ffmpeg_path="ffmpeg"
    )
    failing_started = asyncio.Event()

    async def fake_create(*cmd, **_kwargs):
        work_dir = _work_dir_from_cmd(cmd)
        if str(cmd[-1]).endswith("/fail"):
            (work_dir / "fail.mp4.part").write_bytes(b"partial")
            failing_started.set()
            proc = _FinishedProcess(stdout=b"[download]  50%\n")
            proc.returncode = 1
            return proc
        await failing_started.wait()
        media = work_dir / "ok [id].mp4"
        media.write_bytes(b"good")
        return _FinishedProcess(stdout=f"__RETRODISC_FILE__:{media}\n".encode())

    with patch("src.core.downloader.create_hidden_subprocess", new=fake_create):
        results = await asyncio.gather(
            downloader.download("https://example.invalid/fail"),
            downloader.download("https://example.invalid/ok"),
            return_exceptions=True,
        )

    assert isinstance(results[0], DownloadError)
    assert results[1] == tmp_path / "ok [id].mp4"
    assert results[1].read_bytes() == b"good"
    # The failing job took its partial with it; nothing else leaked.
    assert sorted(p.name for p in tmp_path.rglob("*")) == ["ok [id].mp4"]


@pytest.mark.asyncio
async def test_download_without_after_move_line_falls_back_to_the_media_file(tmp_path):
    downloader = Downloader(
        ytdlp_path="yt-dlp", output_dir=tmp_path, ffmpeg_path="ffmpeg"
    )

    async def fake_create(*cmd, **_kwargs):
        work_dir = _work_dir_from_cmd(cmd)
        (work_dir / "Video [id].mp4").write_bytes(b"the-media")
        # A sidecar that is *larger* than the media must not win the fallback.
        (work_dir / "Video [id].de.srt").write_text("x" * 500, encoding="utf-8")
        return _FinishedProcess(stdout=b"[download] 100%\n")

    with patch("src.core.downloader.create_hidden_subprocess", new=fake_create):
        result = await downloader.download("https://example.invalid/v")

    assert result == tmp_path / "Video [id].mp4"
    assert (tmp_path / "Video [id].de.srt").is_file()


def test_build_download_command_roots_template_in_dest_dir(tmp_path):
    downloader = Downloader(ytdlp_path="yt-dlp", output_dir=tmp_path)
    work = tmp_path / ".retrodisc-dl-abc"
    common = dict(
        url="https://example.invalid/v", format="best", output_template=None,
        extract_audio=False, audio_format="mp3", audio_quality="320k",
        subtitles=False, subtitle_langs="de,en",
    )

    scoped = downloader._build_download_command(dest_dir=work, **common)
    assert Path(scoped[scoped.index("-o") + 1]).parent == work

    default = downloader._build_download_command(**common)
    assert Path(default[default.index("-o") + 1]).parent == tmp_path


def test_claim_unique_target_is_atomic_under_real_thread_concurrency(tmp_path):
    """A genuine OS-level race (real threads, not cooperative asyncio tasks)
    must never let two publishes agree on the same free name.

    A plain ``exists()`` check followed later by ``os.replace`` is a classic
    check-then-act race: two callers can both observe the same "free" name
    before either claims it, and the second replace then silently overwrites
    the first caller's file. asyncio.gather alone can never exercise this
    window (this method makes no ``await`` call, so the event loop cannot
    interleave callers), so real OS threads are required to prove the fix.
    """
    target = tmp_path / "race.mp4"
    claimed: list[Path] = []
    lock = threading.Lock()

    def claim():
        path = Downloader._claim_unique_target(target)
        with lock:
            claimed.append(path)

    threads = [threading.Thread(target=claim) for _ in range(32)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(claimed) == 32
    assert len(set(claimed)) == 32  # every thread won a distinct name
    assert all(path.is_file() for path in claimed)


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


# ── FFmpeg merge: eigene, eindeutige Concat-Liste ──────────────────────

def _concat_path_from_cmd(cmd: tuple) -> Path:
    parts = [str(c) for c in cmd]
    return Path(parts[parts.index("-i") + 1])


@pytest.mark.asyncio
async def test_merge_uses_a_private_concat_file_and_spares_a_foreign_one(tmp_path):
    a = tmp_path / "a.mp4"
    a.write_bytes(b"a")
    b = tmp_path / "b.mp4"
    b.write_bytes(b"b")
    output = tmp_path / "final.mp4"
    # The old deterministic name would have been clobbered and then deleted.
    foreign = tmp_path / "_concat_final.txt"
    foreign.write_text("someone elses list", encoding="utf-8")
    seen: dict = {}

    async def fake_create(*cmd, **_kwargs):
        concat = _concat_path_from_cmd(cmd)
        seen["concat"] = concat
        # Readable in full here => the descriptor was flushed and closed.
        seen["text"] = concat.read_text(encoding="utf-8")
        Path(str(cmd[-1])).write_bytes(b"merged")
        return _FinishedProcess(stderr=b"muxing")

    ffmpeg = FFmpeg(ffmpeg_path="ffmpeg", ffprobe_path="ffprobe")
    with patch("src.core.ffmpeg.create_hidden_subprocess", new=fake_create):
        result = await ffmpeg.merge([a, b], output)

    assert result == output
    assert output.read_bytes() == b"merged"
    assert foreign.read_text(encoding="utf-8") == "someone elses list"
    assert seen["concat"].name != "_concat_final.txt"
    assert seen["concat"].name.startswith(".final.retrodisc-concat-")
    assert not seen["concat"].exists()
    assert str(a.resolve()) in seen["text"]
    assert str(b.resolve()) in seen["text"]


@pytest.mark.asyncio
async def test_merge_concat_list_quotes_apostrophes_in_paths(tmp_path):
    tricky = tmp_path / "Rock 'n' Roll.mp4"
    tricky.write_bytes(b"x")
    plain = tmp_path / "plain.mp4"
    plain.write_bytes(b"y")
    captured: dict = {}

    async def fake_create(*cmd, **_kwargs):
        captured["text"] = _concat_path_from_cmd(cmd).read_text(encoding="utf-8")
        Path(str(cmd[-1])).write_bytes(b"merged")
        return _FinishedProcess(stderr=b"ok")

    ffmpeg = FFmpeg(ffmpeg_path="ffmpeg", ffprobe_path="ffprobe")
    with patch("src.core.ffmpeg.create_hidden_subprocess", new=fake_create):
        await ffmpeg.merge([tricky, plain], tmp_path / "out.mp4")

    assert "Rock '\\''n'\\'' Roll.mp4" in captured["text"]
    assert f"file '{plain.resolve()}'" in captured["text"]


@pytest.mark.asyncio
async def test_parallel_merges_to_same_output_use_distinct_concat_files(tmp_path):
    a = tmp_path / "a.mp4"
    a.write_bytes(b"a")
    b = tmp_path / "b.mp4"
    b.write_bytes(b"b")
    output = tmp_path / "same.mp4"
    concat_paths: list[Path] = []
    both_ready = asyncio.Event()

    async def fake_create(*cmd, **_kwargs):
        concat = _concat_path_from_cmd(cmd)
        concat_paths.append(concat)
        if len(concat_paths) >= 2:
            both_ready.set()
        await both_ready.wait()
        # Both jobs' concat lists coexist right now, each still its own file.
        assert concat.is_file()
        Path(str(cmd[-1])).write_bytes(b"merged")
        return _FinishedProcess(stderr=b"ok")

    ffmpeg = FFmpeg(ffmpeg_path="ffmpeg", ffprobe_path="ffprobe")
    with patch("src.core.ffmpeg.create_hidden_subprocess", new=fake_create):
        results = await asyncio.gather(
            ffmpeg.merge([a, b], output),
            ffmpeg.merge([a, b], output),
        )

    assert results == [output, output]
    assert len({str(p) for p in concat_paths}) == 2
    assert not any(p.exists() for p in concat_paths)


# ── Upscaler / Interpolation: eigene, eindeutige Scratch-Verzeichnisse ──

def _fake_ncnn_backend():
    """Stand-in for ffmpeg + realesrgan/rife that only touches given paths."""
    async def fake_create(*cmd, **_kwargs):
        parts = [str(c) for c in cmd]
        target = parts[-1]
        if target.endswith("frame_%08d.png"):
            frames = Path(target).parent
            frames.mkdir(parents=True, exist_ok=True)
            (frames / "frame_00000001.png").write_bytes(b"png")
        elif "-framerate" in parts:
            Path(target).write_bytes(b"rendered-video")
        return _FinishedProcess(stderr=b"1/1\n")

    return fake_create


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method_name, deterministic, prefix",
    [
        ("upscale", "_upscale_temp_clip_out", ".clip_out.retrodisc-upscale-"),
        ("interpolate", "_interpolate_temp_clip_out", ".clip_out.retrodisc-interpolate-"),
    ],
)
async def test_ncnn_cleanup_spares_a_foreign_deterministic_temp_dir(
    tmp_path, monkeypatch, method_name, deterministic, prefix
):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"src")
    output = tmp_path / "clip_out.mp4"
    foreign = tmp_path / deterministic
    foreign.mkdir()
    (foreign / "keep.txt").write_text("keep me", encoding="utf-8")

    upscaler = VideoUpscaler(
        realesrgan_path="realesrgan", rife_path="rife", ffmpeg_path="ffmpeg"
    )
    monkeypatch.setattr(
        "src.services.upscaler.shutil.which", lambda _p: "/usr/bin/tool"
    )
    monkeypatch.setattr(upscaler, "_get_fps", AsyncMock(return_value=25.0))

    with patch(
        "src.services.upscaler.create_hidden_subprocess", new=_fake_ncnn_backend()
    ):
        kwargs = {"scale": 2} if method_name == "upscale" else {"target_fps": 50}
        result = await getattr(upscaler, method_name)(source, output, **kwargs)

    assert result == output
    assert output.read_bytes() == b"rendered-video"
    assert (foreign / "keep.txt").read_text(encoding="utf-8") == "keep me"
    assert not any(p.name.startswith(prefix) for p in tmp_path.iterdir())


@pytest.mark.asyncio
async def test_parallel_upscales_to_same_output_keep_isolated_scratch_dirs(
    tmp_path, monkeypatch
):
    src_a = tmp_path / "a.mp4"
    src_a.write_bytes(b"a")
    src_b = tmp_path / "b.mp4"
    src_b.write_bytes(b"b")
    output = tmp_path / "shared_2x.mp4"

    monkeypatch.setattr(
        "src.services.upscaler.shutil.which", lambda _p: "/usr/bin/tool"
    )
    upscaler = VideoUpscaler(
        realesrgan_path="realesrgan", rife_path="rife", ffmpeg_path="ffmpeg"
    )
    monkeypatch.setattr(upscaler, "_get_fps", AsyncMock(return_value=25.0))

    scratch_dirs: list[Path] = []
    both_extracted = asyncio.Event()
    extracted = 0

    async def fake_create(*cmd, **_kwargs):
        nonlocal extracted
        parts = [str(c) for c in cmd]
        target = parts[-1]
        if target.endswith("frame_%08d.png"):
            frames = Path(target).parent
            frames.mkdir(parents=True, exist_ok=True)
            (frames / "frame_00000001.png").write_bytes(b"png")
            scratch_dirs.append(frames.parent)
            extracted += 1
            if extracted >= 2:
                both_extracted.set()
            await both_extracted.wait()
            # Each job must still see exactly its own single extracted frame.
            assert sorted(p.name for p in frames.iterdir()) == ["frame_00000001.png"]
        elif "-framerate" in parts:
            Path(target).write_bytes(b"video")
        return _FinishedProcess(stderr=b"1/1\n")

    with patch("src.services.upscaler.create_hidden_subprocess", new=fake_create):
        results = await asyncio.gather(
            upscaler.upscale(src_a, output, scale=2),
            upscaler.upscale(src_b, output, scale=2),
        )

    assert results == [output, output]
    assert output.is_file()
    assert len({str(d) for d in scratch_dirs}) == 2
    assert not any(d.exists() for d in scratch_dirs)
    assert not any(
        p.name.startswith(".shared_2x.retrodisc-upscale-") for p in tmp_path.iterdir()
    )
