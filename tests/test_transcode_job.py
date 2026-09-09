"""TranscodingJob state machine + run_transcode with a fake process."""
import asyncio
import pytest
from src.services.transcode.job import (
    TranscodingJob, TranscodingState, run_transcode,
)
from src.services.transcode.errors import FFmpegErrorClass


class FakeStream:
    def __init__(self, lines, stop=None):
        self._lines = list(lines)
        self._stop = stop
    async def readline(self):
        if self._lines:
            return self._lines.pop(0)
        if self._stop is not None:
            await self._stop.wait()
        return b""


class FakeErr:
    def __init__(self, data=b""):
        self._data = data
        self._sent = False
    async def read(self, n=-1):
        if self._sent:
            return b""
        self._sent = True
        return self._data


class FakeProc:
    def __init__(self, lines, *, returncode=0, stderr=b"", run_forever=False):
        self._stop = asyncio.Event() if run_forever else None
        self.stdout = FakeStream(lines, self._stop)
        self.stderr = FakeErr(stderr)
        self._rc = returncode
        self.returncode = None if run_forever else returncode
    async def wait(self):
        if self._stop is not None:
            await self._stop.wait()
        self.returncode = self._rc
        return self._rc
    def force_stop(self, rc=-9):
        if self.returncode is None:
            self.returncode = rc
        if self._stop is not None:
            self._stop.set()


def spawn_of(proc):
    async def spawn(args):
        return proc
    return spawn


async def fake_terminator(proc):
    proc.force_stop(-9)


PROGRESS = [b"frame=10\n", b"out_time=00:00:05.00\n", b"speed=2.0x\n", b"progress=continue\n"]


# ── state machine ─────────────────────────────────────────────────────────────
def test_state_transitions_and_terminal_guard():
    job = TranscodingJob(source="a", destination="b")
    assert job.state == TranscodingState.CREATED
    job.mark_probing(); job.mark_selecting(); job.mark_preparing(); job.mark_running()
    assert job.start_time is not None
    job.mark_completed(0)
    assert job.state == TranscodingState.COMPLETED and job.progress == 100.0
    job.fail(FFmpegErrorClass.UNKNOWN)                # terminal -> no-op
    assert job.state == TranscodingState.COMPLETED


def test_update_progress_only_while_running():
    job = TranscodingJob()
    job.update_progress(50)                           # nicht RUNNING -> ignoriert
    assert job.progress == 0.0
    job.mark_running(); job.update_progress(40); job.update_progress(20)
    assert job.progress == 40.0                       # monoton


# ── runner ────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_successful_run_completes_with_progress():
    proc = FakeProc(PROGRESS, returncode=0)
    job = TranscodingJob(source="in", destination="out")
    seen = []
    await run_transcode(job, ["ffmpeg"], total_duration=50.0, spawn=spawn_of(proc),
                        terminator=fake_terminator, on_progress=seen.append)
    assert job.state == TranscodingState.COMPLETED and job.exit_code == 0
    assert job.progress == 100.0 and seen and seen[0].percent == 10.0


@pytest.mark.asyncio
async def test_failed_run_classifies_error():
    proc = FakeProc([b"progress=end\n"], returncode=1, stderr=b"No space left on device")
    job = TranscodingJob()
    await run_transcode(job, ["ffmpeg"], spawn=spawn_of(proc), terminator=fake_terminator)
    assert job.state == TranscodingState.FAILED
    assert job.error_class == FFmpegErrorClass.OUT_OF_DISK.value and job.exit_code == 1


@pytest.mark.asyncio
async def test_timeout_terminates_and_marks_failed():
    proc = FakeProc(PROGRESS, run_forever=True)
    job = TranscodingJob()
    await run_transcode(job, ["ffmpeg"], total_duration=50.0, spawn=spawn_of(proc),
                        terminator=fake_terminator, timeout=0.05)
    assert job.state == TranscodingState.FAILED
    assert job.error_class == FFmpegErrorClass.PROCESS_TIMEOUT.value
    assert proc._stop.is_set()                        # Prozess wurde terminiert (kein Zombie)


@pytest.mark.asyncio
async def test_cancel_during_run_marks_cancelled():
    proc = FakeProc(PROGRESS, run_forever=True)
    job = TranscodingJob()
    cancel = asyncio.Event()

    def on_progress(snap):
        cancel.set()                                  # nach dem ersten Snapshot abbrechen
    await run_transcode(job, ["ffmpeg"], total_duration=50.0, spawn=spawn_of(proc),
                        terminator=fake_terminator, on_progress=on_progress, cancel_event=cancel)
    assert job.state == TranscodingState.CANCELLED
    assert job.error_class == FFmpegErrorClass.PROCESS_CANCELLED.value
    assert proc._stop.is_set()                        # terminiert
