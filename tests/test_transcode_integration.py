"""End-to-end transcoding pipeline: mocked (CI) + optional real FFmpeg."""
import asyncio
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from src.services.transcode.process import ProcResult
from src.services.transcode.service import TranscodeService
from src.services.transcode.job import TranscodingState

FFPROBE_JSON = {"format": {"duration": "100.0"},
                "streams": [{"codec_type": "video", "codec_name": "h264",
                             "width": 1920, "height": 1080, "avg_frame_rate": "25/1"}]}
ENCODERS = " V....D libx264               H.264\n V....D libx265               H.265\n"


class FakeStream:
    def __init__(self, lines):
        self._lines = list(lines)
    async def readline(self):
        return self._lines.pop(0) if self._lines else b""


class FakeErr:
    def __init__(self):
        self._sent = False
    async def read(self, n=-1):
        if self._sent:
            return b""
        self._sent = True
        return b""


class FakeProc:
    def __init__(self, lines, returncode=0):
        self.stdout = FakeStream(lines)
        self.stderr = FakeErr()
        self.returncode = returncode
        self._rc = returncode
    async def wait(self):
        self.returncode = self._rc
        return self._rc


def make_runner(*, probe_payload=FFPROBE_JSON, encoders=ENCODERS):
    async def runner(args, timeout=None):
        exe = args[0]
        if exe.endswith("ffprobe"):
            return ProcResult(0, json.dumps(probe_payload), "")
        if "-version" in args:
            return ProcResult(0, "ffmpeg version 6.1", "")
        if "-encoders" in args:
            return ProcResult(0, encoders, "")
        return ProcResult(0, "", "")            # probe-encode ok
    return runner


def make_spawn(dest, lines, rc=0):
    async def spawn(args):
        Path(dest).write_bytes(b"0" * 100000)   # ffmpeg-Ausgabe simulieren
        return FakeProc(lines, rc)
    return spawn


async def _noop_terminator(proc):
    return None


PROGRESS = [b"out_time=00:00:50.00\n", b"progress=continue\n", b"progress=end\n"]


@pytest.mark.asyncio
async def test_full_pipeline_mocked(tmp_path):
    dst = tmp_path / "out.mp4"
    service = TranscodeService(runner=make_runner())
    job = await service.transcode("in.mkv", str(dst), "h264_compatibility", overwrite=True,
                                  spawn=make_spawn(dst, PROGRESS), terminator=_noop_terminator)
    assert job.state == TranscodingState.COMPLETED
    assert job.selected_encoder == "libx264" and job.progress == 100.0
    assert job.verification and job.verification["status"] == "PASS"


@pytest.mark.asyncio
async def test_pipeline_selection_failure_without_encoders(tmp_path):
    dst = tmp_path / "out.mp4"
    spawned = {"called": False}

    async def spy_spawn(args):
        spawned["called"] = True
        return FakeProc(PROGRESS)
    service = TranscodeService(runner=make_runner(encoders="Encoders:\n"))   # keine Encoder
    job = await service.transcode("in.mkv", str(dst), "h264_compatibility",
                                  spawn=spy_spawn, terminator=_noop_terminator)
    assert job.state == TranscodingState.FAILED
    assert job.error_class == "ENCODER_NOT_AVAILABLE" and not spawned["called"]


@pytest.mark.asyncio
async def test_pipeline_verification_failure_marks_failed(tmp_path):
    dst = tmp_path / "out.mp4"
    # Ausgabe-Probe liefert keinen Videostream -> Verifikation FAIL
    bad_probe = {"format": {"duration": "0"}, "streams": [{"codec_type": "audio", "codec_name": "aac"}]}
    service = TranscodeService(runner=make_runner(probe_payload=bad_probe))
    job = await service.transcode("in.mkv", str(dst), "h264_compatibility", overwrite=True,
                                  spawn=make_spawn(dst, PROGRESS), terminator=_noop_terminator)
    assert job.state == TranscodingState.FAILED and job.verification["status"] == "FAIL"


@pytest.mark.asyncio
async def test_plan_produces_command_without_running(tmp_path):
    service = TranscodeService(runner=make_runner())
    plan = await service.plan("in.mkv", str(tmp_path / "o.mp4"), "h264_compatibility", overwrite=True)
    assert plan.selection.encoder == "libx264" and "libx264" in plan.args
    assert plan.info.primary_video.width == 1920


# ── optional real FFmpeg (skips in CI without FFmpeg; not a mandatory gate) ──
_FFMPEG = shutil.which("ffmpeg")
_FFPROBE = shutil.which("ffprobe")


@pytest.mark.skipif(not (_FFMPEG and _FFPROBE), reason="FFmpeg/ffprobe nicht vorhanden")
@pytest.mark.asyncio
async def test_real_ffmpeg_transcode(tmp_path):
    src = tmp_path / "src.mp4"
    subprocess.run([_FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                    "-i", "testsrc2=size=160x120:rate=15:duration=2", "-pix_fmt", "yuv420p",
                    "-c:v", "libx264", "-crf", "30", "-y", str(src)], check=True)
    dst = tmp_path / "out.mp4"
    service = TranscodeService(ffmpeg=_FFMPEG, ffprobe=_FFPROBE)
    job = await service.transcode(str(src), str(dst), "h264_compatibility", overwrite=True,
                                  timeout=120)
    assert job.state == TranscodingState.COMPLETED, job.to_dict()
    assert job.verification["status"] in ("PASS", "PASS_WITH_WARNINGS")
    assert dst.is_file() and dst.stat().st_size > 1000
