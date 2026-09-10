"""Resource slots so jobs don't overload the same GPU / optical drive.

Jobs declare needed resources (e.g. ["NVIDIA_GPU"] or ["OPTICAL_DRIVE:E"]).
The scheduler starts a job only when all its resources have a free slot.
Single event loop, cooperative — no locks needed, no threads.
"""
from __future__ import annotations

from collections import defaultdict
from contextlib import contextmanager

# Known capacities; unknown resources (e.g. OPTICAL_DRIVE:<id>) default to 1.
DEFAULT_CAPACITY = {
    "CPU_TRANSCODE": 2,
    "NVIDIA_GPU": 1,
    "INTEL_GPU": 1,
    "AMD_GPU": 1,
}


class ResourceManager:
    def __init__(self, capacity: dict | None = None):
        self._capacity = dict(DEFAULT_CAPACITY)
        if capacity:
            self._capacity.update(capacity)
        self._in_use: dict[str, int] = defaultdict(int)

    def _cap(self, resource: str) -> int:
        return self._capacity.get(resource, 1)     # optische Laufwerke etc.: exklusiv (1)

    def available(self, resources) -> bool:
        want = defaultdict(int)
        for r in resources or []:
            want[r] += 1
        return all(self._in_use[r] + n <= self._cap(r) for r, n in want.items())

    def acquire(self, resources) -> bool:
        if not self.available(resources):
            return False
        for r in resources or []:
            self._in_use[r] += 1
        return True

    def release(self, resources) -> None:
        for r in resources or []:
            self._in_use[r] = max(0, self._in_use[r] - 1)

    def in_use(self, resource: str) -> int:
        return self._in_use.get(resource, 0)

    @contextmanager
    def lease(self, resources):
        acquired = self.acquire(resources)
        try:
            yield acquired
        finally:
            if acquired:
                self.release(resources)
