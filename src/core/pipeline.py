"""RetroDisc Pipeline — Job-Queue & Workflow-Engine."""

from __future__ import annotations

import asyncio
import structlog
from collections import deque
from typing import Callable, Optional

from src.models.media import Job, JobState
from src.utils.sound import play_completion_sound
from src.utils.subprocesses import terminate_process

log = structlog.get_logger()


class Pipeline:
    """
    Verwaltet die Job-Queue und führt Jobs sequenziell oder parallel aus.

    Die Pipeline ist das Herzstück von RetroDisc — alle Operationen
    (Konvertierung, Download, Brennen, AI-Features) laufen als Jobs
    durch diese Queue.

    Beispiel:
        pipeline = Pipeline(max_concurrent=2)
        pipeline.on_job_complete = my_callback

        job = Job(job_type=JobType.CONVERT, input_files=[...])
        await pipeline.submit(job)
        await pipeline.start()
    """

    def __init__(self, max_concurrent: int = 1, play_sound: bool = True):
        self.max_concurrent = max_concurrent
        self.play_sound = play_sound
        self._queue: deque[Job] = deque()
        self._running: list[Job] = []
        self._completed: list[Job] = []
        self._tasks: dict[str, asyncio.Task] = {}
        self._is_running = False
        self._lock = asyncio.Lock()

        # Callbacks
        self.on_job_complete: Optional[Callable[[Job], None]] = None
        self.on_job_failed: Optional[Callable[[Job], None]] = None
        self.on_queue_empty: Optional[Callable[[], None]] = None

        # Job-Handler Registry
        self._handlers: dict[str, Callable] = {}
        # Dynamische Bridge-Aufträge können pro Job unterschiedliche
        # Closures/Parameter besitzen. Ein reines Typ-Registry würde den
        # Handler älterer, noch wartender Jobs beim nächsten Submit ersetzen.
        self._job_handlers: dict[str, Callable] = {}

    def register_handler(self, job_type: str, handler: Callable) -> None:
        """Registriert einen Handler für einen Job-Typ."""
        self._handlers[job_type] = handler
        log.info("Handler registriert", job_type=job_type)

    async def submit(self, job: Job, handler: Optional[Callable] = None) -> str:
        """Fügt einen Job zur Queue hinzu."""
        async with self._lock:
            if handler is not None:
                self._job_handlers[job.id] = handler
            self._queue.append(job)
            log.info("Job submitted", job_id=job.id, type=job.job_type.value,
                     queue_size=len(self._queue))
        return job.id

    async def start(self) -> None:
        """Startet die Pipeline — läuft als Daemon bis stop() aufgerufen wird."""
        if self._is_running:
            log.warning("Pipeline läuft bereits")
            return

        self._is_running = True
        log.info("Pipeline gestartet", max_concurrent=self.max_concurrent)
        _notified_empty = False

        try:
            while self._is_running:
                async with self._lock:
                    while self._queue and len(self._running) < self.max_concurrent:
                        job = self._queue.popleft()
                        self._running.append(job)
                        self._tasks[job.id] = asyncio.create_task(self._execute_job(job))
                        _notified_empty = False

                # Queue-Leer-Event einmalig senden
                if not self._queue and not self._running and not _notified_empty:
                    _notified_empty = True
                    if self.on_queue_empty:
                        self.on_queue_empty()

                await asyncio.sleep(0.05)

        finally:
            self._is_running = False
            log.info("Pipeline gestoppt")

    async def stop(self) -> None:
        """Stoppt die Pipeline nach Abschluss laufender Jobs."""
        self._is_running = False
        log.info("Pipeline Stop angefordert")

    async def shutdown(self) -> None:
        """Stoppt Queue und laufende Jobs inklusive nativer Prozesse."""
        self._is_running = False
        async with self._lock:
            job_ids = [job.id for job in self._queue] + [job.id for job in self._running]
        for job_id in job_ids:
            await self.cancel_job(job_id)
        for _ in range(100):
            if not self._running:
                break
            await asyncio.sleep(0.01)
        log.info("Pipeline heruntergefahren", remaining=len(self._running))

    async def cancel_job(self, job_id: str) -> bool:
        """Bricht einen Job ab."""
        async with self._lock:
            # In Queue suchen
            for job in self._queue:
                if job.id == job_id:
                    self._queue.remove(job)
                    self._job_handlers.pop(job.id, None)
                    job.mark_cancelled()
                    log.info("Job aus Queue entfernt", job_id=job_id)
                    return True

            # In Running suchen
            for job in self._running:
                if job.id == job_id:
                    job.mark_cancelled()
                    process = getattr(job, "_process", None)
                    if process is not None and getattr(process, "returncode", None) is None:
                        await terminate_process(process)
                    task = self._tasks.get(job_id)
                    if task is not None and task is not asyncio.current_task():
                        task.cancel()
                    log.info("Laufender Job abgebrochen", job_id=job_id)
                    return True

        return False

    async def _execute_job(self, job: Job) -> None:
        """Führt einen einzelnen Job aus."""
        job.mark_running()
        log.info("Job gestartet", job_id=job.id, type=job.job_type.value)

        try:
            handler = self._job_handlers.pop(job.id, None)
            if handler is None:
                handler = self._handlers.get(job.job_type.value)
            if handler is None:
                raise ValueError(f"Kein Handler für Job-Typ: {job.job_type.value}")

            await handler(job)

            if job.state != JobState.CANCELLED:
                job.mark_done()
                log.info("Job abgeschlossen", job_id=job.id,
                         elapsed=f"{job.elapsed_seconds:.1f}s")

                if self.play_sound:
                    play_completion_sound()

                if self.on_job_complete:
                    try:
                        self.on_job_complete(job)
                    except Exception as observer_error:
                        log.error(
                            "Completion-Observer fehlgeschlagen",
                            job_id=job.id,
                            error=str(observer_error),
                        )

        except Exception as e:
            if job.state == JobState.CANCELLED:
                log.info("Job-Abbruch bestätigt", job_id=job.id)
            else:
                job.mark_failed(str(e))
                log.error("Job fehlgeschlagen", job_id=job.id, error=str(e))

                if self.on_job_failed:
                    try:
                        self.on_job_failed(job)
                    except Exception as observer_error:
                        log.error(
                            "Failure-Observer fehlgeschlagen",
                            job_id=job.id,
                            error=str(observer_error),
                        )

        finally:
            self._job_handlers.pop(job.id, None)
            self._tasks.pop(job.id, None)
            async with self._lock:
                if job in self._running:
                    self._running.remove(job)
                self._completed.append(job)

    @property
    def queue_size(self) -> int:
        return len(self._queue)

    @property
    def running_count(self) -> int:
        return len(self._running)

    @property
    def completed_jobs(self) -> list[Job]:
        return list(self._completed)

    def get_job(self, job_id: str) -> Optional[Job]:
        """Sucht einen Job in Queue, Running oder Completed."""
        for job in list(self._queue) + self._running + self._completed:
            if job.id == job_id:
                return job
        return None

    def clear_completed(self) -> None:
        """Löscht abgeschlossene Jobs aus der Historie."""
        self._completed.clear()
