"""Persistent SQLite job queue that survives restarts.

Jobs are stored in their own DB (PRAGMA user_version schema, busy_timeout for
concurrency). On open, jobs that were mid-flight (running/preparing/verifying)
are recovered to INTERRUPTED — a crashed process never leaves a phantom RUNNING
job. Supports FIFO+priority ordering, retry, dependencies and history.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

import structlog

from src.core.errors import QueueError

log = structlog.get_logger()

SCHEMA_VERSION = 1
_ACTIVE = ("running", "preparing", "verifying")
_COLUMNS = ("id", "type", "source", "destination", "profile", "status", "priority",
            "created", "started", "finished", "progress", "error", "retry_count",
            "max_retries", "depends_on", "metadata_json")


class JobState(str, Enum):
    QUEUED = "queued"
    PREPARING = "preparing"
    RUNNING = "running"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"
    PAUSED = "paused"


TERMINAL = {JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED}


@dataclass
class PipelineJob:
    type: str = "transcode"
    source: str = ""
    destination: str = ""
    profile: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: str = JobState.QUEUED.value
    priority: int = 0
    created: Optional[float] = None
    started: Optional[float] = None
    finished: Optional[float] = None
    progress: float = 0.0
    error: str = ""
    retry_count: int = 0
    max_retries: int = 1
    depends_on: str = ""
    metadata: dict = field(default_factory=dict)

    def to_row(self) -> dict:
        row = {k: getattr(self, k) for k in _COLUMNS if k != "metadata_json"}
        row["metadata_json"] = json.dumps(self.metadata or {}, ensure_ascii=False)
        return row

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "PipelineJob":
        data = {k: row[k] for k in _COLUMNS if k != "metadata_json"}
        try:
            data["metadata"] = json.loads(row["metadata_json"] or "{}")
        except (ValueError, TypeError):
            data["metadata"] = {}
        return cls(**data)


class JobQueue:
    def __init__(self, db_path, *, now=time.time):
        self.db_path = Path(db_path)
        self._now = now
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._conn = sqlite3.connect(str(self.db_path), timeout=5.0)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA busy_timeout = 5000")
            self._migrate()
        except sqlite3.DatabaseError as exc:
            raise QueueError(f"Queue-Datenbank ungültig/beschädigt: {self.db_path}",
                             detail=str(exc)) from exc

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _migrate(self):
        version = self._conn.execute("PRAGMA user_version").fetchone()[0]
        if version < 1:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS pipeline_jobs (
                    id TEXT PRIMARY KEY, type TEXT, source TEXT, destination TEXT,
                    profile TEXT, status TEXT, priority INTEGER DEFAULT 0,
                    created REAL, started REAL, finished REAL, progress REAL DEFAULT 0,
                    error TEXT DEFAULT '', retry_count INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 1, depends_on TEXT DEFAULT '',
                    metadata_json TEXT DEFAULT '{}'
                )""")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON pipeline_jobs(status)")
            self._conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            self._conn.commit()

    # ── recovery ────────────────────────────────────────────────────────
    def recover(self) -> list[str]:
        """Mid-flight jobs from a crashed process -> INTERRUPTED. Returns their ids."""
        rows = self._conn.execute(
            f"SELECT id FROM pipeline_jobs WHERE status IN ({','.join('?' * len(_ACTIVE))})",
            _ACTIVE).fetchall()
        ids = [r["id"] for r in rows]
        if ids:
            with self._conn:
                self._conn.execute(
                    f"UPDATE pipeline_jobs SET status='interrupted' WHERE status IN "
                    f"({','.join('?' * len(_ACTIVE))})", _ACTIVE)
            log.info("queue: unterbrochene Jobs wiederhergestellt", count=len(ids))
        return ids

    # ── writes ──────────────────────────────────────────────────────────
    def enqueue(self, job: PipelineJob) -> PipelineJob:
        if job.created is None:
            job.created = self._now()
        if not job.status:
            job.status = JobState.QUEUED.value
        placeholders = ",".join(f":{c}" for c in _COLUMNS)
        with self._conn:
            self._conn.execute(
                f"INSERT INTO pipeline_jobs ({','.join(_COLUMNS)}) VALUES ({placeholders})",
                job.to_row())
        return job

    def _set(self, job_id: str, **fields) -> bool:
        if not fields:
            return False
        assignments = ",".join(f"{k}=:{k}" for k in fields)
        fields["id"] = job_id
        with self._conn:
            cur = self._conn.execute(
                f"UPDATE pipeline_jobs SET {assignments} WHERE id=:id", fields)
        return cur.rowcount > 0

    def set_status(self, job_id: str, status: JobState, **fields) -> bool:
        value = status.value if isinstance(status, JobState) else status
        return self._set(job_id, status=value, **fields)

    def set_progress(self, job_id: str, percent: float) -> bool:
        return self._set(job_id, progress=max(0.0, min(100.0, float(percent))))

    def mark_started(self, job_id: str) -> bool:
        return self.set_status(job_id, JobState.PREPARING, started=self._now())

    def mark_running(self, job_id: str) -> bool:
        return self.set_status(job_id, JobState.RUNNING)

    def mark_completed(self, job_id: str) -> bool:
        return self.set_status(job_id, JobState.COMPLETED, progress=100.0, finished=self._now())

    def mark_failed(self, job_id: str, error: str = "") -> bool:
        return self.set_status(job_id, JobState.FAILED, error=error, finished=self._now())

    def mark_cancelled(self, job_id: str) -> bool:
        return self.set_status(job_id, JobState.CANCELLED, finished=self._now())

    def pause(self, job_id: str) -> bool:
        job = self.get(job_id)
        if job and job.status == JobState.QUEUED.value:
            return self.set_status(job_id, JobState.PAUSED)
        return False

    def resume(self, job_id: str) -> bool:
        job = self.get(job_id)
        if job and job.status == JobState.PAUSED.value:
            return self.set_status(job_id, JobState.QUEUED)
        return False

    def retry(self, job_id: str) -> bool:
        job = self.get(job_id)
        if not job or job.status not in (JobState.FAILED.value, JobState.INTERRUPTED.value):
            return False
        if job.retry_count >= job.max_retries:
            return False
        return self.set_status(job_id, JobState.QUEUED, retry_count=job.retry_count + 1,
                               error="", started=None, finished=None, progress=0.0)

    def remove(self, job_id: str) -> bool:
        with self._conn:
            cur = self._conn.execute("DELETE FROM pipeline_jobs WHERE id=?", (job_id,))
        return cur.rowcount > 0

    def clear_completed(self) -> int:
        with self._conn:
            cur = self._conn.execute("DELETE FROM pipeline_jobs WHERE status='completed'")
        return cur.rowcount

    # ── reads ───────────────────────────────────────────────────────────
    def get(self, job_id: str) -> Optional[PipelineJob]:
        row = self._conn.execute("SELECT * FROM pipeline_jobs WHERE id=?", (job_id,)).fetchone()
        return PipelineJob.from_row(row) if row else None

    def all(self) -> list[PipelineJob]:
        rows = self._conn.execute("SELECT * FROM pipeline_jobs ORDER BY created").fetchall()
        return [PipelineJob.from_row(r) for r in rows]

    def by_status(self, status: JobState) -> list[PipelineJob]:
        value = status.value if isinstance(status, JobState) else status
        rows = self._conn.execute("SELECT * FROM pipeline_jobs WHERE status=? ORDER BY created",
                                  (value,)).fetchall()
        return [PipelineJob.from_row(r) for r in rows]

    def pending(self) -> list[PipelineJob]:
        rows = self._conn.execute(
            "SELECT * FROM pipeline_jobs WHERE status='queued' "
            "ORDER BY priority DESC, created ASC").fetchall()
        return [PipelineJob.from_row(r) for r in rows]

    def running(self) -> list[PipelineJob]:
        rows = self._conn.execute(
            f"SELECT * FROM pipeline_jobs WHERE status IN ({','.join('?' * len(_ACTIVE))})",
            _ACTIVE).fetchall()
        return [PipelineJob.from_row(r) for r in rows]

    def dependency_ready(self, job: PipelineJob) -> Optional[bool]:
        """None = no dependency; True = dependency completed; False = pending/failed."""
        if not job.depends_on:
            return None
        dep = self.get(job.depends_on)
        if dep is None:
            return False
        return dep.status == JobState.COMPLETED.value

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM pipeline_jobs").fetchone()[0]

    def close(self):
        self._conn.close()
