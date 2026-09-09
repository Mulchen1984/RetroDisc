"""Local disc/media catalog keyed by disc fingerprint.

A proper, migration-capable store (SQLite with PRAGMA user_version), not a flat
JSON list. Discs and media are catalogued by their fingerprint (natural dedupe),
optionally enriched with MetadataService data, and prepared for a later
player/library UI. Reuses the project's existing sqlite approach; kept in its own
catalog DB so it never touches the scanned-media library.
"""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import closing
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

import structlog

log = structlog.get_logger()

SCHEMA_VERSION = 1

_COLUMNS = ("fingerprint", "title", "year", "source_type", "original_disc_type",
            "iso_path", "rip_path", "cover", "content_hash", "created",
            "last_verified", "notes", "metadata_json")


@dataclass
class LibraryItem:
    fingerprint: str
    title: str = ""
    year: Optional[int] = None
    source_type: str = ""              # disc | iso | video_ts | bdmv | file
    original_disc_type: str = ""       # DVD | BD | UHD | ...
    iso_path: str = ""
    rip_path: str = ""
    cover: str = ""
    content_hash: str = ""             # zusätzlicher Dubletten-Schlüssel (gleicher Inhalt)
    created: Optional[float] = None
    last_verified: Optional[float] = None
    notes: str = ""
    metadata: dict = field(default_factory=dict)

    def to_row(self) -> dict:
        data = asdict(self)
        data["metadata_json"] = json.dumps(data.pop("metadata") or {}, ensure_ascii=False)
        return data

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "LibraryItem":
        data = {k: row[k] for k in _COLUMNS if k != "metadata_json"}
        try:
            data["metadata"] = json.loads(row["metadata_json"] or "{}")
        except (ValueError, TypeError):
            data["metadata"] = {}
        return cls(**data)


class LibraryService:
    def __init__(self, db_path, *, now=time.time):
        self.db_path = Path(db_path)
        self._now = now
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._migrate()

    # ── schema / migration ──────────────────────────────────────────────
    def _migrate(self) -> None:
        version = self._conn.execute("PRAGMA user_version").fetchone()[0]
        if version < 1:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS library_items (
                    fingerprint TEXT PRIMARY KEY,
                    title TEXT DEFAULT '', year INTEGER,
                    source_type TEXT DEFAULT '', original_disc_type TEXT DEFAULT '',
                    iso_path TEXT DEFAULT '', rip_path TEXT DEFAULT '',
                    cover TEXT DEFAULT '', content_hash TEXT DEFAULT '',
                    created REAL, last_verified REAL,
                    notes TEXT DEFAULT '', metadata_json TEXT DEFAULT '{}'
                )""")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_content_hash ON library_items(content_hash)")
            self._conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            self._conn.commit()
        # Zukünftige Migrationen: hier `if version < 2: ...` anhängen.

    # ── writes (upsert = dedupe by fingerprint) ─────────────────────────
    def add_or_update(self, item: LibraryItem) -> LibraryItem:
        if not item.fingerprint:
            raise ValueError("LibraryItem benötigt einen Fingerprint.")
        existing = self.get(item.fingerprint)
        if existing is None and item.created is None:
            item.created = self._now()
        elif existing is not None:
            item.created = existing.created            # ursprüngliches Anlegedatum bewahren
            # Manuelle Notizen nie ungefragt verwerfen.
            if not item.notes:
                item.notes = existing.notes
        row = item.to_row()
        placeholders = ",".join(f":{c}" for c in _COLUMNS)
        updates = ",".join(f"{c}=excluded.{c}" for c in _COLUMNS if c != "fingerprint")
        with self._conn:
            self._conn.execute(
                f"INSERT INTO library_items ({','.join(_COLUMNS)}) VALUES ({placeholders}) "
                f"ON CONFLICT(fingerprint) DO UPDATE SET {updates}", row)
        return item

    def attach_metadata(self, fingerprint: str, metadata) -> Optional[LibraryItem]:
        item = self.get(fingerprint)
        if item is None:
            return None
        item.metadata = metadata.to_dict() if hasattr(metadata, "to_dict") else dict(metadata)
        if not item.title and item.metadata.get("title"):
            item.title = item.metadata["title"]
        if item.year is None and item.metadata.get("year"):
            item.year = item.metadata["year"]
        return self.add_or_update(item)

    def mark_verified(self, fingerprint: str, when: Optional[float] = None) -> bool:
        with self._conn:
            cur = self._conn.execute("UPDATE library_items SET last_verified=? WHERE fingerprint=?",
                                     (when if when is not None else self._now(), fingerprint))
        return cur.rowcount > 0

    def remove(self, fingerprint: str) -> bool:
        with self._conn:
            cur = self._conn.execute("DELETE FROM library_items WHERE fingerprint=?", (fingerprint,))
        return cur.rowcount > 0

    # ── reads ───────────────────────────────────────────────────────────
    def get(self, fingerprint: str) -> Optional[LibraryItem]:
        row = self._conn.execute("SELECT * FROM library_items WHERE fingerprint=?",
                                 (fingerprint,)).fetchone()
        return LibraryItem.from_row(row) if row else None

    def all(self) -> list[LibraryItem]:
        rows = self._conn.execute("SELECT * FROM library_items ORDER BY title, created").fetchall()
        return [LibraryItem.from_row(r) for r in rows]

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM library_items").fetchone()[0]

    def find_duplicates(self) -> list[list[LibraryItem]]:
        """Groups of items that share a non-empty content_hash (same content)."""
        groups: dict[str, list[LibraryItem]] = {}
        for item in self.all():
            if item.content_hash:
                groups.setdefault(item.content_hash, []).append(item)
        return [g for g in groups.values() if len(g) > 1]

    def schema_version(self) -> int:
        return self._conn.execute("PRAGMA user_version").fetchone()[0]

    def close(self) -> None:
        self._conn.close()
