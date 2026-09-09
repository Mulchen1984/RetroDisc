"""Central temp-file management: unique per-job dirs, cleanup, crash recovery.

Production concerns handled here:
* configurable temp root (sensible OS default),
* unique per-job/session directories (jobs never overwrite each other),
* automatic cleanup on success, safe handling on error/abort,
* optional free-space precheck before a job starts,
* deletions are hard-guarded to RetroDisc job dirs *inside* the root — nothing
  outside our own temp area can ever be removed,
* Windows file-lock tolerance (bounded retry, then best-effort),
* structured logging, no raw tracebacks leaking to callers.
"""
from __future__ import annotations

import re
import shutil
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

import structlog

from src.services.disk_space import ensure_space

log = structlog.get_logger()

_PREFIX = "retrodisc-job-"
_SAFE = re.compile(r"[^A-Za-z0-9_-]")


class TempManager:
    def __init__(self, root=None):
        # Konfigurierbarer Temp-Pfad mit sinnvollem Default (plattformneutral).
        self.root = Path(root) if root else Path(tempfile.gettempdir()) / "RetroDisc"

    # ── ids / paths ─────────────────────────────────────────────────────
    @staticmethod
    def _safe_id(job_id) -> str:
        cleaned = _SAFE.sub("_", str(job_id)).strip("_")
        return cleaned or "job"          # nie leer -> trifft nie das Wurzelverzeichnis

    def job_dir(self, job_id, *, create: bool = True) -> Path:
        path = self.root / f"{_PREFIX}{self._safe_id(job_id)}"
        if create:
            path.mkdir(parents=True, exist_ok=True)
        return path

    def allocate(self, job_id, name: str) -> Path:
        """Path for one artifact inside the job dir; callers reuse it so the same
        large image is never held twice."""
        safe_name = Path(str(name)).name or "artifact"     # kein Pfad-Ausbruch
        return self.job_dir(job_id) / safe_name

    # ── space ───────────────────────────────────────────────────────────
    def ensure_space(self, required_bytes: int, **kwargs):
        """Raise StorageError early if the temp filesystem lacks room."""
        self.root.mkdir(parents=True, exist_ok=True)
        return ensure_space(self.root, required_bytes, **kwargs)

    # ── deletion (hard-guarded) ─────────────────────────────────────────
    def _is_own_job_dir(self, path: Path) -> bool:
        try:
            resolved = path.resolve()
            root = self.root.resolve()
        except OSError:
            return False
        return path.name.startswith(_PREFIX) and root in resolved.parents

    def _safe_rmtree(self, path: Path) -> bool:
        """Remove a job dir, refusing anything outside our own temp area."""
        path = Path(path)
        if not self._is_own_job_dir(path):
            log.warning("temp: Löschen außerhalb eigener Job-Verzeichnisse abgelehnt", path=str(path))
            return False
        for attempt in range(3):
            shutil.rmtree(path, ignore_errors=(attempt == 2))   # Windows-Sperre: kurz erneut versuchen
            if not path.exists():
                return True
            time.sleep(0.1)
        remaining = path.exists()
        if remaining:
            log.warning("temp: Verzeichnis konnte nicht vollständig entfernt werden", path=str(path))
        return not remaining

    def cleanup(self, job_id) -> bool:
        path = self.job_dir(job_id, create=False)
        if path.is_dir():
            return self._safe_rmtree(path)
        return False

    def cleanup_stale(self, max_age_seconds: int = 86400) -> list[str]:
        """Reclaim leftover job dirs older than max_age (crash recovery)."""
        removed = []
        if not self.root.is_dir():
            return removed
        cutoff = time.time() - max_age_seconds
        for path in self.root.glob(f"{_PREFIX}*"):
            try:
                if path.is_dir() and path.stat().st_mtime < cutoff and self._safe_rmtree(path):
                    removed.append(path.name)
            except OSError as exc:
                log.debug("temp: stale-cleanup übersprungen", path=str(path), error=str(exc))
        if removed:
            log.info("temp: verwaiste Job-Verzeichnisse entfernt", count=len(removed))
        return removed

    # ── session ─────────────────────────────────────────────────────────
    @contextmanager
    def session(self, job_id, *, required_bytes: Optional[int] = None, keep_on_error: bool = False):
        """Yield the job dir. Optional space precheck; remove on success, and on
        error unless keep_on_error (diagnostics)."""
        if required_bytes:
            self.ensure_space(required_bytes)          # StorageError vor dem Anlegen
        path = self.job_dir(job_id)
        log.debug("temp: Session gestartet", job=str(job_id), path=str(path))
        try:
            yield path
        except BaseException:
            if not keep_on_error:
                self._safe_rmtree(path)
            else:
                log.info("temp: Session-Fehler – Diagnoseartefakte behalten", path=str(path))
            raise
        else:
            self._safe_rmtree(path)
