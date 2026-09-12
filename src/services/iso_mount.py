"""Temporäres, sauber aufgeräumtes Mounten von DVD-/Blu-ray-ISO-Dateien.

Nur für die Wiedergabe gedacht: ein ISO wird kurz gemountet, damit die
bereits vorhandene VIDEO_TS-/BDMV-Erkennung (``player_source.py``,
``disc_analyzer.py``) unverändert auf den Mount-Pfad angewendet werden kann -
kein separater ISO-Reader. Jeder erfolgreiche ``mount()`` MUSS über
``unmount()`` (idealerweise via ``async with mount_iso(...)``) wieder gelöst
werden; es bleiben keine dauerhaften Mounts zurück.

macOS: ``hdiutil attach/detach`` (real gegen ein UDF-ISO getestet).
Windows: ``Mount-DiskImage``/``Dismount-DiskImage`` (PowerShell, seit
Windows 8 Bordmittel - dieselbe Kategorie Werkzeug, die
``dvd_workflow.py::_eject`` bereits für Windows-Disc-Operationen nutzt).
Beide Zweige nutzen ``create_hidden_subprocess``/``terminate_process`` wie
jedes andere externe Werkzeug in diesem Projekt.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
from pathlib import Path
from typing import AsyncIterator, Optional

import structlog

from src.utils.subprocesses import create_hidden_subprocess

log = structlog.get_logger()


class IsoMountError(Exception):
    pass


class MountedIso:
    """Repräsentiert einen aktiven ISO-Mount. Niemals direkt konstruieren -
    über ``mount_iso()``/``async with mount_iso(...)``."""

    def __init__(self, root: Path, *, _device: Optional[str] = None):
        self.root = root
        self._device = _device
        self._unmounted = False

    async def unmount(self) -> None:
        if self._unmounted:
            return
        self._unmounted = True
        if os.name == "nt":
            await _windows_dismount(self.root)
        else:
            await _macos_detach(self._device)


async def _macos_attach(iso_path: Path) -> MountedIso:
    proc = await create_hidden_subprocess(
        "hdiutil", "attach", "-nobrowse", "-readonly", "-plist",
        "-mountrandom", "/tmp", str(iso_path),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise IsoMountError(f"ISO konnte nicht gemountet werden: {stderr.decode('utf-8', errors='replace')[-500:]}")

    import plistlib
    plist = plistlib.loads(stdout)
    mount_point = None
    device = None
    for entity in plist.get("system-entities", []):
        if entity.get("mount-point"):
            mount_point = entity["mount-point"]
            device = entity.get("dev-entry")
            break
    if not mount_point:
        raise IsoMountError("hdiutil hat kein Dateisystem im ISO erkannt (kein mount-point).")
    return MountedIso(Path(mount_point), _device=device)


async def _macos_detach(device: Optional[str]) -> None:
    if not device:
        return
    proc = await create_hidden_subprocess(
        "hdiutil", "detach", device, "-force",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        log.warning("hdiutil detach fehlgeschlagen", device=device,
                   error=stderr.decode("utf-8", errors="replace")[-300:])


async def _windows_attach(iso_path: Path) -> MountedIso:
    ps = (
        "$img = Mount-DiskImage -ImagePath '{path}' -PassThru; "
        "$vol = $img | Get-Volume; "
        "Write-Output ($vol.DriveLetter)"
    ).format(path=str(iso_path).replace("'", "''"))
    proc = await create_hidden_subprocess(
        "powershell.exe", "-NoProfile", "-Command", ps,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise IsoMountError(f"ISO konnte nicht gemountet werden: {stderr.decode('utf-8', errors='replace')[-500:]}")
    drive_letter = stdout.decode("utf-8", errors="replace").strip()
    if not drive_letter or not re.fullmatch(r"[A-Za-z]", drive_letter):
        raise IsoMountError("Mount-DiskImage hat keinen Laufwerksbuchstaben zurückgegeben.")
    return MountedIso(Path(f"{drive_letter}:/"), _device=str(iso_path))


async def _windows_dismount(root: Path) -> None:
    ps = "Dismount-DiskImage -ImagePath '{path}'".format(path=root.as_posix())
    proc = await create_hidden_subprocess(
        "powershell.exe", "-NoProfile", "-Command", ps,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        log.warning("Dismount-DiskImage fehlgeschlagen",
                   error=stderr.decode("utf-8", errors="replace")[-300:])


async def mount(iso_path: Path) -> MountedIso:
    iso_path = Path(iso_path)
    if not iso_path.is_file():
        raise IsoMountError(f"ISO-Datei nicht gefunden: {iso_path}")
    if os.name == "nt":
        return await _windows_attach(iso_path)
    return await _macos_attach(iso_path)


@contextlib.asynccontextmanager
async def mount_iso(iso_path: Path) -> AsyncIterator[MountedIso]:
    """Bevorzugter Einstieg: garantiertes Unmount, auch bei einer Exception
    während der Wiedergabe."""
    mounted = await mount(iso_path)
    try:
        yield mounted
    finally:
        await mounted.unmount()
