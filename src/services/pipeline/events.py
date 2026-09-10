"""Tiny in-process event bus for later UI wiring. No browser/WebSocket coupling.

A broken listener is isolated: its exception is logged and never propagates, so
it can't corrupt a job or block other listeners.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

import structlog

log = structlog.get_logger()


class EventType(str, Enum):
    JOB_QUEUED = "job_queued"
    JOB_STARTED = "job_started"
    JOB_PROGRESS = "job_progress"
    JOB_FAILED = "job_failed"
    JOB_COMPLETED = "job_completed"
    JOB_CANCELLED = "job_cancelled"
    MEDIA_ANALYZED = "media_analyzed"
    LIBRARY_UPDATED = "library_updated"


@dataclass
class Event:
    type: EventType
    job_id: str = ""
    data: dict = field(default_factory=dict)


class EventBus:
    def __init__(self):
        self._listeners: list[Callable[[Event], None]] = []

    def subscribe(self, callback: Callable[[Event], None]) -> Callable[[], None]:
        self._listeners.append(callback)

        def unsubscribe():
            if callback in self._listeners:
                self._listeners.remove(callback)
        return unsubscribe

    def emit(self, event: Event) -> None:
        for listener in list(self._listeners):
            try:
                listener(event)
            except Exception as exc:            # defekter Listener darf nichts kaputtmachen
                log.warning("events: Listener-Fehler ignoriert",
                            event_type=event.type.value, error=str(exc))
