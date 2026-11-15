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
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import context
from app.models import Environment, GeneratedArtifact, Job, MaterialUpdate
from app.services import environments as environment_service
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

    jobs.beat(session, "alive", [kept.id], now=NOW + timedelta(minutes=2))
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


def test_the_same_work_is_never_queued_twice(session: Session, session_factory, ran):
    env = environment(session)
    dispatcher = Recording()
    first = queue(
        session, session_factory, env, "Once", [note("a")], dispatcher=dispatcher
    )
    again = queue(
        session, session_factory, env, "Once again", [note("a")], dispatcher=dispatcher
    )
    other = queue(
        session, session_factory, env, "Other", [note("b")], dispatcher=dispatcher
    )

    assert again.id == first.id
    assert other.id != first.id
    assert dispatcher.dispatched == [first.id, other.id]

    claim_and_run(session, session_factory)  # the first one finishes
    later = queue(session, session_factory, env, "Once more", [note("a")])

    assert later.id != first.id
    assert session.get(Job, first.id).status == "succeeded"


def test_two_requests_at_the_same_moment_get_the_same_job(
    session: Session, session_factory, ran, monkeypatch
):
    env = environment(session)
    first = queue(session, session_factory, env, "Once", [note("a")])
    # The second request looks before the first has committed, and misses it.
    real, calls = jobs._active, []

    def racing(*args):
        calls.append(args)
        return None if len(calls) == 1 else real(*args)

    monkeypatch.setattr(jobs, "_active", racing)

    again = queue(session, session_factory, env, "Once again", [note("a")])

    assert again.id == first.id
    assert len(calls) == 2  # missed, then found after the refused insert
    assert session.scalar(select(func.count()).select_from(Job)) == 1
    assert session.get(Job, first.id).status == "queued"  # the session still works


def test_a_jobs_key_ignores_which_steps_are_done(ran):
    steps = [note("a"), note("b")]
    done = [{**steps[0], "done": True}, steps[1]]

    assert jobs.job_key("test", steps) == jobs.job_key("test", done)
    assert jobs.job_key("test", steps) != jobs.job_key("other", steps)
    assert jobs.job_key("test", steps) != jobs.job_key("test", steps[:1])


# --- artifacts a stopped job leaves unfinished (record 21) ---------------------


def artifact(session, env, status="pending", kind="environment_summary"):
    row = GeneratedArtifact(
        environment_id=env.id,
        artifact_type=kind,
        source_version=uuid.uuid4().hex,
        status=status,
        model_name="mock",
        prompt_version="v1",
    )
    session.add(row)
    session.commit()
    return row


@pytest.fixture
def writing(monkeypatch):
    """Test steps for artifacts: crash_writing claims its artifact
    (generating) and then crashes, as a worker dying mid-write would; write
    finishes its artifact."""

    def crash_writing(tools, args):
        with tools.session_factory() as session:
            row = session.get(GeneratedArtifact, jobs._id(args["artifact_id"]))
            row.status = "generating"
            session.commit()
        raise RuntimeError("the worker died mid-write")

    def write(tools, args):
        with tools.session_factory() as session:
            row = session.get(GeneratedArtifact, jobs._id(args["artifact_id"]))
            if row.status == "pending":
                row.status = "ready"
                session.commit()

    monkeypatch.setitem(jobs.STEPS, "crash_writing", crash_writing)
    monkeypatch.setitem(jobs.STEPS, "write", write)


def status_of(session, row):
    session.expire_all()
    found = session.get(GeneratedArtifact, row.id)
    return found.status, found.error


def test_a_crash_mid_write_puts_the_artifact_back_for_the_retry(
    session: Session, session_factory, ran, writing, monkeypatch
):
    env = environment(session)
    summary = artifact(session, env)
    job = queue(
        session,
        session_factory,
        env,
        "Writing",
        [jobs.step("crash_writing", "Writing", artifact_id=summary.id)],
    )

    claim_and_run(session, session_factory, now=NOW)

    assert session.get(Job, job.id).status == "queued"  # to be tried again
    assert status_of(session, summary) == ("pending", None)  # its step rewrites it

    # The retry's step works this time.
    monkeypatch.setitem(jobs.STEPS, "crash_writing", jobs.STEPS["write"])
    claim_and_run(
        session, session_factory, now=datetime.now(UTC) + timedelta(minutes=1)
    )

    assert session.get(Job, job.id).status == "succeeded"
    assert status_of(session, summary) == ("ready", None)


def test_the_last_failed_attempt_fails_what_the_job_would_have_written(
    session: Session, session_factory, ran, writing
):
    env = environment(session)
    started, never_reached = artifact(session, env), artifact(session, env)
    job = queue(
        session,
        session_factory,
        env,
        "Writing",
        [
            jobs.step("crash_writing", "First", artifact_id=started.id),
            jobs.step("write", "Second", artifact_id=never_reached.id),
        ],
    )
    job.attempts = job.max_attempts - 1  # the next run is the last
    session.commit()

    claim_and_run(session, session_factory, now=NOW)

    reason = "An unexpected error stopped this job."
    assert session.get(Job, job.id).status == "failed"
    assert status_of(session, started) == ("failed", reason)
    assert status_of(session, never_reached) == ("failed", reason)


def test_an_unnamed_artifact_left_generating_fails_so_a_retried_step_rearms_it(
    session: Session, session_factory, ran, writing
):
    env = environment(session)
    # Written inside a chain step, whose arguments do not name it.
    chain_summary = artifact(session, env, status="generating")
    job = queue(session, session_factory, env, "Chain", [jobs.step("fail", "Step")])

    claim_and_run(session, session_factory, now=NOW)

    assert session.get(Job, job.id).status == "queued"
    assert status_of(session, chain_summary) == (
        "failed",
        "An unexpected error stopped this job. Trying again.",
    )


def test_cancelling_a_queued_job_fails_only_what_no_other_job_will_write(
    session: Session, session_factory, ran, writing
):
    env = environment(session)
    alone, shared = artifact(session, env), artifact(session, env)
    busy = artifact(session, env, status="generating")  # another job's, running
    cancelled = queue(
        session,
        session_factory,
        env,
        "Cancelled",
        [
            jobs.step("write", "Alone", artifact_id=alone.id),
            jobs.step("write", "Shared", artifact_id=shared.id),
        ],
    )
    queue(
        session,
        session_factory,
        env,
        "Still queued",
        [jobs.step("write", "Shared too", artifact_id=shared.id)],
    )

    jobs.cancel(session, cancelled)

    assert status_of(session, alone) == ("failed", "Cancelled before it was written.")
    assert status_of(session, shared) == ("pending", None)
    assert status_of(session, busy) == ("generating", None)


def test_a_stopped_workers_job_releases_what_it_was_writing(
    session: Session, session_factory, ran, writing
):
    env = environment(session)
    summary = artifact(session, env)
    job = queue(
        session,
        session_factory,
        env,
        "Lost",
        [jobs.step("write", "Writing", artifact_id=summary.id)],
    )
    jobs.claim(session, "model", "gone", now=NOW)
    summary.status = "generating"  # it was mid-write when its worker died
    session.commit()

    jobs.recover(session, now=NOW + timedelta(minutes=3))

    assert session.get(Job, job.id).status == "queued"
    assert status_of(session, summary) == ("pending", None)


def test_reading_jobs_leave_artifacts_alone(session: Session, session_factory, ran):
    env = environment(session)
    other = artifact(session, env, status="generating")
    queue(
        session,
        session_factory,
        env,
        "Reading",
        [jobs.step("fail", "Read")],
        lane="read",
    )

    claim_and_run(session, session_factory, lane="read", now=NOW)

    assert status_of(session, other) == ("generating", None)


def test_a_job_deleted_with_its_environment_stops_where_it_is(
    session: Session, session_factory, ran, monkeypatch
):
    # Deleting an environment deletes its jobs, the running one too, as when
    # a learner deletes it during a long model call.
    env = environment(session)

    def delete_environment(tools, args):
        with tools.session_factory() as other:
            environment_service.delete_environment(
                other, other.get(Environment, env.id)
            )

    monkeypatch.setitem(jobs.STEPS, "delete", delete_environment)
    queue(
        session,
        session_factory,
        env,
        "Deleted midway",
        [note("a"), jobs.step("delete", "Delete the environment"), note("b")],
    )

    claim_and_run(session, session_factory)  # ends without raising

    assert ran == ["a"]  # nothing after the deletion runs
    assert session.scalar(select(func.count()).select_from(Job)) == 0
    # Later lines in the worker's thread are not marked with the deleted job.
    assert context.job_id.get() is None
