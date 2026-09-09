"""TranscodingJob state machine and a streaming, cancellable FFmpeg runner.

The runner streams `-progress pipe:1`, updates job progress, and guarantees clean
process shutdown on cancel/timeout (graceful terminate then kill via an injected
terminator). Spawn and terminator are injectable so the whole flow is unit
tested without a real FFmpeg process.
"""
from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Awaitable, Callable, Optional

from src.services.transcode.errors import FFmpegErrorClass, classify_ffmpeg_error
from src.services.transcode.progress import FFmpegProgressParser, ProgressSnapshot
from src.utils.subprocesses import create_hidden_subprocess, terminate_process


class TranscodingState(str, Enum):
    CREATED = "created"
    PROBING = "probing"
    SELECTING_ENCODER = "selecting_encoder"
    PREPARING = "preparing"
    RUNNING = "running"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


_TERMINAL = {TranscodingState.COMPLETED, TranscodingState.FAILED, TranscodingState.CANCELLED}


@dataclass
class TranscodingJob:
    source: str = ""
    destination: str = ""
    profile_name: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    state: TranscodingState = TranscodingState.CREATED
    selected_encoder: str = ""
    progress: float = 0.0
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    exit_code: Optional[int] = None
    error_class: Optional[str] = None
    error_detail: str = ""
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self):
        self._now = time.time

    # ── transitions ─────────────────────────────────────────────────────
    def mark_probing(self): self.state = TranscodingState.PROBING
    def mark_selecting(self): self.state = TranscodingState.SELECTING_ENCODER
    def mark_preparing(self): self.state = TranscodingState.PREPARING

    def mark_running(self):
        self.state = TranscodingState.RUNNING
        self.start_time = self._now()

    def update_progress(self, percent: float):
        if self.state == TranscodingState.RUNNING:
            self.progress = max(self.progress, min(100.0, float(percent)))

    def mark_verifying(self): self.state = TranscodingState.VERIFYING

    def mark_completed(self, exit_code: int = 0):
        self.state = TranscodingState.COMPLETED
        self.exit_code = exit_code
        self.progress = 100.0
        self.end_time = self._now()

    def fail(self, error_class: FFmpegErrorClass, *, detail: str = "", exit_code: Optional[int] = None):
        if self.state in _TERMINAL:
            return
        self.state = TranscodingState.FAILED
        self.error_class = error_class.value if isinstance(error_class, FFmpegErrorClass) else str(error_class)
        self.error_detail = detail
        self.exit_code = exit_code
        self.end_time = self._now()

    def cancel(self):
        if self.state in _TERMINAL:
            return
        self.state = TranscodingState.CANCELLED
        self.error_class = FFmpegErrorClass.PROCESS_CANCELLED.value
        self.end_time = self._now()

    def timeout(self):
        self.fail(FFmpegErrorClass.PROCESS_TIMEOUT, detail="Prozess-Timeout")

    @property
    def finished(self) -> bool:
        return self.state in _TERMINAL

    def to_dict(self) -> dict:
        return {"id": self.id, "state": self.state.value, "source": self.source,
                "destination": self.destination, "profile": self.profile_name,
                "encoder": self.selected_encoder, "progress": self.progress,
                "exit_code": self.exit_code, "error_class": self.error_class,
                "error_detail": self.error_detail, "warnings": list(self.warnings)}


async def _default_spawn(args):
    return await create_hidden_subprocess(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)


_STDERR_TAIL_BYTES = 16384


async def _pump_stderr(proc, tail: bytearray) -> None:
    """Drain stderr concurrently into a bounded tail so a full pipe never blocks
    (deadlock) the transcode, while keeping the end for error classification."""
    stream = getattr(proc, "stderr", None)
    if stream is None:
        return
    while True:
        try:
            chunk = await stream.read(65536)
        except Exception:
            break
        if not chunk:
            break
        tail.extend(chunk if isinstance(chunk, (bytes, bytearray)) else str(chunk).encode("utf-8", "replace"))
        if len(tail) > _STDERR_TAIL_BYTES:
            del tail[:-_STDERR_TAIL_BYTES]


async def run_transcode(job: TranscodingJob, args, *, total_duration: Optional[float] = None,
                        spawn: Callable[[list], Awaitable] = _default_spawn,
                        terminator: Callable[[object], Awaitable] = terminate_process,
                        on_progress: Optional[Callable[[ProgressSnapshot], None]] = None,
                        timeout: Optional[float] = None,
                        cancel_event: Optional[asyncio.Event] = None) -> TranscodingJob:
    job.mark_running()
    proc = await spawn(list(args))
    parser = FFmpegProgressParser(total_duration)

    async def pump():
        stream = getattr(proc, "stdout", None)
        if stream is None:
            return
        while True:
            raw = await stream.readline()
            if not raw:
                break
            line = raw.decode("utf-8", "replace") if isinstance(raw, (bytes, bytearray)) else raw
            snap = parser.feed_line(line)
            if snap is not None:
                if snap.percent is not None:
                    job.update_progress(snap.percent)
                if on_progress:
                    on_progress(snap)

    stderr_tail = bytearray()
    pump_task = asyncio.create_task(pump())
    err_task = asyncio.create_task(_pump_stderr(proc, stderr_tail))
    exit_task = asyncio.create_task(proc.wait())
    cancel_task = asyncio.create_task(cancel_event.wait()) if cancel_event else None
    waiters = [exit_task] + ([cancel_task] if cancel_task else [])

    done, _pending = await asyncio.wait(waiters, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
    timed_out = not done
    cancelled = bool(cancel_task is not None and cancel_task in done)

    async def _cleanup_tasks():
        for task in (pump_task, err_task, exit_task, cancel_task):
            if task is not None and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task

    def _stderr() -> str:
        return stderr_tail.decode("utf-8", "replace")

    if timed_out or cancelled:
        with contextlib.suppress(Exception):
            await terminator(proc)                 # graceful terminate -> kill
        await _cleanup_tasks()
        (job.cancel() if cancelled else job.timeout())
        job.error_detail = job.error_detail or _stderr()[-500:]
        return job

    # Prozess ist von selbst beendet
    if cancel_task is not None:
        cancel_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await cancel_task
    with contextlib.suppress(Exception):
        await pump_task
    with contextlib.suppress(Exception):
        await err_task                             # restlichen stderr einsammeln
    rc = proc.returncode
    stderr = _stderr()
    if rc == 0:
        job.mark_completed(rc)
    else:
        job.fail(classify_ffmpeg_error(stderr, returncode=rc), detail=stderr[-500:], exit_code=rc)
    return job
