"""Hardware/encoder capability detection via real controlled FFmpeg probes.

Distinguishes: present in the FFmpeg build, hardware present, encoder actually
initialisable, and a successful probe encode. Results are cached against an
environment signature (FFmpeg version + platform + host + optional GPU hint)
with a TTL; a broken cache never blocks detection.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import socket
import tempfile
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

import structlog

from src.services.transcode.process import ProcResult, run_process

log = structlog.get_logger()

CACHE_SCHEMA = 1
DEFAULT_CACHE_TTL = 7 * 24 * 3600


class CapabilityStatus(str, Enum):
    AVAILABLE = "AVAILABLE"                 # probe encode succeeded
    BUILD_SUPPORTED = "BUILD_SUPPORTED"     # in build, not (yet) probe-confirmed
    ABSENT = "ABSENT"                       # not in this FFmpeg build
    HARDWARE_MISSING = "HARDWARE_MISSING"
    DRIVER_ERROR = "DRIVER_ERROR"
    INITIALIZATION_FAILED = "INITIALIZATION_FAILED"
    PROBE_FAILED = "PROBE_FAILED"
    TIMEOUT = "TIMEOUT"
    UNKNOWN = "UNKNOWN"


USABLE = {CapabilityStatus.AVAILABLE}

# (codec, vendor, ffmpeg encoder name). CPU AV1 tries SVT-AV1 then libaom.
KNOWN_ENCODERS: list[tuple[str, str, str]] = [
    ("h264", "cpu", "libx264"), ("h265", "cpu", "libx265"),
    ("av1", "cpu", "libsvtav1"), ("av1", "cpu", "libaom-av1"),
    ("h264", "nvidia", "h264_nvenc"), ("h265", "nvidia", "hevc_nvenc"), ("av1", "nvidia", "av1_nvenc"),
    ("h264", "intel", "h264_qsv"), ("h265", "intel", "hevc_qsv"), ("av1", "intel", "av1_qsv"),
    ("h264", "amd", "h264_amf"), ("h265", "amd", "hevc_amf"), ("av1", "amd", "av1_amf"),
]


@dataclass
class EncoderCapability:
    name: str
    codec: str
    vendor: str
    status: CapabilityStatus = CapabilityStatus.UNKNOWN
    detail: str = ""

    @property
    def usable(self) -> bool:
        return self.status in USABLE

    def to_dict(self) -> dict:
        return {"name": self.name, "codec": self.codec, "vendor": self.vendor,
                "status": self.status.value, "detail": self.detail}

    @classmethod
    def from_dict(cls, d: dict) -> "EncoderCapability":
        return cls(name=d["name"], codec=d["codec"], vendor=d["vendor"],
                   status=CapabilityStatus(d.get("status", "UNKNOWN")), detail=d.get("detail", ""))


def _probe_status(result: ProcResult) -> tuple[CapabilityStatus, str]:
    if result.timed_out:
        return CapabilityStatus.TIMEOUT, "Probe-Encode Timeout"
    if result.ok:
        return CapabilityStatus.AVAILABLE, ""
    low = (result.stderr or "").lower()
    tail = (result.stderr or "").strip()[-300:]
    if any(x in low for x in ("no capable device", "no nvenc capable", "no device",
                              "cannot open the device", "device not found", "no such device")):
        return CapabilityStatus.HARDWARE_MISSING, tail
    if any(x in low for x in ("driver", "version mismatch", "device lost", "device removed")):
        return CapabilityStatus.DRIVER_ERROR, tail
    if any(x in low for x in ("cannot load", "cannot init", "failed to init", "openencode",
                              "device creation failed", "not implemented", "hwaccel")):
        return CapabilityStatus.INITIALIZATION_FAILED, tail
    return CapabilityStatus.PROBE_FAILED, tail


class CapabilityCache:
    def __init__(self, cache_dir, *, now=time.time, ttl_seconds: int = DEFAULT_CACHE_TTL):
        self.cache_dir = Path(cache_dir)
        self._now = now
        self.ttl_seconds = ttl_seconds

    @staticmethod
    def signature(ffmpeg_version: str, *, gpu_hint: str = "") -> str:
        raw = "|".join([ffmpeg_version or "", platform.platform(), platform.machine(),
                        socket.gethostname(), gpu_hint or ""])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]

    def _path(self, signature: str) -> Path:
        return self.cache_dir / f"caps_{signature}.json"

    def get(self, signature: str) -> Optional[dict]:
        path = self._path(signature)
        if not path.is_file():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if raw.get("schema") != CACHE_SCHEMA or raw.get("signature") != signature:
                return None                      # Umgebung/Schema geändert -> invalidieren
            if (self._now() - raw.get("created", 0)) > raw.get("ttl", self.ttl_seconds):
                return None                      # TTL abgelaufen
            return {name: EncoderCapability.from_dict(d) for name, d in raw.get("capabilities", {}).items()}
        except (ValueError, OSError, KeyError) as exc:
            log.warning("capabilities: beschädigter Cache ignoriert", error=str(exc))
            return None                          # kaputter Cache blockiert nichts

    def set(self, signature: str, capabilities: dict) -> None:
        record = {"schema": CACHE_SCHEMA, "signature": signature, "created": self._now(),
                  "ttl": self.ttl_seconds,
                  "capabilities": {name: cap.to_dict() for name, cap in capabilities.items()}}
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        temp = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.cache_dir,
                                             delete=False) as handle:
                temp = Path(handle.name)
                json.dump(record, handle, ensure_ascii=False, indent=2)
                handle.flush(); os.fsync(handle.fileno())
            temp.replace(self._path(signature)); temp = None
        except OSError as exc:
            log.warning("capabilities: Cache konnte nicht geschrieben werden", error=str(exc))
        finally:
            if temp is not None:
                temp.unlink(missing_ok=True)


class HardwareAccelerationService:
    def __init__(self, ffmpeg_path: str = "ffmpeg", *, runner=run_process,
                 probe_timeout: float = 20.0):
        self.ffmpeg_path = ffmpeg_path
        self._run = runner
        self.probe_timeout = probe_timeout

    async def ffmpeg_version(self) -> str:
        result = await self._run([self.ffmpeg_path, "-hide_banner", "-version"], 10)
        first = (result.stdout or result.stderr or "").splitlines()
        return first[0].strip() if first else "unknown"

    async def build_encoders(self) -> set[str]:
        result = await self._run([self.ffmpeg_path, "-hide_banner", "-encoders"], 15)
        names = set()
        for line in (result.stdout or "").splitlines():
            m = re.match(r"\s*[A-Z.]{6}\s+([A-Za-z0-9_\-]+)", line)
            if m:
                names.add(m.group(1))
        return names

    def probe_args(self, encoder: str) -> list[str]:
        return [self.ffmpeg_path, "-hide_banner", "-nostdin",
                "-f", "lavfi", "-i", "testsrc2=size=128x128:rate=5:duration=1",
                "-frames:v", "3", "-pix_fmt", "yuv420p", "-c:v", encoder, "-f", "null", "-"]

    async def probe_encoder(self, encoder: str) -> tuple[CapabilityStatus, str]:
        result = await self._run(self.probe_args(encoder), self.probe_timeout)
        return _probe_status(result)

    async def detect(self, *, cache: Optional[CapabilityCache] = None, force: bool = False,
                     gpu_hint: str = "") -> dict[str, EncoderCapability]:
        signature = None
        if cache is not None:
            signature = CapabilityCache.signature(await self.ffmpeg_version(), gpu_hint=gpu_hint)
            if not force:
                cached = cache.get(signature)
                if cached is not None:
                    return cached
        build = await self.build_encoders()
        capabilities: dict[str, EncoderCapability] = {}
        for codec, vendor, name in KNOWN_ENCODERS:
            cap = EncoderCapability(name=name, codec=codec, vendor=vendor)
            if name not in build:
                cap.status = CapabilityStatus.ABSENT
            else:
                cap.status, cap.detail = await self.probe_encoder(name)
            capabilities[name] = cap
        if cache is not None and signature is not None:
            cache.set(signature, capabilities)
        return capabilities

    @staticmethod
    def usable_encoders(capabilities: dict[str, EncoderCapability]) -> dict[str, EncoderCapability]:
        return {n: c for n, c in capabilities.items() if c.usable}
