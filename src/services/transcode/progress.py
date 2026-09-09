"""Parser for FFmpeg `-progress pipe:1` output. Tolerant of odd/partial lines."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ProgressSnapshot:
    frame: int = 0
    fps: float = 0.0
    bitrate: str = ""
    total_size: int = 0
    out_time_seconds: float = 0.0
    speed: float = 0.0
    status: str = ""                 # "continue" | "end"
    percent: Optional[float] = None
    eta_seconds: Optional[float] = None


def _to_int(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _timestamp_to_seconds(value: str) -> Optional[float]:
    # "HH:MM:SS.micro"
    try:
        h, m, s = value.split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)
    except (ValueError, AttributeError):
        return None


def _speed(value: str) -> float:
    try:
        return float(str(value).lower().rstrip("x").strip())
    except (TypeError, ValueError):
        return 0.0


class FFmpegProgressParser:
    def __init__(self, total_duration: Optional[float] = None):
        self.total_duration = total_duration if (total_duration or 0) > 0 else None
        self._acc: dict[str, str] = {}

    def feed_line(self, line: str) -> Optional[ProgressSnapshot]:
        """Accumulate key=value lines; return a snapshot when a block ends."""
        line = (line or "").strip()
        if not line or "=" not in line:
            return None                    # merkwürdige/unvollständige Zeile ignorieren
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        self._acc[key] = value
        if key != "progress":
            return None
        snapshot = self._snapshot(status=value)
        self._acc = {}                     # nächster Block beginnt frisch
        return snapshot

    def feed(self, text: str) -> list[ProgressSnapshot]:
        out = []
        for line in text.splitlines():
            snap = self.feed_line(line)
            if snap is not None:
                out.append(snap)
        return out

    def _out_time(self) -> float:
        stamped = self._acc.get("out_time")
        seconds = _timestamp_to_seconds(stamped) if stamped and stamped != "N/A" else None
        if seconds is None and self._acc.get("out_time_us", "").isdigit():
            seconds = int(self._acc["out_time_us"]) / 1_000_000
        return round(seconds, 3) if seconds is not None else 0.0

    def _snapshot(self, *, status: str) -> ProgressSnapshot:
        out_time = self._out_time()
        speed = _speed(self._acc.get("speed", ""))
        fps = 0.0
        try:
            fps = float(self._acc.get("fps", "0") or 0)
        except ValueError:
            fps = 0.0
        percent = eta = None
        if self.total_duration:
            percent = max(0.0, min(100.0, round(out_time / self.total_duration * 100, 1)))
            if status == "end":
                percent = 100.0
            remaining = max(0.0, self.total_duration - out_time)
            if speed > 0:
                eta = round(remaining / speed, 1)
        return ProgressSnapshot(
            frame=_to_int(self._acc.get("frame")), fps=fps,
            bitrate=self._acc.get("bitrate", "") or "", total_size=_to_int(self._acc.get("total_size")),
            out_time_seconds=out_time, speed=speed, status=status, percent=percent, eta_seconds=eta)
