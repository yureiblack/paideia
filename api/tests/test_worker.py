"""The worker's long-running loops (decision records 18 and 21).

Purpose: run_one and the job functions are tested on their own elsewhere;
these check what the worker's threads do around them. One keep-alive pass
sweeps leftover files, keeps its own job alive before looking for jobs a
stopped worker left, and tells Redis the worker is alive. A lane that meets
an error goes on. A worker that stops takes its announcement back, so the
page says at once that no worker is running.

Each loop runs one pass in the test's own thread: its wait asks the worker
to stop. Needs Redis, as the worker does (database 15, apart from
development's).
"""

import os
import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app import storage
from app.models import Job
from app.services import jobs
from app.worker import KEY_TTL, Worker
from tests.fakes import MockProvider
from tests.test_document_service import environment
from tests.test_jobs import note, queue

REDIS = "redis://localhost:6379/15"


@pytest.fixture
def worker(session_factory, monkeypatch):
    monkeypatch.setitem(jobs.STEPS, "note", lambda tools, args: None)
    worker = Worker(jobs.Tools(session_factory, MockProvider()), REDIS, name="w-test")
    # One pass: whatever a loop waits for next, the worker is asked to stop.
    monkeypatch.setattr(
        worker.stopping, "wait", lambda timeout=None: worker.stopping.set()
    )
    yield worker
    worker.redis.delete(f"{jobs.WORKER_KEY}{worker.name}")


def test_one_keep_alive_pass(session: Session, session_factory, worker, data_dir):
    env = environment(session)
    long_ago = datetime.now(UTC) - 2 * jobs.STALE
    # This worker's job, and one a stopped worker left: neither has had a
    # heartbeat for longer than STALE.
    mine = queue(session, session_factory, env, "Mine", [note("a")])
    jobs.claim(session, "model", worker.name)
    worker.running["model"] = mine.id
    lost = queue(session, session_factory, env, "Lost", [note("b")], lane="read")
    jobs.claim(session, "read", "stopped-worker")
    for job in (mine, lost):
        job.heartbeat_at = long_ago
    session.commit()
    orphan = storage.uploads_dir(env.id) / f"{uuid.uuid4()}.pdf"
    orphan.parent.mkdir(parents=True, exist_ok=True)
    orphan.write_bytes(b"%PDF-1.7")
    hours_ago = time.time() - 2 * 60 * 60
    os.utime(orphan, (hours_ago, hours_ago))

    worker._keep_alive()

    session.expire_all()
    assert not orphan.exists()
    # Kept alive first, so only the other worker's job goes back to the queue.
    kept = session.get(Job, mine.id)
    assert kept.status == "running"
    assert kept.heartbeat_at > datetime.now(UTC) - timedelta(minutes=1)
    assert session.get(Job, lost.id).status == "queued"
    assert 0 < worker.redis.ttl(f"{jobs.WORKER_KEY}{worker.name}") <= KEY_TTL


def test_a_lane_that_meets_an_error_goes_on(worker, monkeypatch, caplog):
    calls = []

    def run_one(lane):
        calls.append(lane)
        if len(calls) == 1:
            raise RuntimeError("the database went away")
        worker.stopping.set()
        return True

    monkeypatch.setattr(worker, "run_one", run_one)
    # After an error the lane pauses, then looks again.
    monkeypatch.setattr(worker.stopping, "wait", lambda timeout=None: None)

    worker._lane("model")

    assert calls == ["model", "model"]
    assert "The model lane hit an error; going on" in caplog.text


def test_a_stopped_worker_takes_back_its_announcement(worker):
    key = f"{jobs.WORKER_KEY}{worker.name}"
    worker.redis.set(key, "alive", ex=KEY_TTL)
    worker.stopping.set()  # as Ctrl+C does

    worker.run()

    assert worker.redis.exists(key) == 0
