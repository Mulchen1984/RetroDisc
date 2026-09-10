"""File workflow adapter over the existing analysis, queue, transcode and catalog.

Only verified, fully decodable output is published/imported. Physical-disc
operations are deliberately left to their existing backends. No UI coupling.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from src.services.fingerprint import fingerprint
from src.services.library_catalog import LibraryItem
from src.services.pipeline.events import Event, EventType
from src.services.pipeline.queue import PipelineJob, JobState
from src.services.pipeline.recommend import ProfileRecommendationEngine, ProfileGoal
from src.services.pipeline.source import SourceKind
from src.services.transcode.job import TranscodingState
from src.services.transcode.process import run_process
from src.services.transcode.selection import SelectionPrefs
from src.utils.subprocesses import staging_output_path


class FileWorkflow:
    def __init__(self, queue, analysis, transcode, library, events, *, runner=run_process):
        self.queue = queue
        self.analysis = analysis
        self.transcode = transcode
        self.library = library
        self.events = events
        self.runner = runner
        self.recommend = ProfileRecommendationEngine()

    @staticmethod
    def _stamp(path):
        stat = Path(path).stat()
        return {'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns}

    async def enqueue(self, source, destination, *, goal=ProfileGoal.COMPATIBILITY,
                      depends_on='', max_retries=1):
        source, destination = Path(source).resolve(), Path(destination).absolute()
        if source == destination.resolve() or destination.exists() or destination.is_symlink():
            raise ValueError('Ziel existiert bereits oder entspricht der Quelle.')
        before = self._stamp(source)
        result = await self.analysis.analyze(str(source))
        if (result.errors or result.source.kind != SourceKind.FILE or
                not result.media_info or not result.media_info.primary_video or
                result.media_info.duration <= 0):
            raise ValueError('Keine lesbare Videodatei mit gültiger Dauer.')
        if self._stamp(source) != before:
            raise ValueError('Quelle wurde während der Analyse verändert.')
        recommendation = self.recommend.recommend(result, goal)
        job = PipelineJob(source=str(source), destination=str(destination),
            profile=recommendation.recommended_profile, depends_on=depends_on,
            max_retries=max_retries, metadata={
                'resources': ['CPU_TRANSCODE', 'OUTPUT:' + os.path.normcase(str(destination.resolve()))],
                'source_stamp': before, 'analysis': result.to_dict(),
                'source_fingerprint': result.fingerprint,
                'recommendation': recommendation.to_dict(), 'encoder_policy': 'cpu'})
        self.queue.enqueue(job)
        self.events.emit(Event(EventType.MEDIA_ANALYZED, job.id, result.to_dict()))
        self.events.emit(Event(EventType.JOB_QUEUED, job.id))
        return job

    async def __call__(self, job, report):
        if job.type != 'transcode':
            return False, 'Nicht unterstützter Workflow-Typ.'
        source, destination = Path(job.source), Path(job.destination)
        if self._stamp(source) != job.metadata.get('source_stamp'):
            return False, 'Quelle wurde seit der Analyse verändert.'
        if source.resolve() == destination.resolve() or destination.exists() or destination.is_symlink():
            return False, 'Zieldatei existiert bereits; nichts überschrieben.'
        if not destination.parent.is_dir():
            return False, 'Zielverzeichnis fehlt.'
        staged = staging_output_path(destination)
        # Stored before starting: after a crash, recovery can identify this job's
        # partial output. It is never imported or automatically resumed.
        self.queue.update_metadata(job.id, {'staging_path': str(staged)})
        try:
            def progress(snapshot):
                if snapshot.percent is not None:
                    report(min(snapshot.percent, 99))
            encoded = await self.transcode.transcode(job.source, str(staged), job.profile,
                prefs=SelectionPrefs(allow_hardware=False, prefer_hardware=False),
                verify=True, on_progress=progress)
            verification = encoded.verification or {}
            self.queue.update_metadata(job.id, {'verification': verification,
                                                'encoder': encoded.selected_encoder})
            if encoded.state != TranscodingState.COMPLETED or verification.get('status') not in ('PASS', 'PASS_WITH_WARNINGS'):
                return False, encoded.error_detail or 'Ausgabe nicht erfolgreich verifiziert.'
            self.queue.set_status(job.id, JobState.VERIFYING)
            decoded = await self.runner([self.transcode.builder.ffmpeg_path,
                '-hide_banner', '-nostdin', '-v', 'error', '-xerror', '-i', str(staged),
                '-map', '0:v', '-map', '0:a?', '-f', 'null', '-'], timeout=600)
            if not decoded.ok:
                return False, 'Vollständige Decoderprüfung fehlgeschlagen.'
            if self._stamp(source) != job.metadata['source_stamp']:
                return False, 'Quelle wurde während der Verarbeitung verändert.'
            provenance = {'job_id': job.id, 'source_fingerprint': job.metadata['source_fingerprint'],
                'profile': job.profile, 'encoder': encoded.selected_encoder,
                'verification': verification, 'full_decode': True,
                'output_bytes': staged.stat().st_size, 'verified_at': time.time()}
            self.queue.update_metadata(job.id, {'provenance': provenance})
            # Exclusive atomic publication on the same filesystem; never replace
            # a file created by another job/user while FFmpeg was running.
            os.link(staged, destination)
            item = LibraryItem(
                fingerprint=fingerprint({'label': job.id, 'files': [
                    {'path': destination.name, 'size': provenance['output_bytes']}]}),
                title=destination.stem, source_type='file', rip_path=str(destination),
                last_verified=provenance['verified_at'], metadata={'provenance': provenance})
            self.library.add_or_update(item)
            self.queue.update_metadata(job.id, {'library_fingerprint': item.fingerprint})
            self.events.emit(Event(EventType.LIBRARY_UPDATED, job.id,
                                   {'fingerprint': item.fingerprint, 'output': str(destination)}))
            return True, ''
        finally:
            staged.unlink(missing_ok=True)
