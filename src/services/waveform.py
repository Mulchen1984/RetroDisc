"""Real, cached audio peak data for the timeline. No dummy/constant peaks.

Path: Mediendatei -> ffmpeg PCM (mono, dauerabhängige Rate) -> Peak-Buckets ->
Disk-Cache (an Datei+mtime+size gebunden) -> Timeline-UI schneidet pro Clip.

Kein Vollladen der Audiodatei nach JavaScript: der Client bekommt nur die
kompakten Peak-Werte (<= `buckets` Zahlen) je Quelle und schneidet clientseitig
das Clip-Fenster [start,end] heraus.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import tempfile
from pathlib import Path

from src.utils.subprocesses import create_hidden_subprocess


class Waveform:
    VERSION = 1
    TARGET_SAMPLES = 2_000_000        # obere Schranke für Speicher/Analysezeit
    MAX_RATE = 8000
    MIN_RATE = 200

    def __init__(self, ffmpeg, cache_dir):
        self.ffmpeg = ffmpeg
        self.cache_dir = Path(cache_dir)

    def _cache_path(self, path: Path, stat, buckets: int) -> Path:
        digest = hashlib.sha256(str(path).encode('utf-8')).hexdigest()[:16]
        return self.cache_dir / f"{digest}_{stat.st_size}_{stat.st_mtime_ns}_{buckets}_v{self.VERSION}.json"

    @classmethod
    def _rate_for(cls, duration: float) -> int:
        return max(cls.MIN_RATE, min(cls.MAX_RATE, int(cls.TARGET_SAMPLES / max(duration, 0.1))))

    @staticmethod
    def _bucketize(samples, buckets: int) -> list[float]:
        """Max-abs peak per bucket, normalised to 0..1 of full scale (real values)."""
        try:
            import numpy as np
            a = np.frombuffer(samples, dtype=np.int16)
            if a.size == 0:
                return []
            buckets = max(1, min(buckets, a.size))
            per = math.ceil(a.size / buckets)
            pad = per * buckets - a.size
            if pad:
                a = np.concatenate([a, np.zeros(pad, dtype=np.int16)])
            peaks = np.abs(a.astype(np.int32)).reshape(buckets, per).max(axis=1) / 32768.0
            return [round(float(v), 4) for v in peaks]
        except ImportError:
            import array
            a = array.array('h'); a.frombytes(samples)
            if not len(a):
                return []
            buckets = max(1, min(buckets, len(a)))
            per = math.ceil(len(a) / buckets)
            peaks = []
            for start in range(0, len(a), per):
                chunk = a[start:start + per]
                peaks.append(round(max(abs(x) for x in chunk) / 32768.0, 4) if chunk else 0.0)
            return peaks[:buckets]

    async def peaks(self, path, buckets: int = 1600) -> dict:
        path = Path(path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f'Audioquelle fehlt: {path}')
        stat = path.stat()
        cache_file = self._cache_path(path, stat, buckets)
        if cache_file.is_file():
            try:
                cached = json.loads(cache_file.read_text(encoding='utf-8'))
                if cached.get('version') == self.VERSION:
                    return cached
            except (ValueError, OSError):
                pass  # beschädigter Cache -> neu analysieren

        info = await self.ffmpeg.probe(path)
        duration = float(info.duration_seconds or 0)
        if not info.audio_streams:
            result = {'has_audio': False, 'duration': duration, 'peaks': [],
                      'buckets': 0, 'rate': 0, 'version': self.VERSION}
        else:
            rate = self._rate_for(duration)
            proc = await create_hidden_subprocess(
                self.ffmpeg.ffmpeg_path, '-hide_banner', '-v', 'error', '-nostdin',
                '-i', str(path), '-ac', '1', '-ar', str(rate), '-f', 's16le', '-',
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            raw, err = await proc.communicate()
            if proc.returncode:
                raise RuntimeError(err.decode('utf-8', errors='replace')[-2000:])
            peaks = await asyncio.to_thread(self._bucketize, raw, buckets)
            result = {'has_audio': bool(peaks), 'duration': duration, 'peaks': peaks,
                      'buckets': len(peaks), 'rate': rate, 'version': self.VERSION}

        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=self.cache_dir, delete=False) as handle:
                temp = Path(handle.name)
                json.dump(result, handle, ensure_ascii=False)
            temp.replace(cache_file)
        except OSError:
            pass  # Cache ist Optimierung, kein Fehler wenn nicht schreibbar
        return result

    @staticmethod
    def slice_window(peaks: list[float], duration: float, start: float, end: float) -> list[float]:
        """Clip-Fenster [start,end] aus den Quell-Peaks (für Trim/Split/Move)."""
        n = len(peaks)
        if not n or duration <= 0 or end <= start:
            return []
        lo = max(0, int(start / duration * n))
        hi = min(n, math.ceil(end / duration * n))
        return peaks[lo:hi] if hi > lo else []
