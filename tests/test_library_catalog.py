"""LibraryService: fingerprint catalog, dedupe, migration, metadata linkage."""
import sqlite3
import pytest
from src.services.library_catalog import LibraryService, LibraryItem, SCHEMA_VERSION
from src.services.metadata import Metadata


class Clock:
    def __init__(self, t=1000.0):
        self.t = t
    def __call__(self):
        return self.t


def svc(tmp_path):
    return LibraryService(tmp_path / "catalog.db", now=Clock())


def test_add_get_roundtrip(tmp_path):
    s = svc(tmp_path)
    s.add_or_update(LibraryItem(fingerprint="fp1", title="Alien", year=1979, source_type="disc"))
    got = s.get("fp1")
    assert got.title == "Alien" and got.year == 1979 and got.created == 1000.0


def test_requires_fingerprint(tmp_path):
    with pytest.raises(ValueError):
        svc(tmp_path).add_or_update(LibraryItem(fingerprint=""))


def test_upsert_dedupes_and_preserves_created_and_notes(tmp_path):
    s = svc(tmp_path)
    s.add_or_update(LibraryItem(fingerprint="fp1", title="Old", notes="meine Notiz"))
    s._now = lambda: 2000.0
    s.add_or_update(LibraryItem(fingerprint="fp1", title="New"))     # ohne Notiz
    assert s.count() == 1                                            # Dedupe per Fingerprint
    item = s.get("fp1")
    assert item.title == "New" and item.created == 1000.0           # Anlegedatum bewahrt
    assert item.notes == "meine Notiz"                              # Notiz nicht verworfen


def test_all_and_remove(tmp_path):
    s = svc(tmp_path)
    s.add_or_update(LibraryItem(fingerprint="a", title="A"))
    s.add_or_update(LibraryItem(fingerprint="b", title="B"))
    assert len(s.all()) == 2
    assert s.remove("a") is True and s.count() == 1
    assert s.remove("a") is False


def test_mark_verified(tmp_path):
    s = svc(tmp_path)
    s.add_or_update(LibraryItem(fingerprint="fp1", title="X"))
    assert s.get("fp1").last_verified is None
    assert s.mark_verified("fp1", when=1234.0) is True
    assert s.get("fp1").last_verified == 1234.0
    assert s.mark_verified("missing") is False


def test_schema_version_and_migration(tmp_path):
    db = tmp_path / "catalog.db"
    s = LibraryService(db, now=Clock()); assert s.schema_version() == SCHEMA_VERSION; s.close()
    # simuliere altes DB ohne Tabelle/Version -> Reopen migriert
    conn = sqlite3.connect(str(db)); conn.execute("DROP TABLE library_items")
    conn.execute("PRAGMA user_version=0"); conn.commit(); conn.close()
    s2 = LibraryService(db, now=Clock())
    assert s2.schema_version() == SCHEMA_VERSION
    s2.add_or_update(LibraryItem(fingerprint="fp", title="Migrated"))   # wieder nutzbar
    assert s2.get("fp").title == "Migrated"


def test_find_duplicates_by_content_hash(tmp_path):
    s = svc(tmp_path)
    s.add_or_update(LibraryItem(fingerprint="a", title="Disc", content_hash="H1"))
    s.add_or_update(LibraryItem(fingerprint="b", title="ISO of disc", content_hash="H1"))
    s.add_or_update(LibraryItem(fingerprint="c", title="Other", content_hash="H2"))
    dups = s.find_duplicates()
    assert len(dups) == 1 and {i.fingerprint for i in dups[0]} == {"a", "b"}


def test_attach_metadata_fills_title_and_persists(tmp_path):
    s = svc(tmp_path)
    s.add_or_update(LibraryItem(fingerprint="fp1"))
    s.attach_metadata("fp1", Metadata(title="Blade Runner", year=1982))
    item = s.get("fp1")
    assert item.title == "Blade Runner" and item.year == 1982
    assert item.metadata["title"] == "Blade Runner"
    assert s.attach_metadata("unknown", Metadata(title="x")) is None


def test_metadata_json_corruption_is_tolerated(tmp_path):
    s = svc(tmp_path)
    s.add_or_update(LibraryItem(fingerprint="fp1", title="X"))
    s._conn.execute("UPDATE library_items SET metadata_json='{broken' WHERE fingerprint='fp1'")
    s._conn.commit()
    assert s.get("fp1").metadata == {}          # kaputtes JSON -> leeres Dict, kein Absturz
