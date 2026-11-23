"""Background jobs: work done outside any request, by the worker process.

Purpose
-------
Reading documents and everything the language model writes take seconds to
minutes. They used to run in the API process after each response, and died
with it. Now each piece of such work is a job (decision record 18): a row in
Postgres saying which steps to run, where it has got to, and how it ended.
The worker process (app/worker.py) claims jobs and runs them; Redis only
wakes it when a job is queued, and the worker also checks the table every
few seconds, so a lost signal never strands a job.

A job runs the same functions the requests used to queue, as named steps.
Steps that carry out a material update record themselves on it, as before
(app/services/updates.py). Jobs move through queued, running, then
succeeded, failed or cancelled:

- A step's own failure (the model unreachable, an unreadable PDF) is
  recorded where it always was, and the job ends failed with that message;
  trying again starts a new job.
- A job that crashes, or whose worker stops (no heartbeat for STALE), is run
  again later, up to max_attempts, from its first step not done.
- Cancelling a queued job ends it at once; a running one stops before its
  next step.
"""

import hashlib
import json
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

import redis
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import context
from app.db import SessionFactory
from app.llm import LLMError, LLMProvider
from app.models import Document, GeneratedArtifact, Job, MaterialUpdate
from app.schemas import JobRead
from app.services import concepts as concept_service
from app.services import documents as document_service
from app.services import environment_summaries as environment_summary_service
from app.services import figures as figure_service
from app.services import graph as graph_service
from app.services import maths_reading, updates
from app.services import practice as practice_service
from app.services import roadmap as roadmap_service
from app.services import summaries as summary_service

logger = logging.getLogger(__name__)

LANES = ("read", "model")
RETRY_AFTER = (timedelta(seconds=30), timedelta(minutes=2))
STALE = timedelta(minutes=2)  # no heartbeat for this long: its worker stopped
SIGNAL = "paideia:jobs:{lane}"  # Redis list a queued job's id is pushed to
WORKER_KEY = "paideia:workers:"  # prefix of each live worker's key in Redis
ACTIVE = ("queued", "running")


@dataclass
class Tools:
    """What jobs' steps work with: sessions, the models and the parser."""

    session_factory: SessionFactory
    llm: LLMProvider
    embedder: Any = None
    parser: Any = None
    reranker: Any = None
    # Set when the worker is stopping: a running job is put back in the
    # queue at its next step, without counting as an attempt.
    stopping: Any = None


def _id(value) -> uuid.UUID:
    return uuid.UUID(str(value))


# Every step a job can run, by name, with its arguments (decision record 18).
# A job's steps are stored as names and arguments, never as code.
STEPS: dict[str, Callable[[Tools, dict], object]] = {
    "process_document": lambda t, a: document_service.process_document(
        t.session_factory, _id(a["document_id"]), t.parser, t.embedder
    ),
    "queue_concepts": lambda t, a: concept_service.queue_when_ready(
        t.session_factory, _id(a["document_id"]), t.llm
    ),
    "summarize": lambda t, a: summary_service.summarize_when_ready(
        t.session_factory, _id(a["document_id"]), t.llm
    ),
    "write_summary": lambda t, a: summary_service.write_summary(
        t.session_factory, _id(a["artifact_id"]), t.llm
    ),
    "environment_summary": lambda t, a: (
        environment_summary_service.refresh_environment_summary(
            t.session_factory, _id(a["environment_id"]), t.llm
        )
    ),
    "write_environment_summary": lambda t, a: (
        environment_summary_service.write_environment_summary(
            t.session_factory, _id(a["artifact_id"]), t.llm
        )
    ),
    "extract": lambda t, a: concept_service.extract_when_ready(
        t.session_factory, _id(a["document_id"]), t.llm
    ),
    "write_extraction": lambda t, a: concept_service.write_extraction(
        t.session_factory, _id(a["artifact_id"]), t.llm
    ),
    "graph": lambda t, a: graph_service.refresh_graph(
        t.session_factory, _id(a["environment_id"]), t.llm
    ),
    "write_graph": lambda t, a: graph_service.write_graph(
        t.session_factory, _id(a["artifact_id"]), t.llm
    ),
    "roadmap": lambda t, a: roadmap_service.refresh_roadmap(
        t.session_factory, _id(a["environment_id"]), t.llm
    ),
    "write_roadmap": lambda t, a: roadmap_service.write_roadmap(
        t.session_factory, _id(a["artifact_id"]), t.llm
    ),
    "write_practice": lambda t, a: practice_service.write_practice(
        t.session_factory, _id(a["artifact_id"]), t.llm, t.reranker
    ),
    "finish_update": lambda t, a: updates.finish(
        t.session_factory, _id(a["update_id"]), t.llm
    ),
    "transcribe_page": lambda t, a: maths_reading.transcribe_page(
        t.session_factory,
        _id(a["document_id"]),
        int(a["page"]),
        t.llm,
        _id(a["update_id"]),
        int(a["total"]),
    ),
    "apply_maths": lambda t, a: maths_reading.apply(
        t.session_factory, _id(a["document_id"]), int(a["first"]), int(a["last"])
    ),
    "read_figure": lambda t, a: figure_service.read_figure(
        t.session_factory,
        _id(a["document_id"]),
        figure_service.decode(a["figure"]),
        t.llm,
        _id(a["update_id"]),
        int(a["total"]),
    ),
    "apply_figures": lambda t, a: figure_service.apply(
        t.session_factory, _id(a["document_id"]), int(a["first"]), int(a["last"])
    ),
}


def step(call: str, label: str, update_step: str | None = None, **args) -> dict:
    """One step of a job: a function from STEPS, a label for the page, and,
    for a material update, the update step it records itself as."""
    if call not in STEPS:
        raise ValueError(f"unknown step {call!r}")
    return {
        "call": call,
        "label": label,
        "update_step": update_step,
        "args": {k: str(v) for k, v in args.items()},
    }


def document_steps(document_id, environment_id, update_id) -> tuple[list, list]:
    """A document added, read again or replaced: reading it (read lane), then
    everything derived from it (model lane), each step recorded on its
    update."""
    read = [
        step(
            "process_document", "Reading the document", "read", document_id=document_id
        )
    ]
    derive = [
        step("queue_concepts", "Queuing its concepts", document_id=document_id),
        step(
            "summarize",
            "Writing its summary",
            "document_summary",
            document_id=document_id,
        ),
        step(
            "environment_summary",
            "Updating the environment summary",
            "environment_summary",
            environment_id=environment_id,
        ),
        step("extract", "Extracting concepts", "concepts", document_id=document_id),
        step(
            "graph",
            "Updating the knowledge map",
            "knowledge_graph",
            environment_id=environment_id,
        ),
        step(
            "roadmap", "Updating the roadmap", "roadmap", environment_id=environment_id
        ),
        step("finish_update", "Summing up what changed", update_id=update_id),
    ]
    return read, derive


def maths_steps(document_id, update_id, pages: list[int], first: int, last: int):
    """Reading a document's maths (decision record 26): one step per page,
    so the reading shows its progress and stops between pages when
    cancelled, then putting the pages read in place."""
    return [
        step(
            "transcribe_page",
            f"Reading the maths of page {page}",
            document_id=document_id,
            page=page,
            update_id=update_id,
            total=len(pages),
        )
        for page in pages
    ] + [
        step(
            "apply_maths",
            "Putting the pages read in place",
            "maths",
            document_id=document_id,
            first=first,
            last=last,
        )
    ]


def figure_steps(document_id, update_id, figures: list, first: int, last: int):
    """Reading a document's figures (decision record 29): one step per
    figure, then putting the figures read in place."""
    return [
        step(
            "read_figure",
            f"Reading {figure_service.name(figure)} on page {figure.page}",
            document_id=document_id,
            figure=figure_service.encode(figure),
            update_id=update_id,
            total=len(figures),
        )
        for figure in figures
    ] + [
        step(
            "apply_figures",
            "Putting the figures read in place",
            "figures",
            document_id=document_id,
            first=first,
            last=last,
        )
    ]


def deletion_steps(environment_id, update_id) -> list:
    return [
        step(
            "environment_summary",
            "Updating the environment summary",
            "environment_summary",
            environment_id=environment_id,
        ),
        step(
            "graph",
            "Updating the knowledge map",
            "knowledge_graph",
            environment_id=environment_id,
        ),
        step(
            "roadmap", "Updating the roadmap", "roadmap", environment_id=environment_id
        ),
        step("finish_update", "Summing up what changed", update_id=update_id),
    ]


# --- dispatching ---------------------------------------------------------------


class Dispatcher(Protocol):
    def dispatch(self, job: Job, background, tools: Tools) -> None:
        """Make sure a newly queued job gets run."""

    def workers(self) -> int | None:
        """How many workers are running; None when that cannot be known."""


class RedisDispatcher:
    """Wakes the worker through Redis. If Redis cannot be reached the job is
    still queued in Postgres, and the worker finds it within seconds."""

    def __init__(self, url: str):
        self.url = url

    def _client(self) -> redis.Redis:
        return redis.Redis.from_url(
            self.url, socket_timeout=2, socket_connect_timeout=2
        )

    def dispatch(self, job: Job, background, tools: Tools) -> None:
        try:
            self._client().lpush(SIGNAL.format(lane=job.lane), str(job.id))
        except redis.RedisError:
            logger.warning("Could not signal job %s through Redis", job.id)

    def workers(self) -> int | None:
        try:
            return sum(1 for _ in self._client().scan_iter(f"{WORKER_KEY}*"))
        except redis.RedisError:
            return None


class InlineDispatcher:
    """Runs each job in this process right after the response, as the
    background tasks before jobs did. For tests, which need no Redis and no
    worker."""

    def dispatch(self, job: Job, background, tools: Tools) -> None:
        background.add_task(run_now, tools, job.id)

    def workers(self) -> int | None:
        return 1


def start(
    session: Session,
    *,
    environment_id: uuid.UUID,
    kind: str,
    title: str,
    lane: str,
    steps: list,
    tools: Tools,
    dispatcher: Dispatcher,
    background,
    update_id: uuid.UUID | None = None,
    after: Job | None = None,
) -> Job:
    """Queue a job and have it run. Commits.

    The same work is never queued twice (record 21): while a job with the
    same key is queued or running in the environment, that job is returned
    instead of a new one. Two requests arriving together both miss it, and
    then the database's unique index refuses the second insert; the insert
    sits in a savepoint, so the refusal undoes only it, and the job that won
    is returned."""
    key = job_key(kind, steps)
    existing = _active(session, environment_id, key)
    if existing is not None:
        return existing
    job = Job(
        environment_id=environment_id,
        update_id=update_id,
        after_id=after.id if after else None,
        kind=kind,
        key=key,
        request_id=context.request_id.get(),
        title=title,
        lane=lane,
        steps=steps,
        status="queued",
        progress=0,
        created_at=datetime.now(UTC),
    )
    try:
        with session.begin_nested():
            session.add(job)
    except IntegrityError:
        existing = _active(session, environment_id, key)
        if existing is None:
            raise
        session.commit()
        return existing
    session.commit()
    dispatcher.dispatch(job, background, tools)
    return job


def reading(session: Session, document_id: uuid.UUID) -> Job | None:
    """The queued or running job reading this document, if there is one.
    Asking to read it again meanwhile would queue a second chain with its
    own material update, which the job key cannot see as the same work."""
    return session.scalar(
        select(Job)
        .where(
            Job.kind == "read",
            Job.status.in_(ACTIVE),
            Job.steps.contains([{"args": {"document_id": str(document_id)}}]),
        )
        .limit(1)
    )


def job_key(kind: str, steps: list) -> str:
    """What a job does, as a fingerprint: its kind and its steps with their
    arguments, not whether each is done yet. Two jobs with the same key
    would do the same work."""
    plain = [{k: v for k, v in s.items() if k != "done"} for s in steps]
    text = json.dumps({"kind": kind, "steps": plain}, sort_keys=True, default=str)
    return hashlib.sha256(text.encode()).hexdigest()[:32]


def _active(session: Session, environment_id: uuid.UUID, key: str) -> Job | None:
    return session.scalar(
        select(Job).where(
            Job.environment_id == environment_id,
            Job.key == key,
            Job.status.in_(ACTIVE),
        )
    )


def queue_model_work(
    session: Session,
    environment_id: uuid.UUID,
    kind: str,
    title: str,
    steps: list,
    *,
    session_factory: SessionFactory,
    llm: LLMProvider,
    dispatcher: Dispatcher,
    background,
    reranker=None,
) -> Job:
    """Queue work for the language model, asked for by a request."""
    return start(
        session,
        environment_id=environment_id,
        kind=kind,
        title=title,
        lane="model",
        steps=steps,
        tools=Tools(session_factory, llm, reranker=reranker),
        dispatcher=dispatcher,
        background=background,
    )


# --- claiming and running -----------------------------------------------------


def claim(
    session: Session,
    lane: str,
    worker: str,
    now: datetime | None = None,
    job_id: uuid.UUID | None = None,
) -> Job | None:
    """Take the oldest queued job of a lane that may run now, marking it
    running. A job waiting for another runs once that one has ended; if
    that one was cancelled, so is this. Rows other workers hold are skipped.
    Commits."""
    now = now or datetime.now(UTC)
    query = (
        select(Job)
        .where(
            Job.lane == lane,
            Job.status == "queued",
            or_(Job.not_before.is_(None), Job.not_before <= now),
        )
        .order_by(Job.created_at, Job.id)
        .limit(20)
        .with_for_update(skip_locked=True)
    )
    if job_id is not None:
        query = query.where(Job.id == job_id)
    for job in session.scalars(query):
        before = session.get(Job, job.after_id) if job.after_id else None
        if before is not None and before.status in ACTIVE:
            continue
        if before is not None and before.status == "cancelled":
            _end_cancelled(session, job, now)
            continue
        job.status = "running"
        job.attempts += 1
        job.worker = worker
        job.started_at = now
        job.heartbeat_at = now
        job.error = None
        session.commit()
        return job
    session.commit()
    return None


def _end_cancelled(
    session: Session, job: Job, now: datetime, was_running: bool = False
) -> None:
    job.status = "cancelled"
    job.step = None
    job.finished_at = now
    release(session, job, retrying=False, was_running=was_running)
    if job.update_id:
        updates.cancel(session, job.update_id, now)
    for waiting in session.scalars(
        select(Job).where(Job.after_id == job.id, Job.status == "queued")
    ):
        _end_cancelled(session, waiting, now)


def _outcome(session: Session, job: Job) -> str | None:
    """Why a job that ran to its end failed, from what its steps recorded:
    the update it carried out, the document it read, or the results it was
    to write. None if nothing failed."""
    if job.update_id and job.lane == "model":
        record = session.get(MaterialUpdate, job.update_id)
        if record is not None:
            failed = [s for s in record.steps if s["state"] == "failed"]
            if failed:
                return f"{failed[0]['label']}: {failed[0]['detail']}"
    problems, written = [], 0
    for spec in job.steps:
        args = spec["args"]
        if spec["call"] == "process_document":
            document = session.get(Document, _id(args["document_id"]))
            if document is not None and document.status == "failed":
                problems.append(document.error)
        if "artifact_id" in args:
            written += 1
            artifact = session.get(GeneratedArtifact, _id(args["artifact_id"]))
            if artifact is not None and artifact.status == "failed":
                problems.append(artifact.error)
    if not problems:
        return None
    if written > 1:
        return f"{len(problems)} of {written} could not be written: {problems[0]}"
    return problems[0]


def run(tools: Tools, job_id: uuid.UUID) -> None:
    """Run a claimed job's steps in order, recording progress, then how it
    ended. Each step is marked done as it completes, so a job run again,
    after a crash or a worker's stop, starts at its first step not done. A
    crash is retried later, up to the job's attempts.

    Deleting an environment deletes its jobs, a running one too: a job whose
    row is gone stops where it is, with nothing left to record."""
    factory = tools.session_factory
    with factory() as session:
        job = session.get(Job, job_id)
        if job is None:  # deleted with its environment since it was claimed
            return
        steps, update_id = list(job.steps), job.update_id
        title, request = job.title, job.request_id
    # Every log line written while the job runs carries these (app/logs.py).
    tokens = [
        (context.job_id, context.job_id.set(str(job_id))),
        (
            context.update_id,
            context.update_id.set(str(update_id) if update_id else None),
        ),
        (context.request_id, context.request_id.set(request)),
    ]
    started = time.perf_counter()
    logger.info("Job started: %s", title, extra={"title": title})
    try:
        _run(tools, job_id, steps, update_id)
    finally:
        with factory() as session:
            ended = session.get(Job, job_id)
            ms = round(1000 * (time.perf_counter() - started))
            if ended is None:
                logger.info(
                    "Job deleted with its environment: %s",
                    title,
                    extra={"title": title, "ms": ms},
                )
            else:
                logger.info(
                    "Job %s: %s",
                    ended.status,
                    title,
                    extra={
                        "title": title,
                        "status": ended.status,
                        "reason": ended.error,
                        "ms": ms,
                    },
                )
        for var, token in reversed(tokens):
            var.reset(token)


def _run(tools: Tools, job_id: uuid.UUID, steps: list, update_id) -> None:
    factory = tools.session_factory
    try:
        for index, spec in enumerate(steps):
            if spec.get("done"):
                continue
            with factory() as session:
                job = session.get(Job, job_id, with_for_update=True)
                if job is None:  # deleted with its environment
                    return
                if job.cancel_requested:
                    _end_cancelled(session, job, datetime.now(UTC), was_running=True)
                    session.commit()
                    return
                if tools.stopping is not None and tools.stopping.is_set():
                    # The worker is stopping: the next one carries on from
                    # this step, and this run does not count as an attempt.
                    job.status, job.worker, job.step = "queued", None, None
                    job.attempts -= 1
                    session.commit()
                    return
                job.step = spec["label"]
                job.progress = 100 * index // len(steps)
                job.heartbeat_at = datetime.now(UTC)
                session.commit()
            work = STEPS[spec["call"]]
            step_started = time.perf_counter()
            if spec.get("update_step") and update_id:
                updates.run_step(
                    factory,
                    update_id,
                    spec["update_step"],
                    tools.llm,
                    work,
                    tools,
                    spec["args"],
                )
            else:
                work(tools, spec["args"])
            logger.info(
                "Step done: %s",
                spec["label"],
                extra={
                    "step": spec["call"],
                    "ms": round(1000 * (time.perf_counter() - step_started)),
                },
            )
            steps[index] = {**spec, "done": True}
            with factory() as session:
                job = session.get(Job, job_id, with_for_update=True)
                if job is None:  # deleted with its environment
                    return
                job.steps = list(steps)
                session.commit()
    except Exception as exc:
        logger.exception("Job %s failed", job_id)
        # The model's own reasons say what to do ("Is Ollama running?"); a
        # step that calls it directly, reading a page, leaves them to the job.
        why = str(exc) if isinstance(exc, LLMError) else None
        with factory() as session:
            job = session.get(Job, job_id, with_for_update=True)
            if job is None:  # deleted with its environment, perhaps the cause
                return
            _retry_or_fail(
                job, datetime.now(UTC), why or "An unexpected error stopped this job."
            )
            release(session, job, retrying=job.status == "queued", was_running=True)
            session.commit()
        return
    with factory() as session:
        job = session.get(Job, job_id, with_for_update=True)
        if job is None:  # deleted with its environment
            return
        error = _outcome(session, job)
        job.status = "failed" if error else "succeeded"
        job.error = error
        job.progress = 100
        job.step = None
        job.finished_at = datetime.now(UTC)
        session.commit()


def _named_artifacts(job: Job) -> set[uuid.UUID]:
    """The artifacts the job's steps not yet done would write."""
    return {
        _id(s["args"]["artifact_id"])
        for s in job.steps
        if not s.get("done") and "artifact_id" in s["args"]
    }


def release(
    session: Session, job: Job, *, retrying: bool, was_running: bool
) -> list[uuid.UUID]:
    """Settle the artifacts a model job leaves unfinished when it stops
    without finishing, instead of leaving them to the one-hour stale rule
    (record 21). Returns the artifacts changed; the caller commits.

    - An artifact still generating was being written by this job, if it was
      running: only a running model job writes, one at a time. If a step of
      the job will write it again on the retry, it goes back to pending;
      otherwise it fails with the job's reason, and a retried step re-arms
      it, as anyone can from the page.
    - A pending artifact that a step never reached fails with the job's
      reason when the job ends for good, unless another active job would
      still write it.
    """
    if job.lane != "model":
        return []
    reason = job.error or "Cancelled before it was written."
    remaining = _named_artifacts(job)
    still_wanted: set[uuid.UUID] = set()
    if not retrying:
        for other in session.scalars(
            select(Job).where(
                Job.environment_id == job.environment_id,
                Job.status.in_(ACTIVE),
                Job.id != job.id,
            )
        ):
            still_wanted |= _named_artifacts(other)
    released = []
    for artifact in session.scalars(
        select(GeneratedArtifact)
        .where(
            GeneratedArtifact.environment_id == job.environment_id,
            GeneratedArtifact.status.in_(("pending", "generating")),
        )
        .with_for_update()
    ):
        if artifact.status == "generating" and was_running:
            if retrying and artifact.id in remaining:
                artifact.status, artifact.error = "pending", None
            else:
                artifact.status, artifact.error = "failed", reason
        elif (
            artifact.status == "pending"
            and not retrying
            and artifact.id in remaining
            and artifact.id not in still_wanted
        ):
            artifact.status, artifact.error = "failed", reason
        else:
            continue
        released.append(artifact.id)
    return released


def _retry_or_fail(job: Job, now: datetime, why: str) -> None:
    if job.attempts < job.max_attempts:
        job.status = "queued"
        job.not_before = now + RETRY_AFTER[min(job.attempts, len(RETRY_AFTER)) - 1]
        job.error = f"{why} Trying again."
        job.worker = None
    else:
        job.status = "failed"
        job.error = why
        job.finished_at = now
    job.step = None


def run_now(tools: Tools, job_id: uuid.UUID) -> None:
    """Claim one job and run it, here and now (the inline dispatcher)."""
    with tools.session_factory() as session:
        job = session.get(Job, job_id)
        if job is None:
            return
        claimed = claim(session, job.lane, "inline", job_id=job_id)
    if claimed is not None:
        run(tools, job_id)


def recover(session: Session, now: datetime | None = None) -> int:
    """Jobs left running by a worker that stopped (no heartbeat for STALE):
    run again later, or failed after their last attempt. Commits. Returns
    how many were found."""
    now = now or datetime.now(UTC)
    stale = list(
        session.scalars(
            select(Job)
            .where(Job.status == "running", Job.heartbeat_at < now - STALE)
            .with_for_update(skip_locked=True)
        )
    )
    for job in stale:
        _retry_or_fail(job, now, "Its worker stopped while running it.")
        release(session, job, retrying=job.status == "queued", was_running=True)
    session.commit()
    return len(stale)


def beat(session: Session, worker: str, job_ids, now: datetime | None = None) -> None:
    """Mark as alive the jobs a worker is running at this moment. Commits.

    Only those it names: a job whose run has ended without its outcome being
    recorded, for example because the database failed just then, is still
    "running" in the table but no longer kept alive, so it is found as stale
    and run again (record 21)."""
    ids = list(job_ids)
    if not ids:
        return
    session.execute(
        update(Job)
        .where(Job.id.in_(ids), Job.worker == worker, Job.status == "running")
        .values(heartbeat_at=now or datetime.now(UTC))
    )
    session.commit()


def cancel(session: Session, job: Job, now: datetime | None = None) -> Job:
    """Cancel a job: a queued one at once, a running one before its next
    step. A finished job is left as it is. Commits."""
    now = now or datetime.now(UTC)
    if job.status == "queued":
        _end_cancelled(session, job, now)
    elif job.status == "running":
        job.cancel_requested = True
    session.commit()
    return job


# --- reading -------------------------------------------------------------------


def recent(session: Session, environment_id: uuid.UUID, limit: int = 20) -> list[Job]:
    """An environment's jobs: those queued or running first, then the rest,
    newest first."""
    jobs = list(
        session.scalars(
            select(Job)
            .where(Job.environment_id == environment_id)
            .order_by(Job.created_at.desc(), Job.id)
            .limit(limit)
        )
    )
    return sorted(jobs, key=lambda j: j.status not in ACTIVE)


def to_read(job: Job) -> JobRead:
    return JobRead(
        id=job.id,
        kind=job.kind,
        title=job.title,
        lane=job.lane,
        status=job.status,
        progress=job.progress,
        step=job.step,
        error=job.error,
        attempts=job.attempts,
        max_attempts=job.max_attempts,
        cancel_requested=job.cancel_requested,
        update_id=job.update_id,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        not_before=job.not_before,
    )
