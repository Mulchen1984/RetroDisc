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
