"""TranscodeService: end-to-end orchestration of the transcoding pipeline.

MediaProbe -> HardwareCapability -> Profile -> EncoderSelection ->
FFmpegCommandBuilder -> TranscodingJob (+progress) -> Verification.

Every external call (ffprobe, ffmpeg detection, the transcode process) is
injected, so the full pipeline is unit-testable without FFmpeg; the defaults use
the real process helpers.
"""
from __future__ import annotations

from typing import Optional

import structlog

from src.services.transcode.process import run_process
from src.services.transcode.capabilities import HardwareAccelerationService, CapabilityCache
from src.services.transcode.probe import MediaProbeService, SourceMediaInfo
from src.services.transcode.profiles import get_profile
from src.services.transcode.selection import EncoderSelectionEngine, EncoderSelection, SelectionPrefs
from src.services.transcode.command import FFmpegCommandBuilder
from src.services.transcode.job import (
    TranscodingJob, TranscodingState, run_transcode, _default_spawn,
)
from src.services.transcode.errors import FFmpegErrorClass
from src.services.transcode.verify import verify_transcode
from src.utils.subprocesses import terminate_process

log = structlog.get_logger()


class TranscodePlan:
    def __init__(self, info: SourceMediaInfo, selection: EncoderSelection, args: list[str]):
        self.info = info
        self.selection = selection
        self.args = args


class TranscodeService:
    def __init__(self, *, ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe", runner=run_process,
                 hardware: Optional[HardwareAccelerationService] = None,
                 probe: Optional[MediaProbeService] = None,
                 builder: Optional[FFmpegCommandBuilder] = None,
                 cache: Optional[CapabilityCache] = None):
        self.probe = probe or MediaProbeService(ffprobe, runner=runner)
        self.hardware = hardware or HardwareAccelerationService(ffmpeg, runner=runner)
        self.builder = builder or FFmpegCommandBuilder(ffmpeg)
        self.engine = EncoderSelectionEngine()
        self.cache = cache

    async def plan(self, source: str, destination: str, profile_name: str, *,
                   prefs: Optional[SelectionPrefs] = None, overwrite: bool = False) -> TranscodePlan:
        info = await self.probe.probe(source)
        profile = get_profile(profile_name)
        capabilities = await self.hardware.detect(cache=self.cache)
        selection = self.engine.select(profile, capabilities, info.to_hints(), prefs)
        args = self.builder.build(info, profile, selection, destination,
                                  overwrite=overwrite, progress=True) if selection.ok else []
        return TranscodePlan(info, selection, args)

    async def transcode(self, source: str, destination: str, profile_name: str, *,
                        prefs: Optional[SelectionPrefs] = None, overwrite: bool = False,
                        verify: bool = True, on_progress=None, timeout: Optional[float] = None,
                        cancel_event=None, spawn=_default_spawn, terminator=terminate_process):
        job = TranscodingJob(source=source, destination=destination, profile_name=profile_name)
        job.verification = None

        job.mark_probing()
        info = await self.probe.probe(source)

        job.mark_selecting()
        profile = get_profile(profile_name)
        capabilities = await self.hardware.detect(cache=self.cache)
        selection = self.engine.select(profile, capabilities, info.to_hints(), prefs)
        if not selection.ok:
            job.fail(FFmpegErrorClass.ENCODER_NOT_AVAILABLE,
                     detail="; ".join(selection.reasons) or "Kein nutzbarer Encoder")
            return job
        job.selected_encoder = selection.encoder
        job.warnings.extend(selection.warnings)

        job.mark_preparing()
        args = self.builder.build(info, profile, selection, destination,
                                  overwrite=overwrite, progress=True)

        await run_transcode(job, args, total_duration=info.duration, spawn=spawn,
                            terminator=terminator, on_progress=on_progress,
                            timeout=timeout, cancel_event=cancel_event)

        if job.state == TranscodingState.COMPLETED and verify:
            job.mark_verifying()
            result = await verify_transcode(destination, self.probe,
                                            expected_duration=info.duration,
                                            expected_codec=selection.codec)
            job.verification = result.to_dict()
            if result.status == "FAIL":
                # Erfolg vortäuschen wäre falsch: Verifikation schlägt fehl -> Job fehlgeschlagen.
                job.state = TranscodingState.FAILED
                job.error_class = job.error_class or FFmpegErrorClass.OUTPUT_WRITE_ERROR.value
                job.error_detail = job.error_detail or result.message
            else:
                job.mark_completed(job.exit_code or 0)
        return job
