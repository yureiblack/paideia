"""Tests for background jobs in app/services/jobs.py and app/worker.py.

Purpose: the queue's rules, against Postgres, with simple test steps and no
Redis. Jobs are claimed oldest first within their lane, once the job they
follow has ended; progress is recorded step by step; a crash is retried
later and fails after the last attempt; a stopped worker's jobs are found
and run again unless their heartbeat is kept; cancelling ends a queued job
at once, with those waiting for it and the update it carries out, and stops
a running one before its next step.
"""

import threading
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.models import Job, MaterialUpdate
from app.services import jobs
from app.worker import Worker
from tests.fakes import MockProvider
from tests.test_concepts import environment

NOW = datetime(2026, 11, 14, 9, tzinfo=UTC)


class Recording:
    """A dispatcher that only notes what it was given."""

    def __init__(self):
        self.dispatched = []

    def dispatch(self, job, background, tools):
        self.dispatched.append(job.id)

    def workers(self):
        return 0


@pytest.fixture
def ran(monkeypatch):
    """Test steps: note (records its name), fail (raises), and cancel (asks
    for its own job to be cancelled, as the API would meanwhile)."""
    done: list[str] = []

    def cancel(tools, args):
        with tools.session_factory() as session:
            job = session.get(Job, jobs._id(args["job_id"]))
            jobs.cancel(session, job)

    monkeypatch.setitem(jobs.STEPS, "note", lambda t, a: done.append(a["name"]))
    monkeypatch.setitem(jobs.STEPS, "fail", lambda t, a: 1 / 0)
    monkeypatch.setitem(jobs.STEPS, "cancel", cancel)
    return done


def queue(
    session,
    session_factory,
    env,
    title,
    steps,
    lane="model",
    after=None,
    dispatcher=None,
):
    created = jobs.start(
        session,
        environment_id=env.id,
        kind="test",
        title=title,
        lane=lane,
        steps=steps,
        tools=jobs.Tools(session_factory, MockProvider()),
        dispatcher=dispatcher or Recording(),
        background=None,
        after=after,
    )
    return created


def note(name):
    return jobs.step("note", f"Step {name}", name=name)


def claim_and_run(session, session_factory, lane="model", now=None):
    job = jobs.claim(session, lane, "test-worker", now=now)
    if job is not None:
        jobs.run(jobs.Tools(session_factory, MockProvider()), job.id)
        session.expire_all()
    return job


def test_jobs_run_oldest_first_within_their_lane(
    session: Session, session_factory, ran
):
    env = environment(session)
    dispatcher = Recording()
    first = queue(
        session,
        session_factory,
        env,
        "First",
        [note("a"), note("b")],
        dispatcher=dispatcher,
    )
    queue(session, session_factory, env, "Second", [note("c")], dispatcher=dispatcher)
    queue(session, session_factory, env, "Reading", [note("r")], lane="read")

    claimed = claim_and_run(session, session_factory)

    assert claimed.id == first.id
    assert len(dispatcher.dispatched) == 2 and dispatcher.dispatched[0] == first.id
    assert ran == ["a", "b"]
    done = session.get(Job, first.id)
    assert (done.status, done.progress, done.step, done.attempts) == (
        "succeeded",
        100,
        None,
        1,
    )
    assert done.finished_at is not None
    claim_and_run(session, session_factory)
    claim_and_run(session, session_factory, lane="read")
    assert ran == ["a", "b", "c", "r"]
    assert claim_and_run(session, session_factory) is None


def test_a_job_waits_for_the_one_it_follows(session: Session, session_factory, ran):
    env = environment(session)
    reading = queue(
        session, session_factory, env, "Reading", [note("read")], lane="read"
    )
    queue(session, session_factory, env, "Deriving", [note("derive")], after=reading)

    assert claim_and_run(session, session_factory) is None  # still waiting

    claim_and_run(session, session_factory, lane="read")
    claim_and_run(session, session_factory)

    assert ran == ["read", "derive"]


def test_a_crash_is_tried_again_later_then_fails(
    session: Session, session_factory, ran
):
    env = environment(session)
    job = queue(
        session,
        session_factory,
        env,
        "Fragile",
        [note("a"), jobs.step("fail", "Failing")],
    )

    claim_and_run(session, session_factory, now=NOW)
    first = session.get(Job, job.id)
    assert (first.status, first.attempts) == ("queued", 1)
    assert first.not_before == pytest.approx(
        datetime.now(UTC) + timedelta(seconds=30), abs=timedelta(seconds=5)
    )
    assert first.error == "An unexpected error stopped this job. Trying again."
    assert claim_and_run(session, session_factory, now=NOW) is None  # not yet

    later = datetime.now(UTC) + timedelta(seconds=31)
    claim_and_run(session, session_factory, now=later)
    second = session.get(Job, job.id)
    assert (second.status, second.attempts) == ("queued", 2)
    assert second.not_before == pytest.approx(
        datetime.now(UTC) + timedelta(minutes=2), abs=timedelta(seconds=5)
    )

    claim_and_run(
        session, session_factory, now=datetime.now(UTC) + timedelta(minutes=3)
    )
    last = session.get(Job, job.id)
    assert (last.status, last.attempts, last.error) == (
        "failed",
        3,
        "An unexpected error stopped this job.",
    )
    assert ran == ["a"]  # done once; each try starts at the step that failed


def test_a_stopped_workers_jobs_are_run_again_unless_kept_alive(
    session: Session, session_factory, ran
):
    env = environment(session)
    lost = queue(session, session_factory, env, "Lost", [note("a")])
    kept = queue(session, session_factory, env, "Kept", [note("b")], lane="read")
    jobs.claim(session, "model", "gone", now=NOW)
    jobs.claim(session, "read", "alive", now=NOW)

    jobs.beat(session, "alive", now=NOW + timedelta(minutes=2))
    found = jobs.recover(session, now=NOW + timedelta(minutes=3))

    session.expire_all()
    assert found == 1
    again = session.get(Job, lost.id)
    assert (again.status, again.worker) == ("queued", None)
    assert again.error == "Its worker stopped while running it. Trying again."
    assert session.get(Job, kept.id).status == "running"


def test_cancelling_a_queued_job_ends_it_those_waiting_and_its_update(
    session: Session, session_factory, ran
):
    env = environment(session)
    record = MaterialUpdate(
        environment_id=env.id,
        filename="scheduling.pdf",
        kind="added",
        status="running",
        steps=[
            {
                "name": "read",
                "label": "Reading the document",
                "state": "waiting",
                "detail": None,
            }
        ],
        before={},
        started_at=NOW,
    )
    session.add(record)
    session.commit()
    reading = jobs.start(
        session,
        environment_id=env.id,
        kind="read",
        title="Reading",
        lane="read",
        steps=[note("read")],
        tools=jobs.Tools(session_factory, MockProvider()),
        dispatcher=Recording(),
        background=None,
        update_id=record.id,
    )
    deriving = queue(
        session, session_factory, env, "Deriving", [note("derive")], after=reading
    )

    jobs.cancel(session, reading)

    session.expire_all()
    assert session.get(Job, reading.id).status == "cancelled"
    assert session.get(Job, deriving.id).status == "cancelled"
    assert session.get(MaterialUpdate, record.id).status == "cancelled"
    assert session.get(MaterialUpdate, record.id).steps[0]["state"] == "skipped"
    assert claim_and_run(session, session_factory) is None
    assert ran == []


def test_a_running_job_stops_before_its_next_step(
    session: Session, session_factory, ran
):
    env = environment(session)
    job = queue(session, session_factory, env, "Stopped", [note("a")])
    job.steps = [
        note("a"),
        jobs.step("cancel", "Cancelling", job_id=job.id),
        note("never"),
    ]
    session.commit()

    claim_and_run(session, session_factory)

    stopped = session.get(Job, job.id)
    assert (stopped.status, stopped.cancel_requested) == ("cancelled", True)
    assert ran == ["a"]


def test_a_finished_job_cannot_be_cancelled(session: Session, session_factory, ran):
    env = environment(session)
    job = queue(session, session_factory, env, "Done", [note("a")])
    claim_and_run(session, session_factory)

    jobs.cancel(session, session.get(Job, job.id))

    assert session.get(Job, job.id).status == "succeeded"


def test_an_unknown_step_is_refused():
    with pytest.raises(ValueError):
        jobs.step("format_disk", "Nope")


def test_the_worker_runs_one_job_of_a_lane(session: Session, session_factory, ran):
    env = environment(session)
    queue(session, session_factory, env, "Worker's", [note("w")])
    worker = Worker(
        jobs.Tools(session_factory, MockProvider()),
        "redis://localhost:6379/15",
        name="w1",
    )

    assert worker.run_one("model") is True
    assert worker.run_one("model") is False
    assert ran == ["w"]


def test_a_stopping_worker_puts_its_job_back_where_it_was(
    session: Session, session_factory, ran, monkeypatch
):
    env = environment(session)
    stopping = threading.Event()
    tools = jobs.Tools(session_factory, MockProvider(), stopping=stopping)
    # The worker is told to stop during the second step.
    monkeypatch.setitem(jobs.STEPS, "stop", lambda t, a: stopping.set())
    job = queue(session, session_factory, env, "Long", [note("a")])
    job.steps = [note("a"), jobs.step("stop", "Stopping"), note("b"), note("c")]
    session.commit()

    jobs.claim(session, "model", "w1")
    jobs.run(tools, job.id)

    session.expire_all()
    back = session.get(Job, job.id)
    assert (back.status, back.attempts, back.worker) == ("queued", 0, None)
    assert [bool(s.get("done")) for s in back.steps] == [True, True, False, False]
    assert ran == ["a"]

    stopping.clear()
    jobs.claim(session, "model", "w2")
    jobs.run(tools, job.id)

    session.expire_all()
    assert session.get(Job, job.id).status == "succeeded"
    assert ran == ["a", "b", "c"]
