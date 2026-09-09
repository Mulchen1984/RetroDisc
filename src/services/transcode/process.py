"""Controlled subprocess execution for short FFmpeg/ffprobe commands.

Buffered runner with a hard timeout that terminates the whole process tree so
nothing hangs or leaks. Injectable everywhere (probes, ffprobe) so tests never
need a real FFmpeg. Streaming (progress) runs live in the job module.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional, Sequence

from src.utils.subprocesses import create_hidden_subprocess, decode_console_output, terminate_process


@dataclass
class ProcResult:
    returncode: Optional[int]
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    cancelled: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out and not self.cancelled


# A runner is any async callable (args, timeout) -> ProcResult; injectable for tests.
Runner = Callable[[Sequence[str], Optional[float]], Awaitable[ProcResult]]


async def run_process(args: Sequence[str], timeout: Optional[float] = None) -> ProcResult:
    """Run a command, capture output, kill the tree on timeout. Never raises for
    process failure — returns a ProcResult the caller classifies."""
    try:
        proc = await create_hidden_subprocess(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    except (OSError, FileNotFoundError) as exc:
        return ProcResult(returncode=None, stderr=f"process start failed: {exc}")
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        await terminate_process(proc)
        return ProcResult(returncode=None, timed_out=True,
                          stderr=f"timeout after {timeout}s")
    except asyncio.CancelledError:
        await terminate_process(proc)
        raise
    return ProcResult(returncode=proc.returncode,
                      stdout=decode_console_output(out), stderr=decode_console_output(err))
