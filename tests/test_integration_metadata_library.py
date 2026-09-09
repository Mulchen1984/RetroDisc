"""End-to-end: DiscFingerprint -> MetadataService -> MetadataCache -> LibraryService.

Uses the real fingerprint service, real JSON cache and real SQLite catalog (only
the network provider is a fake). Verifies the data actually flows across all
components, plus the offline path where no provider is available.
"""
import pytest
from src.services import fingerprint as fp_service
from src.services.metadata import Metadata, MetadataQuery, MetadataCache, MetadataService
from src.services.library_catalog import LibraryService, LibraryItem


class Clock:
    def __call__(self):
        return 1000.0


class FakeTMDb:
    name = "faketmdb"
    priority = 10
    def __init__(self, results):
        self.results = results
        self.calls = []
    async def search(self, query):
        self.calls.append(query)
        return [Metadata.from_dict(r) for r in self.results]


def _make_dvd(root, marker=b"ifo"):
    vts = root / "VIDEO_TS"; vts.mkdir(parents=True)
    (vts / "VIDEO_TS.IFO").write_bytes(marker)
    (vts / "VTS_01_1.VOB").write_bytes(b"0" * 4000)


@pytest.mark.asyncio
async def test_full_pipeline_disc_to_library(tmp_path):
    disc = tmp_path / "disc"; _make_dvd(disc)
    fingerprint = fp_service.fingerprint_path(disc, label="ALIEN_1979")
    assert len(fingerprint) == 64

    cache = MetadataCache(tmp_path / "meta", now=Clock())
    provider = FakeTMDb([{"title": "Alien", "year": 1979, "runtime": 6960,
                          "provider_id": "tt0078748"}])
    service = MetadataService(cache, [provider])
    library = LibraryService(tmp_path / "catalog.db", now=Clock())

    # 1) Lookup über die echte Kette
    query = MetadataQuery(fingerprint=fingerprint, title="Alien", year=1979, runtime=6960,
                          disc_label="ALIEN_1979", disc_type="DVD")
    meta = await service.lookup(query)
    assert meta.title == "Alien" and meta.confidence >= 80
    assert (tmp_path / "meta" / f"{fingerprint}.json").is_file()      # wirklich gecacht

    # 2) In Katalog aufnehmen und Metadaten verknüpfen
    library.add_or_update(LibraryItem(fingerprint=fingerprint, source_type="video_ts",
                                      original_disc_type="DVD", iso_path=""))
    library.attach_metadata(fingerprint, meta)
    item = library.get(fingerprint)
    assert item.title == "Alien" and item.year == 1979
    assert item.metadata["provider_id"] == "tt0078748"

    # 3) Zweiter Lookup = Cache-Hit, KEIN erneuter Provideraufruf
    provider.calls.clear()
    again = await service.lookup(query)
    assert again.title == "Alien" and provider.calls == []
    library.close()


@pytest.mark.asyncio
async def test_offline_pipeline_still_catalogues(tmp_path):
    disc = tmp_path / "disc"; _make_dvd(disc)
    fingerprint = fp_service.fingerprint_path(disc)
    cache = MetadataCache(tmp_path / "meta", now=Clock())
    service = MetadataService(cache, providers=[])                   # kein Provider = offline
    library = LibraryService(tmp_path / "catalog.db", now=Clock())

    meta = await service.lookup(MetadataQuery(fingerprint=fingerprint), allow_network=False)
    assert meta is None                                             # keine Metadaten, aber kein Fehler
    # Disc lässt sich trotzdem katalogisieren (Kernfunktionen unabhängig von Metadaten)
    library.add_or_update(LibraryItem(fingerprint=fingerprint, source_type="video_ts",
                                      original_disc_type="DVD"))
    assert library.get(fingerprint) is not None
    library.close()


def test_same_disc_same_fingerprint_dedupes(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    _make_dvd(a); _make_dvd(b)                                       # identische Struktur
    fp_a = fp_service.fingerprint_path(a, label="SAME")
    fp_b = fp_service.fingerprint_path(b, label="SAME")
    assert fp_a == fp_b                                             # gleiche Disc -> gleicher Fingerprint
    library = LibraryService(tmp_path / "catalog.db", now=Clock())
    library.add_or_update(LibraryItem(fingerprint=fp_a, title="Erst"))
    library.add_or_update(LibraryItem(fingerprint=fp_b, title="Nochmal"))
    assert library.count() == 1                                    # Dedupe über den Fingerprint
    library.close()
