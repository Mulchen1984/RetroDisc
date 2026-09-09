"""MetadataService + local cache: offline-first, manual overrides, providers."""
import json
import pytest
from src.services.metadata import (
    Metadata, MetadataQuery, MetadataCache, MetadataService, score_candidate,
    SCHEMA_VERSION,
)

FP = "a" * 64
FP2 = "b" * 40


class Clock:
    def __init__(self, t=1000.0):
        self.t = t
    def __call__(self):
        return self.t


class FakeProvider:
    name = "fake"
    priority = 10
    def __init__(self, results):
        self.results = results
        self.calls = []
    async def search(self, query):
        self.calls.append(query)
        return [Metadata.from_dict(r) for r in self.results]


class BoomProvider:
    name = "boom"
    priority = 5
    def __init__(self):
        self.calls = []
    async def search(self, query):
        self.calls.append(query)
        raise RuntimeError("kein Internet")


def test_cache_write_read_roundtrip(tmp_path):
    cache = MetadataCache(tmp_path, now=Clock())
    cache.set_auto(FP, Metadata(title="Alien", year=1979, runtime=6960))
    got = cache.get(FP)
    assert got.title == "Alien" and got.year == 1979 and got.runtime == 6960


def test_unknown_fingerprint(tmp_path):
    cache = MetadataCache(tmp_path)
    assert cache.get(FP) is None and cache.is_stale(FP) is True


def test_invalid_fingerprint_is_safe(tmp_path):
    cache = MetadataCache(tmp_path)
    assert cache.get("../etc/passwd") is None
    assert cache.get("") is None


def test_corrupt_cache_does_not_crash(tmp_path):
    cache = MetadataCache(tmp_path)
    (tmp_path / f"{FP}.json").write_text("{not valid json", encoding="utf-8")
    assert cache.get(FP) is None                       # ignoriert, kein Absturz


def test_schema_version_written_and_migrated(tmp_path):
    cache = MetadataCache(tmp_path)
    cache.set_auto(FP, Metadata(title="X"))
    raw = json.loads((tmp_path / f"{FP}.json").read_text(encoding="utf-8"))
    assert raw["schema_version"] == SCHEMA_VERSION
    # altes Schema ohne 'auto' -> Migration hebt an
    (tmp_path / f"{FP2}.json").write_text(json.dumps(
        {"schema_version": 0, "metadata": {"title": "Old"}}), encoding="utf-8")
    rec = cache.get_record(FP2)
    assert rec["schema_version"] == SCHEMA_VERSION and rec["auto"]["title"] == "Old"


def test_manual_override_wins_and_survives_auto_refresh(tmp_path):
    cache = MetadataCache(tmp_path, now=Clock())
    cache.set_auto(FP, Metadata(title="Auto Title", year=1999))
    cache.set_manual(FP, {"title": "Mein Titel"})
    assert cache.get(FP).title == "Mein Titel" and cache.get(FP).year == 1999
    cache.set_auto(FP, Metadata(title="Neuer Auto Titel", year=2001))   # Refresh
    assert cache.get(FP).title == "Mein Titel"          # manuell bleibt
    assert cache.get(FP).year == 2001                   # nicht-manuelles Feld aktualisiert


def test_ttl_staleness(tmp_path):
    clock = Clock(1000.0)
    cache = MetadataCache(tmp_path, now=clock, ttl_seconds=100)
    cache.set_auto(FP, Metadata(title="X"))
    assert not cache.is_stale(FP)
    clock.t = 1000.0 + 101
    assert cache.is_stale(FP)


def test_atomic_write_leaves_no_temp_files(tmp_path):
    cache = MetadataCache(tmp_path, now=Clock())
    cache.set_auto(FP, Metadata(title="X"))
    entries = list(tmp_path.iterdir())
    assert entries == [tmp_path / f"{FP}.json"]         # keine .tmp-Reste


def test_score_candidate_ranks_by_title_year_runtime():
    q = MetadataQuery(title="Blade Runner", year=1982, runtime=6960)
    good = score_candidate(q, Metadata(title="Blade Runner", year=1982, runtime=6980))
    bad = score_candidate(q, Metadata(title="Total Recall", year=1990, runtime=6000))
    assert good > bad and good >= 90


@pytest.mark.asyncio
async def test_lookup_cache_hit_skips_provider(tmp_path):
    cache = MetadataCache(tmp_path, now=Clock())
    provider = FakeProvider([{"title": "From Net"}])
    service = MetadataService(cache, [provider])
    cache.set_auto(FP, Metadata(title="Cached"))
    result = await service.lookup(MetadataQuery(fingerprint=FP, title="Cached"))
    assert result.title == "Cached" and provider.calls == []   # kein Provider-Aufruf


@pytest.mark.asyncio
async def test_lookup_queries_provider_and_caches(tmp_path):
    cache = MetadataCache(tmp_path, now=Clock())
    provider = FakeProvider([{"title": "Matrix", "year": 1999, "runtime": 8160}])
    service = MetadataService(cache, [provider])
    q = MetadataQuery(fingerprint=FP, title="Matrix", year=1999, runtime=8160)
    result = await service.lookup(q)
    assert result.title == "Matrix" and result.confidence >= 80
    assert provider.calls and cache.get(FP).title == "Matrix"   # jetzt gecacht


@pytest.mark.asyncio
async def test_provider_error_does_not_block_and_falls_back(tmp_path):
    cache = MetadataCache(tmp_path, now=Clock(), ttl_seconds=0)   # sofort stale
    cache.set_auto(FP, Metadata(title="Local"))
    service = MetadataService(cache, [BoomProvider()])
    result = await service.lookup(MetadataQuery(fingerprint=FP, title="Local"), force_refresh=True)
    assert result.title == "Local"                     # Providerfehler -> Fallback auf Cache


@pytest.mark.asyncio
async def test_offline_never_calls_providers(tmp_path):
    cache = MetadataCache(tmp_path, now=Clock())
    provider = FakeProvider([{"title": "Net"}])
    service = MetadataService(cache, [provider])
    cache.set_auto(FP, Metadata(title="Local"))
    result = await service.lookup(MetadataQuery(fingerprint=FP), allow_network=False, force_refresh=True)
    assert result.title == "Local" and provider.calls == []


@pytest.mark.asyncio
async def test_multiple_candidates_sorted_by_confidence(tmp_path):
    cache = MetadataCache(tmp_path, now=Clock())
    provider = FakeProvider([
        {"title": "Wrong Film", "year": 1950},
        {"title": "Alien", "year": 1979, "runtime": 6960},
    ])
    service = MetadataService(cache, [provider])
    q = MetadataQuery(title="Alien", year=1979, runtime=6960)
    cands = await service.candidates(q)
    assert len(cands) == 2 and cands[0].title == "Alien"
    assert cands[0].confidence > cands[1].confidence


@pytest.mark.asyncio
async def test_provider_priority_order(tmp_path):
    cache = MetadataCache(tmp_path, now=Clock())
    low = FakeProvider([{"title": "Low"}]); low.name = "low"; low.priority = 1
    high = FakeProvider([{"title": "High"}]); high.name = "high"; high.priority = 9
    service = MetadataService(cache, [low, high])
    assert [p.name for p in service.providers] == ["high", "low"]   # nach Priorität


@pytest.mark.asyncio
async def test_failing_provider_does_not_stop_the_next_one(tmp_path):
    cache = MetadataCache(tmp_path, now=Clock())
    boom = BoomProvider(); boom.priority = 9                        # scheitert, höhere Priorität
    good = FakeProvider([{"title": "Rettung"}]); good.name = "good"; good.priority = 1
    service = MetadataService(cache, [boom, good])
    cands = await service.candidates(MetadataQuery(title="Rettung"))
    assert boom.calls and [c.title for c in cands] == ["Rettung"]   # zweiter Provider trotzdem probiert


@pytest.mark.asyncio
async def test_hanging_provider_times_out_and_next_runs(tmp_path):
    import asyncio

    class Hang:
        name = "hang"; priority = 9
        async def search(self, query):
            await asyncio.sleep(5)
            return []
    good = FakeProvider([{"title": "Da"}]); good.name = "good"; good.priority = 1
    service = MetadataService(cache=MetadataCache(tmp_path, now=Clock()),
                              providers=[Hang(), good], provider_timeout=0.05)
    cands = await service.candidates(MetadataQuery(title="Da"))
    assert [c.title for c in cands] == ["Da"]                       # Hänger per Timeout übersprungen


def test_disc_label_used_when_no_title():
    from src.services.metadata import MetadataQuery, Metadata
    q = MetadataQuery(disc_label="THE_MATRIX")
    with_match = score_candidate(q, Metadata(title="THE_MATRIX"))
    no_match = score_candidate(q, Metadata(title="Toy Story"))
    assert with_match > no_match and with_match >= 55              # Disc-Label fließt ins Matching ein


@pytest.mark.asyncio
async def test_tie_break_prefers_exact_year(tmp_path):
    # Zwei Kandidaten mit gleichem Titel (gleiche Titel-Ähnlichkeit) – Jahr entscheidet.
    provider = FakeProvider([
        {"title": "Dune", "year": 1984},
        {"title": "Dune", "year": 2021},
    ])
    service = MetadataService(MetadataCache(tmp_path, now=Clock()), [provider])
    cands = await service.candidates(MetadataQuery(title="Dune", year=2021))
    assert cands[0].year == 2021                                   # deterministischer Tie-Break


@pytest.mark.asyncio
async def test_stale_cache_triggers_refresh_without_force(tmp_path):
    clock = Clock(1000.0)
    cache = MetadataCache(tmp_path, now=clock, ttl_seconds=100)
    provider = FakeProvider([{"title": "Frisch"}])
    service = MetadataService(cache, [provider])
    cache.set_auto(FP, Metadata(title="Alt"))
    clock.t = 1000.0 + 500                                         # jetzt stale
    result = await service.lookup(MetadataQuery(fingerprint=FP, title="Frisch"))
    assert provider.calls and result.title == "Frisch"            # ohne force refreshed


@pytest.mark.asyncio
async def test_manual_override_survives_service_lookup_refresh(tmp_path):
    cache = MetadataCache(tmp_path, now=Clock())
    provider = FakeProvider([{"title": "Vom Netz", "year": 2000}])
    service = MetadataService(cache, [provider])
    cache.set_auto(FP, Metadata(title="Alt"))
    service.set_manual(FP, {"title": "Mein Titel"})
    result = await service.lookup(MetadataQuery(fingerprint=FP, title="egal"), force_refresh=True)
    assert result.title == "Mein Titel" and result.year == 2000   # manuell bleibt, Rest aktualisiert


def test_migration_does_not_downgrade_newer_schema(tmp_path):
    cache = MetadataCache(tmp_path)
    (tmp_path / f"{FP}.json").write_text(json.dumps(
        {"schema_version": 99, "auto": {"title": "Zukunft"}}), encoding="utf-8")
    assert cache.get(FP).title == "Zukunft"                        # lesbar
    raw = json.loads((tmp_path / f"{FP}.json").read_text(encoding="utf-8"))
    assert raw["schema_version"] == 99                             # NICHT herabgestuft/überschrieben


def test_atomic_write_failure_keeps_old_value_and_no_temp(tmp_path, monkeypatch):
    cache = MetadataCache(tmp_path, now=Clock())
    cache.set_auto(FP, Metadata(title="Gut"))

    def boom(*a, **k):
        raise OSError("Platte voll")
    monkeypatch.setattr("src.services.metadata.json.dump", boom)
    with pytest.raises(OSError):
        cache.set_auto(FP, Metadata(title="Schlecht"))
    assert cache.get(FP).title == "Gut"                            # Ziel unverändert
    assert [p.name for p in tmp_path.iterdir()] == [f"{FP}.json"]  # kein verwaister Temp-Rest
