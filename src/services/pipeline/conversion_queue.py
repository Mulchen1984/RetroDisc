"""Persistent UI conversions using the existing Converter and Scheduler.

Owned entirely by the bridge's asyncio loop (including SQLite). Other job types
continue using their existing handlers. Startup never silently resumes work.
"""
import asyncio
import sys
from pathlib import Path

from src.config.presets import get_preset
from src.models.media import Job, JobType
from src.services.pipeline.events import EventBus, EventType
from src.services.pipeline.queue import JobQueue, PipelineJob, JobState
from src.services.pipeline.scheduler import Scheduler
from src.services.pipeline.resources import ResourceManager
from src.services.transcode.probe import MediaProbeService
from src.services.transcode.verify import verify_transcode


class ConversionQueue:
    def __init__(self, db_path, converter, emit, complete, max_parallel=1):
        self.queue = JobQueue(db_path)
        self.converter, self.emit, self.complete = converter, emit, complete
        self.queue.recover()
        for job in self.queue.pending():
            self.queue.pause(job.id)
        self.events = EventBus()
        self.events.subscribe(self._event)
        self.scheduler = Scheduler(self.queue, ResourceManager({'CPU_TRANSCODE': max_parallel}),
                                   max_parallel=max_parallel, events=self.events)
        self.worker = None
        self.closed = False

    def _event(self, event):
        row = self.queue.get(event.job_id)
        if not row:
            return
        name = row.metadata.get('display_name', Path(row.source).name)
        names = {EventType.JOB_STARTED: 'job_progress', EventType.JOB_PROGRESS: 'job_progress',
                 EventType.JOB_FAILED: 'job_failed', EventType.JOB_CANCELLED: 'job_cancelled'}
        if event.type in names:
            self.emit(names[event.type], {'id': row.id, 'name': name, 'progress': row.progress,
                                         'error': row.error, 'status': row.status})

    def _wake(self):
        if self.closed:
            raise RuntimeError('Queue wird beendet.')
        if self.worker is None or self.worker.done():
            self.worker = asyncio.create_task(self.scheduler.run_all(self._handle))

    async def submit(self, job):
        if self.closed:
            raise RuntimeError('Queue wird beendet.')
        row = PipelineJob(id=job.id, type='convert', source=str(job.input_files[0].resolve()),
            destination=str(job.output_path.absolute()) if job.output_path else '',
            profile=job.params['preset_name'], max_retries=3, metadata={
                **job.params, 'resources': ['CPU_TRANSCODE' if job.params['encoder']=='cpu' else 'VIDEO_ENCODER']})
        self.queue.enqueue(row)
        self._wake()
        return row.id

    async def _handle(self, row, report):
        preset = get_preset(row.profile)
        job = Job(id=row.id, job_type=JobType.CONVERT, input_files=[Path(row.source)],
                  output_path=Path(row.destination) if row.destination else None,
                  preset=preset, params=dict(row.metadata))
        job.mark_running()
        job.on_progress = lambda percent, text: report(min(percent, 99))
        # Reuse the established converter: includes native hardware/CPU fallback,
        # final path resolution, atomic output handling and process cancellation.
        output = await self.converter.convert_file(job.input_files[0], preset, job.output_path,
            job=job, overwrite=bool(row.metadata.get('overwrite')) if row.retry_count == 0 else False,
            hwaccel=row.metadata.get('encoder', 'auto') if sys.platform == 'darwin' else None)
        self.queue.set_status(row.id, JobState.VERIFYING)
        probe = MediaProbeService(self.converter.ffmpeg.ffprobe_path)
        if preset.video_codec:
            verification = await verify_transcode(output, probe)
            if verification.status not in ('PASS', 'PASS_WITH_WARNINGS'):
                return False, verification.message
        else:
            info = await probe.probe(str(output))
            if not info.audio or info.duration <= 0:
                return False, 'Audioausgabe konnte nicht verifiziert werden.'
        self.queue.update_metadata(row.id, {'output_path': str(output), 'verified': True})
        job.output_path = Path(output)
        job.mark_done()
        self.complete(job)  # existing Recent Media registration + job_done event
        return True, ''

    async def rows(self):
        states = {'queued': 'pending', 'preparing': 'running', 'verifying': 'running',
                  'completed': 'done'}
        return [{'id': row.id, 'name': row.metadata.get('display_name', Path(row.source).name),
                 'state': states.get(row.status, row.status), 'progress': row.progress,
                 'error': row.error, 'persistent': True,
                 'can_retry': (row.status in ('failed', 'interrupted') and row.retry_count < row.max_retries) or row.status == 'paused',
                 'retry_count': row.retry_count, 'max_retries': row.max_retries,
                 'output': row.metadata.get('output_path') if row.status == 'completed' else None}
                for row in self.queue.all()]

    async def cancel(self, job_id):
        if not self.queue.get(job_id):
            return None
        return self.scheduler.request_cancel(job_id)

    async def retry(self, job_id):
        row = self.queue.get(job_id)
        if not row or self.closed:
            return False
        ok = self.queue.resume(job_id) if row.status == 'paused' else self.queue.retry(job_id)
        if ok:
            self._wake()
        return ok

    async def shutdown(self):
        self.closed = True
        active = [job.id for job in self.queue.running()]
        if self.worker and not self.worker.done():
            self.worker.cancel()
            await asyncio.gather(self.worker, return_exceptions=True)
        for job_id in active:
            self.queue.set_status(job_id, JobState.INTERRUPTED,
                                  error='App beendet; erneuten Start bestätigen.', finished=None)
        self.queue.close()
