"""Resource- and dependency-aware scheduler over the persistent JobQueue.

Runs queued jobs concurrently up to max_parallel, only when their resources are
free and their dependency (if any) has completed. A failed dependency skips the
downstream job. Emits events; a job handler returns (ok, error).
Single event loop (cooperative) — no threads, no DB races.
"""
from __future__ import annotations

import asyncio
import contextlib
from typing import Awaitable, Callable, Optional

import structlog

from src.services.pipeline.queue import JobQueue, PipelineJob, JobState
from src.services.pipeline.resources import ResourceManager
from src.services.pipeline.events import EventBus, Event, EventType

log = structlog.get_logger()

# handler(job, report) -> (ok: bool, error: str); report(pct) updates progress.
Handler = Callable[[PipelineJob, Callable[[float], None]], Awaitable[tuple]]


class Scheduler:
    def __init__(self, queue: JobQueue, resources: Optional[ResourceManager] = None, *,
                 max_parallel: int = 2, events: Optional[EventBus] = None):
        self.queue = queue
        self.resources = resources or ResourceManager()
        self.max_parallel = max_parallel
        if max_parallel < 1:
            raise ValueError("max_parallel muss mindestens 1 sein")
        self.events = events or EventBus()
        self._running: dict[str, asyncio.Task] = {}

    def _emit(self, kind: EventType, job_id: str = "", data: Optional[dict] = None):
        self.events.emit(Event(kind, job_id=job_id, data=data or {}))

    def recover(self) -> list[str]:
        if self._running:
            raise RuntimeError("Recovery nur vor dem Scheduler-Start erlaubt")
        return self.queue.recover()

    def request_cancel(self, job_id: str) -> bool:
        task = self._running.get(job_id)
        if task is not None and not task.done():
            task.cancel()
            return True
        # nicht laufend: aus der Queue nehmen, falls wartend
        job = self.queue.get(job_id)
        if job and job.status in (JobState.QUEUED.value, JobState.PAUSED.value):
            self.queue.mark_cancelled(job_id)
            self._emit(EventType.JOB_CANCELLED, job_id)
            return True
        return False

    def _resources_for(self, job: PipelineJob) -> list[str]:
        res = job.metadata.get("resources", [])
        return list(res) if isinstance(res, (list, tuple)) else []

    def _launch_runnable(self, handler: Handler):
        changed = False
        for job in self.queue.pending():
            if len(self._running) >= self.max_parallel:
                break
            if job.id in self._running:
                continue
            dep = self.queue.dependency_ready(job)
            if dep is False:
                blocker = self.queue.get(job.depends_on)
                if blocker is None:
                    self.queue.mark_failed(job.id, f"Abhängigkeit {job.depends_on} fehlt")
                    self._emit(EventType.JOB_FAILED, job.id, {"reason": "dependency_missing"})
                    changed = True
                elif blocker.status in (JobState.FAILED.value, JobState.CANCELLED.value):
                    self.queue.mark_failed(job.id, f"Abhängigkeit {job.depends_on} fehlgeschlagen")
                    self._emit(EventType.JOB_FAILED, job.id, {"reason": "dependency_failed"})
                    changed = True
                continue                        # Abhängigkeit noch offen -> später
            resources = self._resources_for(job)
            if not self.resources.acquire(resources):
                continue                        # Ressourcen belegt -> warten
            try:
                claimed = self.queue.mark_started(job.id)
            except BaseException:
                self.resources.release(resources)
                raise
            if not claimed:
                self.resources.release(resources)
                continue
            task = asyncio.create_task(self._run_one(handler, job, resources))
            self._running[job.id] = task
            task.add_done_callback(lambda t, j=job, r=resources: self._finished(t, j, r))
        return changed

    def _finished(self, task, job, resources):
        # A task cancelled before its first instruction never enters its finally.
        self.resources.release(resources)
        if task.cancelled():
            current = self.queue.get(job.id)
            if current and current.status != JobState.CANCELLED.value:
                self.queue.mark_cancelled(job.id)
                self._emit(EventType.JOB_CANCELLED, job.id)

    async def _run_one(self, handler: Handler, job: PipelineJob, resources: list[str]):
        def report(pct: float):
            self.queue.set_progress(job.id, pct)
            self._emit(EventType.JOB_PROGRESS, job.id, {"progress": pct})
        try:
            self._emit(EventType.JOB_STARTED, job.id)
            self.queue.mark_running(job.id)
            ok, error = await handler(job, report)
            if ok:
                self.queue.mark_completed(job.id)
                self._emit(EventType.JOB_COMPLETED, job.id)
            else:
                self.queue.mark_failed(job.id, error or "unbekannter Fehler")
                self._emit(EventType.JOB_FAILED, job.id, {"error": error})
        except asyncio.CancelledError:
            self.queue.mark_cancelled(job.id)
            self._emit(EventType.JOB_CANCELLED, job.id)
            raise
        except Exception as exc:                # Handler-Absturz -> Job failed, Scheduler lebt weiter
            self.queue.mark_failed(job.id, str(exc))
            self._emit(EventType.JOB_FAILED, job.id, {"error": str(exc)})

    async def run_all(self, handler: Handler) -> None:
        """Drain the queue: run all runnable jobs, respecting deps/resources/parallelism."""
        try:
            while True:
                changed = self._launch_runnable(handler)
                if not self._running:
                    if changed:
                        continue  # propagate dependency failures regardless of priority/order
                    break
                await asyncio.wait(list(self._running.values()),
                                   return_when=asyncio.FIRST_COMPLETED)
                for job_id, task in list(self._running.items()):
                    if task.done():
                        self._running.pop(job_id, None)
                        with contextlib.suppress(asyncio.CancelledError, Exception):
                            task.result()
        finally:
            tasks = list(self._running.values())
            for task in tasks:
                if not task.done():
                    task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            self._running.clear()
