"""Subprocess helpers that keep bundled CLI tools invisible on Windows."""

from __future__ import annotations

import asyncio
import os
import subprocess
from typing import Any


_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


async def create_hidden_subprocess(*args: Any, **kwargs: Any):
    """Start an asyncio subprocess without flashing a Windows console."""
    if os.name == "nt":
        kwargs["creationflags"] = (
            int(kwargs.get("creationflags", 0)) | _CREATE_NO_WINDOW
        )
    return await asyncio.create_subprocess_exec(*args, **kwargs)


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
