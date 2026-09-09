"""Metadata layer for RetroDisc: models, fingerprint-keyed cache, providers.

Offline-first by design: a missing network or a failing provider never raises to
callers and never blocks disc/copy/burn features. The local cache is the source
of truth; providers only enrich it. Manual edits are kept apart from
auto-fetched data and win on merge, so they are never silently overwritten.
"""
from __future__ import annotations

import json
import re
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional, Protocol

import structlog

from src.services import fingerprint as fingerprint_service

log = structlog.get_logger()

SCHEMA_VERSION = 1
DEFAULT_TTL_SECONDS = 30 * 24 * 3600          # 30 Tage bis Auto-Refresh
_FP = re.compile(r"[a-f0-9]{16,64}")


@dataclass
class Metadata:
    title: str = ""
    original_title: str = ""
    year: Optional[int] = None
    runtime: Optional[int] = None             # Sekunden
    description: str = ""
    genres: list[str] = field(default_factory=list)
    director: str = ""
    cast: list[str] = field(default_factory=list)
    age_rating: str = ""
    cover_url: str = ""
    backdrop_url: str = ""
    provider: str = ""
    provider_id: str = ""
    language: str = ""
    disc_type: str = ""
    edition: str = ""
    confidence: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Metadata":
        fields = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in (data or {}).items() if k in fields})


@dataclass
class MetadataQuery:
    fingerprint: str = ""
    title: str = ""
    year: Optional[int] = None
    runtime: Optional[int] = None             # Sekunden
    disc_label: str = ""
    disc_type: str = ""


class MetadataProvider(Protocol):
    name: str
    priority: int
    async def search(self, query: MetadataQuery) -> list[Metadata]: ...


# ── matching (simple, explainable) ───────────────────────────────────────────
def score_candidate(query: MetadataQuery, meta: Metadata) -> int:
    """0..100 from title similarity, year and runtime. No opaque AI."""
    import difflib
    score = 0.0
    if query.title and meta.title:
        score += 60 * difflib.SequenceMatcher(None, query.title.lower(), meta.title.lower()).ratio()
    elif not query.title:
        score += 20                            # kein Titel zum Abgleich -> schwaches Grundvertrauen
    if query.year and meta.year and query.year == meta.year:
        score += 25
    if query.runtime and meta.runtime and abs(query.runtime - meta.runtime) <= 120:
        score += 15
    return int(round(max(0.0, min(100.0, score))))


class MetadataCache:
    """Persistent, fingerprint-keyed JSON cache with atomic writes and migration."""

    def __init__(self, cache_dir, *, now=time.time, ttl_seconds: int = DEFAULT_TTL_SECONDS):
        self.cache_dir = Path(cache_dir)
        self._now = now
        self.ttl_seconds = ttl_seconds

    def _path(self, fingerprint: str) -> Path:
        if not fingerprint or not _FP.fullmatch(fingerprint):
            raise ValueError("Ungültiger Fingerprint.")
        return self.cache_dir / f"{fingerprint}.json"

    def _migrate(self, raw: dict) -> dict:
        version = raw.get("schema_version", 0)
        # Zukünftige Migrationen hier einhängen; heute nur Schema 1.
        if version != SCHEMA_VERSION:
            raw = dict(raw)
            raw.setdefault("auto", raw.get("metadata"))     # Beispiel-Aufwärtspfad
            raw["schema_version"] = SCHEMA_VERSION
        return raw

    def get_record(self, fingerprint: str) -> Optional[dict]:
        try:
            path = self._path(fingerprint)
        except ValueError:
            return None
        if not path.is_file():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("kein Objekt")
            return self._migrate(raw)
        except (ValueError, OSError) as exc:
            # Beschädigter Cache darf die App nie zerstören.
            log.warning("metadata: beschädigte Cache-Datei ignoriert", fingerprint=fingerprint, error=str(exc))
            return None

    @staticmethod
    def _effective(record: dict) -> Metadata:
        merged = dict(record.get("auto") or {})
        merged.update({k: v for k, v in (record.get("manual") or {}).items() if v not in ("", None, [])})
        return Metadata.from_dict(merged)

    def get(self, fingerprint: str) -> Optional[Metadata]:
        record = self.get_record(fingerprint)
        return self._effective(record) if record else None

    def is_stale(self, fingerprint: str) -> bool:
        record = self.get_record(fingerprint)
        if not record:
            return True
        fetched = record.get("fetched_at") or 0
        ttl = record.get("ttl_seconds", self.ttl_seconds)
        return (self._now() - fetched) > ttl

    def _atomic_write(self, fingerprint: str, record: dict) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path = self._path(fingerprint)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.cache_dir, delete=False) as handle:
            temp = Path(handle.name)
            json.dump(record, handle, ensure_ascii=False, indent=2)
        temp.replace(path)                     # atomar

    def set_auto(self, fingerprint: str, meta: Metadata) -> None:
        """Store auto-fetched metadata; existing manual overrides are preserved."""
        record = self.get_record(fingerprint) or {}
        record["schema_version"] = SCHEMA_VERSION
        record["fingerprint"] = fingerprint
        record["auto"] = meta.to_dict()
        record.setdefault("manual", {})
        record["fetched_at"] = self._now()
        record["ttl_seconds"] = self.ttl_seconds
        self._atomic_write(fingerprint, record)

    def set_manual(self, fingerprint: str, updates: dict) -> None:
        """Merge manual field overrides; auto data and other manual fields stay."""
        record = self.get_record(fingerprint) or {"schema_version": SCHEMA_VERSION,
                                                   "fingerprint": fingerprint, "auto": {}}
        manual = dict(record.get("manual") or {})
        allowed = set(Metadata.__dataclass_fields__)
        manual.update({k: v for k, v in (updates or {}).items() if k in allowed})
        record["manual"] = manual
        record.setdefault("fetched_at", self._now())
        record.setdefault("ttl_seconds", self.ttl_seconds)
        record["schema_version"] = SCHEMA_VERSION
        self._atomic_write(fingerprint, record)


class MetadataService:
    """Fingerprint-keyed metadata lookup over a cache and prioritised providers."""

    def __init__(self, cache: MetadataCache, providers: Optional[list] = None):
        self.cache = cache
        self.providers = sorted(providers or [], key=lambda p: -getattr(p, "priority", 0))

    @staticmethod
    def fingerprint_for(structure: dict) -> str:
        return fingerprint_service.fingerprint(structure)

    async def candidates(self, query: MetadataQuery, *, allow_network: bool = True) -> list[Metadata]:
        results: list[Metadata] = []
        if allow_network:
            for provider in self.providers:
                try:
                    for meta in await provider.search(query):
                        meta.provider = meta.provider or getattr(provider, "name", "")
                        meta.confidence = score_candidate(query, meta)
                        results.append(meta)
                except Exception as exc:                      # Providerfehler blockiert nichts
                    log.warning("metadata: Provider fehlgeschlagen",
                                provider=getattr(provider, "name", ""), error=str(exc))
        results.sort(key=lambda m: m.confidence, reverse=True)
        return results

    async def lookup(self, query: MetadataQuery, *, allow_network: bool = True,
                     force_refresh: bool = False) -> Optional[Metadata]:
        fp = query.fingerprint
        if fp and not force_refresh:
            cached = self.cache.get(fp)
            if cached is not None and not self.cache.is_stale(fp):
                return cached                                 # Cache-Hit -> kein Provider-Aufruf
        if not allow_network or not self.providers:
            return self.cache.get(fp) if fp else None         # offline: nur was lokal da ist
        best = None
        for meta in await self.candidates(query, allow_network=True):
            best = meta
            break
        if best is not None and fp:
            self.cache.set_auto(fp, best)                     # manuelle Overrides bleiben erhalten
            return self.cache.get(fp)
        if best is not None:
            return best
        return self.cache.get(fp) if fp else None             # nichts gefunden -> Fallback auf Cache

    def set_manual(self, fingerprint: str, updates: dict) -> None:
        self.cache.set_manual(fingerprint, updates)
