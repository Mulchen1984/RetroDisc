"""HardwareAccelerationService: build detection, probes, status, cache."""
import pytest
from src.services.transcode.process import ProcResult
from src.services.transcode.errors import classify_ffmpeg_error, FFmpegErrorClass as E
from src.services.transcode.capabilities import (
    HardwareAccelerationService, CapabilityCache, CapabilityStatus as S, _probe_status,
)

ENCODERS = """Encoders:
 V....D libx264               H.264
 V....D libx265               H.265
 V....D h264_nvenc            NVIDIA NVENC H.264
 A....D aac                   AAC
"""


class Clock:
    def __init__(self, t=1000.0):
        self.t = t
    def __call__(self):
        return self.t


class FakeFFmpeg:
    def __init__(self, *, version="ffmpeg version 6.1", encoders=ENCODERS, probe=None):
        self.version = version
        self.encoders = encoders
        self.probe = probe or {}
        self.calls = []
    async def __call__(self, args, timeout=None):
        self.calls.append(list(args))
        if "-version" in args:
            return ProcResult(0, self.version, "")
        if "-encoders" in args:
            return ProcResult(0, self.encoders, "")
        enc = args[args.index("-c:v") + 1] if "-c:v" in args else ""
        return self.probe.get(enc, ProcResult(0, "", ""))


# ── error classification ──────────────────────────────────────────────────────
def test_error_classification_table():
    assert classify_ffmpeg_error("No space left on device") == E.OUT_OF_DISK
    assert classify_ffmpeg_error("Permission denied") == E.PERMISSION_DENIED
    assert classify_ffmpeg_error("No such file or directory") == E.INPUT_NOT_FOUND
    assert classify_ffmpeg_error("Unknown encoder 'av1_nvenc'") == E.ENCODER_NOT_AVAILABLE
    assert classify_ffmpeg_error("Cannot init CUDA") == E.HARDWARE_INIT_FAILED
    assert classify_ffmpeg_error("total nonsense here") == E.UNKNOWN     # ehrlicher Fallback
    assert classify_ffmpeg_error("", timed_out=True) == E.PROCESS_TIMEOUT
    assert classify_ffmpeg_error("", cancelled=True) == E.PROCESS_CANCELLED


def test_probe_status_mapping():
    assert _probe_status(ProcResult(0, "", ""))[0] == S.AVAILABLE
    assert _probe_status(ProcResult(None, "", "", timed_out=True))[0] == S.TIMEOUT
    assert _probe_status(ProcResult(1, "", "No NVENC capable devices found"))[0] == S.HARDWARE_MISSING
    assert _probe_status(ProcResult(1, "", "Device lost"))[0] == S.DRIVER_ERROR
    assert _probe_status(ProcResult(1, "", "Cannot load libcuda"))[0] == S.INITIALIZATION_FAILED
    assert _probe_status(ProcResult(1, "", "some other failure"))[0] == S.PROBE_FAILED


# ── detection ─────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_build_encoders_parses_names():
    svc = HardwareAccelerationService(runner=FakeFFmpeg())
    assert {"libx264", "libx265", "h264_nvenc"} <= await svc.build_encoders()


@pytest.mark.asyncio
async def test_detect_marks_available_absent_and_hardware_missing():
    fake = FakeFFmpeg(probe={"h264_nvenc": ProcResult(1, "", "No NVENC capable devices found")})
    caps = await HardwareAccelerationService(runner=fake).detect()
    assert caps["libx264"].status == S.AVAILABLE and caps["libx264"].usable
    assert caps["h264_nvenc"].status == S.HARDWARE_MISSING and not caps["h264_nvenc"].usable
    assert caps["hevc_qsv"].status == S.ABSENT          # nicht im Build
    assert caps["av1_nvenc"].status == S.ABSENT


@pytest.mark.asyncio
async def test_detect_timeout_status():
    fake = FakeFFmpeg(probe={"libx265": ProcResult(None, "", "", timed_out=True)})
    caps = await HardwareAccelerationService(runner=fake).detect()
    assert caps["libx265"].status == S.TIMEOUT


# ── cache ───────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_cache_hit_skips_probing(tmp_path):
    fake = FakeFFmpeg()
    cache = CapabilityCache(tmp_path, now=Clock())
    svc = HardwareAccelerationService(runner=fake)
    await svc.detect(cache=cache)
    fake.calls.clear()
    await svc.detect(cache=cache)                       # Cache-Hit
    assert not any("-encoders" in c for c in fake.calls)   # keine erneute Erkennung


@pytest.mark.asyncio
async def test_cache_force_reprobes(tmp_path):
    fake = FakeFFmpeg()
    cache = CapabilityCache(tmp_path, now=Clock())
    svc = HardwareAccelerationService(runner=fake)
    await svc.detect(cache=cache)
    fake.calls.clear()
    await svc.detect(cache=cache, force=True)
    assert any("-encoders" in c for c in fake.calls)


@pytest.mark.asyncio
async def test_cache_invalidates_on_ffmpeg_version_change(tmp_path):
    cache = CapabilityCache(tmp_path, now=Clock())
    await HardwareAccelerationService(runner=FakeFFmpeg(version="ffmpeg version 6.1")).detect(cache=cache)
    fake2 = FakeFFmpeg(version="ffmpeg version 7.0")     # andere Version -> andere Signatur
    fake2.calls.clear()
    await HardwareAccelerationService(runner=fake2).detect(cache=cache)
    assert any("-encoders" in c for c in fake2.calls)    # neu erkannt statt Cache


def test_cache_ttl_and_corruption(tmp_path):
    clock = Clock(1000.0)
    cache = CapabilityCache(tmp_path, now=clock, ttl_seconds=100)
    from src.services.transcode.capabilities import EncoderCapability
    sig = CapabilityCache.signature("ffmpeg version 6.1")
    cache.set(sig, {"libx264": EncoderCapability("libx264", "h264", "cpu", S.AVAILABLE)})
    assert cache.get(sig) is not None
    clock.t = 1000.0 + 500
    assert cache.get(sig) is None                        # TTL abgelaufen
    clock.t = 1000.0
    (tmp_path / f"caps_{sig}.json").write_text("{broken", encoding="utf-8")
    assert cache.get(sig) is None                        # kaputt -> None, kein Absturz
