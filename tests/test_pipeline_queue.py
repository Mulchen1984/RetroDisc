"""Persistent JobQueue: ordering, recovery, retry, persistence, concurrency."""
import sqlite3
import pytest
from src.core.errors import QueueError
from src.services.pipeline.queue import JobQueue, PipelineJob, JobState


class Clock:
    def __init__(self, t=1000.0):
        self.t = t
    def __call__(self):
        self.t += 1
        return self.t


def q(tmp_path, name="q.db"):
    return JobQueue(tmp_path / name, now=Clock())


def test_enqueue_get_roundtrip(tmp_path):
    jq = q(tmp_path)
    jq.enqueue(PipelineJob(id="a", type="transcode", source="s", destination="d", metadata={"k": 1}))
    job = jq.get("a")
    assert job.source == "s" and job.status == JobState.QUEUED.value and job.metadata == {"k": 1}
    assert job.created is not None
    jq.close()


def test_pending_fifo_and_priority(tmp_path):
    jq = q(tmp_path)
    jq.enqueue(PipelineJob(id="a", priority=0))
    jq.enqueue(PipelineJob(id="b", priority=5))     # höhere Priorität zuerst
    jq.enqueue(PipelineJob(id="c", priority=0))
    order = [j.id for j in jq.pending()]
    assert order == ["b", "a", "c"]                 # Priorität, dann FIFO
    jq.close()


def test_status_transitions_and_progress(tmp_path):
    jq = q(tmp_path)
    jq.enqueue(PipelineJob(id="a"))
    jq.mark_started("a"); assert jq.get("a").status == JobState.PREPARING.value
    jq.mark_running("a"); jq.set_progress("a", 42.0)
    assert jq.get("a").status == JobState.RUNNING.value and jq.get("a").progress == 42.0
    jq.mark_completed("a")
    j = jq.get("a")
    assert j.status == JobState.COMPLETED.value and j.progress == 100.0 and j.finished is not None
    jq.close()


def test_restart_recovers_running_to_interrupted(tmp_path):
    jq = q(tmp_path)
    jq.enqueue(PipelineJob(id="a")); jq.mark_running("a")
    jq.enqueue(PipelineJob(id="b"))                 # bleibt QUEUED
    jq.close()
    jq2 = JobQueue(tmp_path / "q.db", now=Clock())  # "Neustart"
    interrupted = jq2.recover()
    assert interrupted == ["a"]
    assert jq2.get("a").status == JobState.INTERRUPTED.value
    assert jq2.get("b").status == JobState.QUEUED.value
    jq2.close()


def test_retry_respects_max_retries(tmp_path):
    jq = q(tmp_path)
    jq.enqueue(PipelineJob(id="a", max_retries=1)); jq.mark_failed("a", "boom")
    assert jq.retry("a") is True and jq.get("a").status == JobState.QUEUED.value
    assert jq.get("a").retry_count == 1 and jq.get("a").error == ""
    jq.mark_failed("a", "again")
    assert jq.retry("a") is False                   # max erreicht
    jq.close()


def test_cancel_pause_resume(tmp_path):
    jq = q(tmp_path)
    jq.enqueue(PipelineJob(id="a"))
    assert jq.pause("a") and jq.get("a").status == JobState.PAUSED.value
    assert jq.resume("a") and jq.get("a").status == JobState.QUEUED.value
    jq.mark_cancelled("a")
    assert jq.get("a").status == JobState.CANCELLED.value
    assert jq.pause("a") is False                   # aus CANCELLED nicht pausierbar
    jq.close()


def test_remove_and_clear_completed(tmp_path):
    jq = q(tmp_path)
    jq.enqueue(PipelineJob(id="a")); jq.mark_completed("a")
    jq.enqueue(PipelineJob(id="b"))
    assert jq.clear_completed() == 1 and jq.get("a") is None
    assert jq.remove("b") is True and jq.count() == 0
    jq.close()


def test_dependency_ready(tmp_path):
    jq = q(tmp_path)
    jq.enqueue(PipelineJob(id="dep"))
    jq.enqueue(PipelineJob(id="child", depends_on="dep"))
    assert jq.dependency_ready(jq.get("dep")) is None      # keine Abhängigkeit
    assert jq.dependency_ready(jq.get("child")) is False   # dep noch nicht fertig
    jq.mark_completed("dep")
    assert jq.dependency_ready(jq.get("child")) is True
    jq.close()


def test_persistence_across_reopen(tmp_path):
    jq = q(tmp_path); jq.enqueue(PipelineJob(id="a", source="keep")); jq.close()
    jq2 = JobQueue(tmp_path / "q.db")
    assert jq2.get("a").source == "keep"
    jq2.close()


def test_corrupt_db_raises_queue_error(tmp_path):
    bad = tmp_path / "q.db"; bad.write_bytes(b"not a sqlite db" * 20)
    with pytest.raises(QueueError):
        JobQueue(bad)


def test_two_connections_share_db(tmp_path):
    a = JobQueue(tmp_path / "q.db"); b = JobQueue(tmp_path / "q.db")
    a.enqueue(PipelineJob(id="x", source="from-a"))
    assert b.get("x").source == "from-a"            # zweite Verbindung sieht es (busy_timeout)
    b.mark_running("x")
    assert a.get("x").status == JobState.RUNNING.value
    a.close(); b.close()


def test_claim_and_retry_are_atomic_across_connections(tmp_path):
    with JobQueue(tmp_path / 'q.db') as a, JobQueue(tmp_path / 'q.db') as b:
        a.enqueue(PipelineJob(id='a'))
        assert a.mark_started('a')
        assert not b.mark_started('a')
        a.mark_failed('a', 'fail')
        assert b.retry('a') and not a.retry('a')
        assert a.get('a').retry_count == 1
        a.update_metadata('a', {'a': 1})
        b.update_metadata('a', {'b': 2})
        assert a.get('a').metadata == {'a': 1, 'b': 2}


def test_sqlite_rollback_lock_and_cleanup(tmp_path):
    with JobQueue(tmp_path / 'q.db') as a, JobQueue(tmp_path / 'q.db') as b:
        a.enqueue(PipelineJob(id='a', source='original'))
        with pytest.raises(sqlite3.IntegrityError):
            a.enqueue(PipelineJob(id='a', source='duplicate'))
        assert a.get('a').source == 'original'
        assert not a._conn.in_transaction
        b._conn.execute('PRAGMA busy_timeout=20')
        a._conn.execute('BEGIN IMMEDIATE')
        try:
            with pytest.raises(sqlite3.OperationalError, match='locked'):
                b.update_metadata('a', {'lost': True})
            assert not b._conn.in_transaction
        finally:
            a._conn.rollback()
        b.update_metadata('a', {'saved': True})
        assert a.get('a').metadata == {'saved': True}
    with pytest.raises(sqlite3.ProgrammingError): a.count()


@pytest.mark.parametrize('state', [JobState.PREPARING, JobState.RUNNING, JobState.VERIFYING])
def test_recovery_never_promotes_partial_output(tmp_path, state):
    partial = tmp_path / 'partial.mp4'; partial.write_bytes(b'partial')
    with JobQueue(tmp_path / 'q.db') as q:
        q.enqueue(PipelineJob(id='a', destination=str(partial)))
        q.set_status('a', state)
    with JobQueue(tmp_path / 'q.db') as q:
        assert q.recover() == ['a']
        assert q.get('a').status == 'interrupted'
        assert q.get('a').finished is None
        assert partial.read_bytes() == b'partial'  # recovery never overwrites user files
        assert q.retry('a') and q.get('a').status == 'queued'
