"""Real CPU workflow acceptance plus negative import gates (no physical-disc claims)."""
import asyncio
import hashlib
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from src.services.pipeline.analysis import MediaAnalysisOrchestrator
from src.services.pipeline.events import EventBus, EventType
from src.services.pipeline.queue import JobQueue
from src.services.pipeline.scheduler import Scheduler
from src.services.pipeline.workflow import FileWorkflow
from src.services.library_catalog import LibraryService
from src.services.metadata import MetadataService, MetadataCache
from src.services.transcode.probe import MediaProbeService
from src.services.transcode.service import TranscodeService
from src.services.transcode.job import TranscodingState
from src.services.transcode.process import ProcResult

FFMPEG, FFPROBE = shutil.which('ffmpeg'), shutil.which('ffprobe')
pytestmark = pytest.mark.skipif(not (FFMPEG and FFPROBE), reason='FFmpeg/ffprobe fehlen')


@pytest.fixture
def source(tmp_path):
    source = tmp_path / 'Quelle ä & Test.mp4'
    subprocess.run([FFMPEG, '-v', 'error', '-f', 'lavfi', '-i',
        'testsrc2=size=160x120:rate=15:duration=2', '-f', 'lavfi', '-i',
        'sine=frequency=440:duration=2', '-c:v', 'libx264', '-c:a', 'aac',
        '-shortest', str(source)], check=True, timeout=30)
    return source


def setup(q, library, events):
    transcode = TranscodeService(ffmpeg=FFMPEG, ffprobe=FFPROBE)
    analysis = MediaAnalysisOrchestrator(probe=transcode.probe, library=library,
        metadata=MetadataService(cache=MetadataCache(q.db_path.parent / 'metadata')))
    return FileWorkflow(q, analysis, transcode, library, events)


@pytest.mark.asyncio
async def test_real_cpu_workflow_persistence_decode_library(source, tmp_path):
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    events, seen = EventBus(), []
    def broken(event): raise RuntimeError('kaputter UI-Listener')
    events.subscribe(broken)
    events.subscribe(lambda event: seen.append(event.type))
    destination = tmp_path / 'Ausgabe.mp4'
    with JobQueue(tmp_path / 'queue.db') as q, LibraryService(tmp_path / 'catalog.db') as library:
        workflow = setup(q, library, events)
        job = await workflow.enqueue(source, destination)
        assert job.metadata['recommendation']['recommended_profile'] == 'h264_compatibility'
    # Queue + catalog reopened as on application restart; jobs carry their plan.
    with JobQueue(tmp_path / 'queue.db') as q, LibraryService(tmp_path / 'catalog.db') as library:
        scheduler = Scheduler(q, events=events)
        assert scheduler.recover() == []
        workflow = setup(q, library, events)
        await scheduler.run_all(workflow)
        done = q.get(job.id)
        assert done.status == 'completed', done.error
        assert done.metadata['encoder'] == 'libx264'
        assert done.metadata['verification']['status'] == 'PASS'
        assert done.metadata['provenance']['full_decode'] is True
        assert done.progress == 100
        item = library.get(done.metadata['library_fingerprint'])
        assert item.rip_path == str(destination) and item.last_verified
        assert not list(tmp_path.glob('.*.retrodisc-*'))
        assert scheduler.resources.in_use('CPU_TRANSCODE') == 0
        assert EventType.JOB_PROGRESS in seen and EventType.LIBRARY_UPDATED in seen
        assert EventType.JOB_COMPLETED in seen
        info = await workflow.transcode.probe.probe(str(destination))
        assert abs(info.duration - 2) < .2 and info.primary_video.codec == 'h264' and info.audio
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before


@pytest.mark.asyncio
@pytest.mark.parametrize('state,verification,decode_ok', [
    (TranscodingState.FAILED, {'status': 'PASS'}, True),
    (TranscodingState.COMPLETED, None, True),
    (TranscodingState.COMPLETED, {'status': 'FAIL'}, True),
    (TranscodingState.COMPLETED, {'status': 'NOT_AVAILABLE'}, True),
    (TranscodingState.COMPLETED, {'status': 'PASS'}, False),
])
async def test_failed_or_unverified_never_imported(source, tmp_path, state, verification, decode_ok):
    with JobQueue(tmp_path / 'q.db') as q, LibraryService(tmp_path / 'l.db') as library:
        workflow = setup(q, library, EventBus())
        job = await workflow.enqueue(source, tmp_path / 'out.mp4')
        async def transcode(src, dst, profile, **kw):
            from pathlib import Path
            Path(dst).write_bytes(b'partial')
            return SimpleNamespace(state=state, verification=verification,
                selected_encoder='libx264', error_detail='test failure')
        async def decode(args, timeout=None): return ProcResult(0 if decode_ok else 1)
        workflow.transcode.transcode = transcode
        workflow.runner = decode
        await Scheduler(q).run_all(workflow)
        assert q.get(job.id).status == 'failed'
        assert library.all() == []
        assert not (tmp_path / 'out.mp4').exists()
        assert not list(tmp_path.glob('.*.retrodisc-*'))


@pytest.mark.asyncio
async def test_existing_output_and_changed_source_preserved(source, tmp_path):
    with JobQueue(tmp_path / 'q.db') as q, LibraryService(tmp_path / 'l.db') as library:
        workflow = setup(q, library, EventBus())
        destination = tmp_path / 'out.mp4'
        job = await workflow.enqueue(source, destination)
        destination.write_bytes(b'user file')
        await Scheduler(q).run_all(workflow)
        assert q.get(job.id).status == 'failed' and destination.read_bytes() == b'user file'
        assert library.all() == []
        other = await workflow.enqueue(source, tmp_path / 'other.mp4')
        source.unlink()
        await Scheduler(q).run_all(workflow)
        assert q.get(other.id).status == 'failed' and library.all() == []


@pytest.mark.asyncio
async def test_real_ffmpeg_task_cancel_stops_child(source):
    from src.services.transcode.job import run_transcode, TranscodingJob, _default_spawn
    started, processes = asyncio.Event(), []
    async def spawn(args):
        proc = await _default_spawn(args)
        processes.append(proc)
        return proc
    task = asyncio.create_task(run_transcode(TranscodingJob(), [FFMPEG, '-v', 'error',
        '-nostdin', '-stream_loop', '-1', '-re', '-i', str(source),
        '-progress', 'pipe:1', '-f', 'null', '-'], spawn=spawn,
        on_progress=lambda snapshot: started.set()))
    try:
        await asyncio.wait_for(started.wait(), 10)
        assert processes[0].returncode is None
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
    assert processes[0].returncode is not None


@pytest.mark.asyncio
async def test_cancel_workflow_cleans_staging_and_catalog(source, tmp_path):
    with JobQueue(tmp_path / 'q.db') as q, LibraryService(tmp_path / 'l.db') as library:
        workflow = setup(q, library, EventBus())
        job = await workflow.enqueue(source, tmp_path / 'out.mp4')
        started = asyncio.Event()
        async def transcode(src, dst, profile, **kw):
            from pathlib import Path
            Path(dst).write_bytes(b'partial')
            started.set()
            await asyncio.Event().wait()
        workflow.transcode.transcode = transcode
        s = Scheduler(q)
        task = asyncio.create_task(s.run_all(workflow))
        await started.wait()
        s.request_cancel(job.id)
        await task
        assert q.get(job.id).status == 'cancelled' and not library.all()
        assert not (tmp_path / 'out.mp4').exists()
        assert not list(tmp_path.glob('.*.retrodisc-*'))
        assert s.resources.in_use('CPU_TRANSCODE') == 0
