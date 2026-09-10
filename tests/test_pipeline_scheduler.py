"""EventBus, ResourceManager and Scheduler (dependencies + resource slots)."""
import asyncio
import pytest
from src.services.pipeline.events import EventBus, Event, EventType
from src.services.pipeline.resources import ResourceManager
from src.services.pipeline.queue import JobQueue, PipelineJob, JobState
from src.services.pipeline.scheduler import Scheduler


# ── events ────────────────────────────────────────────────────────────────────
def test_event_bus_order_and_unsubscribe():
    bus = EventBus()
    seen = []
    off = bus.subscribe(lambda e: seen.append(e.type))
    bus.emit(Event(EventType.JOB_STARTED)); bus.emit(Event(EventType.JOB_COMPLETED))
    off()
    bus.emit(Event(EventType.JOB_FAILED))
    assert seen == [EventType.JOB_STARTED, EventType.JOB_COMPLETED]   # nach off() nichts mehr


def test_broken_listener_does_not_break_others():
    bus = EventBus()
    good = []
    bus.subscribe(lambda e: (_ for _ in ()).throw(RuntimeError("kaputt")))
    bus.subscribe(lambda e: good.append(e.type))
    bus.emit(Event(EventType.JOB_PROGRESS))
    assert good == [EventType.JOB_PROGRESS]                          # zweiter Listener lief


# ── resources ─────────────────────────────────────────────────────────────────
def test_resource_capacity_and_exclusivity():
    rm = ResourceManager()
    assert rm.acquire(["NVIDIA_GPU"]) and not rm.acquire(["NVIDIA_GPU"])   # GPU exklusiv
    rm.release(["NVIDIA_GPU"]); assert rm.acquire(["NVIDIA_GPU"])
    assert rm.acquire(["INTEL_GPU"])                                 # andere GPU frei
    # optisches Laufwerk exklusiv (unbekannte Ressource -> Kapazität 1)
    assert rm.acquire(["OPTICAL_DRIVE:E"]) and not rm.acquire(["OPTICAL_DRIVE:E"])


def test_resource_lease_releases_on_exit():
    rm = ResourceManager()
    with rm.lease(["AMD_GPU"]) as ok:
        assert ok and rm.in_use("AMD_GPU") == 1
    assert rm.in_use("AMD_GPU") == 0


# ── scheduler ─────────────────────────────────────────────────────────────────
def _tracking_handler(peak):
    async def handler(job, report):
        peak["cur"] += 1
        peak["max"] = max(peak["max"], peak["cur"])
        report(50.0)
        await asyncio.sleep(0.02)
        peak["cur"] -= 1
        return (True, "")
    return handler


@pytest.mark.asyncio
async def test_runs_pending_and_emits(tmp_path):
    jq = JobQueue(tmp_path / "q.db")
    jq.enqueue(PipelineJob(id="a", metadata={"resources": ["CPU_TRANSCODE"]}))
    events = EventBus(); seen = []
    events.subscribe(lambda e: seen.append(e.type))
    sched = Scheduler(jq, ResourceManager(), max_parallel=2, events=events)
    await sched.run_all(_tracking_handler({"cur": 0, "max": 0}))
    assert jq.get("a").status == JobState.COMPLETED.value and jq.get("a").progress == 100.0
    assert EventType.JOB_STARTED in seen and EventType.JOB_COMPLETED in seen
    jq.close()


@pytest.mark.asyncio
async def test_same_gpu_serialised_different_gpu_parallel(tmp_path):
    jq = JobQueue(tmp_path / "q.db")
    jq.enqueue(PipelineJob(id="g1", metadata={"resources": ["NVIDIA_GPU"]}))
    jq.enqueue(PipelineJob(id="g2", metadata={"resources": ["NVIDIA_GPU"]}))
    peak = {"cur": 0, "max": 0}
    await Scheduler(jq, ResourceManager(), max_parallel=4).run_all(_tracking_handler(peak))
    assert peak["max"] == 1                                          # gleiche GPU nie parallel
    jq.close()

    jq2 = JobQueue(tmp_path / "q2.db")
    jq2.enqueue(PipelineJob(id="n", metadata={"resources": ["NVIDIA_GPU"]}))
    jq2.enqueue(PipelineJob(id="i", metadata={"resources": ["INTEL_GPU"]}))
    peak2 = {"cur": 0, "max": 0}
    await Scheduler(jq2, ResourceManager(), max_parallel=4).run_all(_tracking_handler(peak2))
    assert peak2["max"] == 2                                         # verschiedene GPUs parallel
    jq2.close()


@pytest.mark.asyncio
async def test_dependency_success_chain(tmp_path):
    jq = JobQueue(tmp_path / "q.db")
    jq.enqueue(PipelineJob(id="dep"))
    jq.enqueue(PipelineJob(id="child", depends_on="dep"))
    ran = []

    async def handler(job, report):
        ran.append(job.id)
        return (True, "")
    await Scheduler(jq, ResourceManager()).run_all(handler)
    assert ran == ["dep", "child"] and jq.get("child").status == JobState.COMPLETED.value
    jq.close()


@pytest.mark.asyncio
async def test_dependency_failure_skips_downstream(tmp_path):
    jq = JobQueue(tmp_path / "q.db")
    jq.enqueue(PipelineJob(id="dep"))
    jq.enqueue(PipelineJob(id="child", depends_on="dep"))

    async def handler(job, report):
        return (job.id != "dep", "dep kaputt" if job.id == "dep" else "")
    await Scheduler(jq, ResourceManager()).run_all(handler)
    assert jq.get("dep").status == JobState.FAILED.value
    child = jq.get("child")
    assert child.status == JobState.FAILED.value and "fehlgeschlagen" in child.error   # übersprungen
    jq.close()


@pytest.mark.asyncio
async def test_handler_exception_marks_failed_and_continues(tmp_path):
    jq = JobQueue(tmp_path / "q.db")
    jq.enqueue(PipelineJob(id="boom"))
    jq.enqueue(PipelineJob(id="ok"))

    async def handler(job, report):
        if job.id == "boom":
            raise RuntimeError("Absturz")
        return (True, "")
    await Scheduler(jq, ResourceManager(), max_parallel=1).run_all(handler)
    assert jq.get("boom").status == JobState.FAILED.value and "Absturz" in jq.get("boom").error
    assert jq.get("ok").status == JobState.COMPLETED.value          # Scheduler lief weiter
    jq.close()


@pytest.mark.asyncio
async def test_retry_then_rerun_succeeds(tmp_path):
    jq = JobQueue(tmp_path / "q.db")
    jq.enqueue(PipelineJob(id="a", max_retries=1))
    attempts = {"n": 0}

    async def handler(job, report):
        attempts["n"] += 1
        return (attempts["n"] > 1, "erst fehlgeschlagen")
    await Scheduler(jq, ResourceManager()).run_all(handler)
    assert jq.get("a").status == JobState.FAILED.value
    assert jq.retry("a")                                            # requeue
    await Scheduler(jq, ResourceManager()).run_all(handler)
    assert jq.get("a").status == JobState.COMPLETED.value and attempts["n"] == 2
    jq.close()

@pytest.mark.asyncio
async def test_cancel_before_task_start_releases_resource(tmp_path):
    with JobQueue(tmp_path / 'q.db') as q:
        q.enqueue(PipelineJob(id='a', metadata={'resources': ['NVIDIA_GPU']}))
        s = Scheduler(q)
        async def handler(job, report):
            pytest.fail('cancelled job must not start')
        s._launch_runnable(handler)
        assert s.request_cancel('a')
        await s.run_all(handler)
        assert q.get('a').status == 'cancelled'
        assert s.resources.in_use('NVIDIA_GPU') == 0


@pytest.mark.asyncio
async def test_scheduler_shutdown_cancels_children(tmp_path):
    with JobQueue(tmp_path / 'q.db') as q:
        q.enqueue(PipelineJob(id='a', metadata={'resources': ['OPTICAL_DRIVE:E']}))
        s = Scheduler(q)
        started, stopped = asyncio.Event(), asyncio.Event()
        async def handler(job, report):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()
        task = asyncio.create_task(s.run_all(handler))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert stopped.is_set()
        assert q.get('a').status == 'cancelled'
        assert not s._running
        assert s.resources.in_use('OPTICAL_DRIVE:E') == 0


@pytest.mark.asyncio
async def test_parent_retry_unblocks_unstarted_descendants(tmp_path):
    with JobQueue(tmp_path / 'q.db') as q:
        for job in [PipelineJob(id='p'), PipelineJob(id='c', depends_on='p'),
                    PipelineJob(id='g', depends_on='c')]:
            q.enqueue(job)
        s = Scheduler(q)
        async def fail(job, report): return False, 'broken parent'
        await s.run_all(fail)
        assert q.get('g').status == 'failed'
        assert q.retry('p')
        seen = []
        async def good(job, report):
            seen.append(job.id)
            return True, ''
        await s.run_all(good)
        assert seen == ['p', 'c', 'g']
        assert q.get('p').retry_count == 1
        assert q.get('c').retry_count == 0


@pytest.mark.asyncio
async def test_broken_listener_during_workflow_and_failed_resource_job(tmp_path):
    with JobQueue(tmp_path / 'q.db') as q:
        for name in ['bad', 'good']:
            q.enqueue(PipelineJob(id=name, metadata={'resources': ['NVIDIA_GPU']}))
        bus, seen = EventBus(), []
        def broken(event): raise RuntimeError('listener')
        bus.subscribe(broken)
        bus.subscribe(lambda event: seen.append((event.job_id, event.type)))
        s = Scheduler(q, events=bus)
        async def handler(job, report):
            report(25)
            if job.id == 'bad': raise ValueError('handler')
            return True, ''
        await s.run_all(handler)
        assert q.get('bad').status == 'failed'
        assert q.get('good').status == 'completed'
        assert ('good', EventType.JOB_COMPLETED) in seen
        assert s.resources.in_use('NVIDIA_GPU') == 0


@pytest.mark.asyncio
async def test_missing_dependency_and_reverse_priority_failure_propagation(tmp_path):
    with JobQueue(tmp_path / 'q.db') as q:
        q.enqueue(PipelineJob(id='p', depends_on='missing'))
        q.enqueue(PipelineJob(id='c', depends_on='p', priority=1))
        q.enqueue(PipelineJob(id='g', depends_on='c', priority=2))
        async def handler(job, report): pytest.fail('must not run')
        await Scheduler(q).run_all(handler)
        assert all(j.status == 'failed' and 'Abhängigkeit' in j.error for j in q.all())


@pytest.mark.asyncio
async def test_queued_and_running_cancel_release_drive_for_next_job(tmp_path):
    with JobQueue(tmp_path / 'q.db') as q:
        for name in ['queued', 'running', 'next']:
            q.enqueue(PipelineJob(id=name, metadata={'resources': ['OPTICAL_DRIVE:E']}))
        s = Scheduler(q)
        assert s.request_cancel('queued')
        started = asyncio.Event()
        async def handler(job, report):
            if job.id == 'running':
                started.set()
                await asyncio.Event().wait()
            return True, ''
        task = asyncio.create_task(s.run_all(handler))
        await started.wait()
        assert s.request_cancel('running')
        await task
        assert [q.get(n).status for n in ['queued', 'running', 'next']] == ['cancelled', 'cancelled', 'completed']
        assert s.resources.in_use('OPTICAL_DRIVE:E') == 0
