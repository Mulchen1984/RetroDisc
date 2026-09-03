"""Subprocess helpers that keep bundled CLI tools invisible on Windows."""

from __future__ import annotations

import asyncio
import os
import subprocess
import uuid
from pathlib import Path
from typing import Any


_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


async def create_hidden_subprocess(*args: Any, **kwargs: Any):
    """Start an asyncio subprocess without flashing a Windows console."""
    if os.name == "nt":
        kwargs["creationflags"] = (
            int(kwargs.get("creationflags", 0)) | _CREATE_NO_WINDOW
        )
    return await asyncio.create_subprocess_exec(*args, **kwargs)


async def iter_stream_records(
    reader: asyncio.StreamReader,
    *,
    chunk_size: int = 4096,
    max_record_bytes: int = 16384,
):
    """Yield bounded records from a byte stream split on CR or LF.

    FFmpeg and several media tools update progress with carriage returns. Using
    ``StreamReader.readline()`` waits for LF and eventually raises once the
    default 64 KiB reader limit is exceeded. Chunked reads avoid that limit and
    the explicit record bound prevents a malformed tool from growing memory
    without limit.
    """
    if chunk_size <= 0 or max_record_bytes <= 0:
        raise ValueError("chunk_size and max_record_bytes must be positive")

    record = bytearray()
    while True:
        chunk = await reader.read(chunk_size)
        if not chunk:
            break
        for byte in chunk:
            if byte in (10, 13):  # LF / CR (CRLF naturally skips the empty half)
                if record:
                    yield bytes(record)
                    record.clear()
                continue
            record.append(byte)
            if len(record) >= max_record_bytes:
                yield bytes(record)
                record.clear()
    if record:
        yield bytes(record)


async def terminate_process(proc: Any, *, timeout: float = 3.0) -> None:
    """Terminate a subprocess tree and reap its root process.

    On Windows, terminating only the asyncio process can orphan children such
    as the FFmpeg process launched by yt-dlp. ``taskkill /T`` walks the tree
    first; it is itself launched through :func:`run_hidden`, so cancellation
    cannot flash a console window.
    """
    if getattr(proc, "returncode", None) is not None:
        return

    pid = getattr(proc, "pid", None)
    if os.name == "nt" and isinstance(pid, int) and pid > 0:
        try:
            await asyncio.to_thread(
                run_hidden,
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        except (FileNotFoundError, OSError):
            # Extremely defensive fallback for stripped-down Windows systems.
            try:
                proc.kill()
            except ProcessLookupError:
                pass
    else:
        try:
            proc.terminate()
        except ProcessLookupError:
            pass

    try:
        await asyncio.wait_for(proc.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            return
        await proc.wait()


async def _read_bounded_tail(
    reader: asyncio.StreamReader | None,
    *,
    max_output_bytes: int,
    chunk_size: int = 4096,
) -> bytes:
    """Drain a stream fully while retaining only a bounded diagnostic tail."""
    if reader is None:
        return b""
    tail = bytearray()
    while True:
        chunk = await reader.read(chunk_size)
        if not chunk:
            return bytes(tail)
        tail.extend(chunk)
        if len(tail) > max_output_bytes:
            del tail[:-max_output_bytes]


async def communicate_with_job(
    proc: Any,
    job: Any = None,
    *,
    max_output_bytes: int = 8192,
) -> tuple[bytes, bytes]:
    """Drain a child with bounded memory while exposing it for cancellation."""
    if max_output_bytes <= 0:
        raise ValueError("max_output_bytes must be positive")
    if job is not None:
        job._process = proc
    stdout_task = asyncio.create_task(
        _read_bounded_tail(
            getattr(proc, "stdout", None), max_output_bytes=max_output_bytes
        )
    )
    stderr_task = asyncio.create_task(
        _read_bounded_tail(
            getattr(proc, "stderr", None), max_output_bytes=max_output_bytes
        )
    )
    try:
        stdout, stderr = await asyncio.gather(stdout_task, stderr_task)
        await proc.wait()
        return stdout, stderr
    except BaseException:
        await terminate_process(proc)
        raise
    finally:
        for task in (stdout_task, stderr_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
        if job is not None and getattr(job, "_process", None) is proc:
            job._process = None


def staging_output_path(output_path: Path | str) -> Path:
    """Return a unique sibling path that preserves the media extension."""
    output_path = Path(output_path)
    return output_path.with_name(
        f".{output_path.stem}.retrodisc-{uuid.uuid4().hex}{output_path.suffix}"
    )


def commit_staged_output(staging_path: Path, output_path: Path) -> None:
    """Atomically publish a completed same-directory media output."""
    os.replace(staging_path, output_path)


def run_hidden(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
    """Run a synchronous CLI helper without flashing a Windows console."""
    if os.name == "nt":
        kwargs["creationflags"] = (
            int(kwargs.get("creationflags", 0)) | _CREATE_NO_WINDOW
        )
    return subprocess.run(*args, **kwargs)


# Redirected Windows CLI output is written in the OEM console codepage
# (cp850 on a German system), while Python's ``text=True`` decodes with the
# ANSI locale codepage (cp1252). Bytes such as 0x81 ("ue" in cp850) are
# undefined in cp1252 and kill subprocess' reader thread with a
# UnicodeDecodeError. Decoding is therefore done explicitly and leniently.
_OUTPUT_ENCODINGS = ("utf-8", "cp850", "cp1252")


def decode_console_output(data: Any) -> str:
    """Decode CLI output without ever raising on unexpected bytes."""
    if data is None:
        return ""
    if isinstance(data, str):
        return data
    for encoding in _OUTPUT_ENCODINGS:
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def run_powershell_hidden(
    script: str, *, timeout: float | None = None
) -> subprocess.CompletedProcess:
    """Run a PowerShell snippet hidden and return safely decoded text.

    The snippet is forced to UTF-8 output; the raw bytes are still decoded
    leniently so a differently encoded error message cannot crash the caller.
    ``subprocess.TimeoutExpired`` propagates unchanged.
    """
    command = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; " + script
    completed = run_hidden(
        ["powershell", "-NoProfile", "-Command", command],
        capture_output=True,
        timeout=timeout,
    )
    return subprocess.CompletedProcess(
        completed.args,
        completed.returncode,
        decode_console_output(completed.stdout),
        decode_console_output(completed.stderr),
    )
