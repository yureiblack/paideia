"""Failures forced between the steps of writes that change both the
database and the files, or that end a job (decision record 21).

Purpose: each of these writes must leave the database and the disk agreeing
whatever step fails. An upload whose row is not committed leaves no file; a
new version whose row is not committed keeps the old file and row; a file
that is not the version its row records is never read as if it were; a
deletion that is not committed removes nothing; and a job whose outcome
cannot be recorded is no longer kept alive, so it is found and run again.
"""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app import storage
from app.models import Document, Environment, Job
from app.services import documents as service
from app.services import environments as environment_service
from app.services import jobs
from app.worker import Worker
from tests import pdfs
from tests.fakes import MockProvider
from tests.test_document_service import environment, process, upload
from tests.test_jobs import note, queue


def staged(data: bytes) -> storage.StagedUpload:
    async def chunks():
        yield data

    return asyncio.run(storage.stage_upload(chunks(), max_bytes=10_000_000))


def failing_commit(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    """The session's next commit fails, as it would if the database went
    away at that moment. Only that commit: the session's own commit comes
    back for the rest of the test. (monkeypatch.undo() would also undo the
    fixture that keeps every test's files out of the real data folder.)"""
    real = session.commit

    def boom():
        session.commit = real
        raise OperationalError("COMMIT", {}, Exception("the database went away"))

    monkeypatch.setattr(session, "commit", boom)


def files_of(env: Environment) -> list[str]:
    folder = storage.uploads_dir(env.id)
    return sorted(p.name for p in folder.iterdir()) if folder.exists() else []


def test_an_upload_whose_commit_fails_leaves_no_file_and_no_row(
    session: Session, monkeypatch
):
    env = environment(session)
    failing_commit(session, monkeypatch)

    with pytest.raises(OperationalError):
        service.create_document(session, env, staged(pdfs.pdf("Threads.")), "a.pdf")

    session.rollback()
    assert session.scalar(select(func.count()).select_from(Document)) == 0
    assert files_of(env) == []


def test_a_new_version_whose_commit_fails_keeps_the_old_file_and_row(
    session: Session, session_factory, monkeypatch
):
    env = environment(session)
    document = process(session, session_factory, upload(session, env, pdfs.pdf("v1")))
    old_sha = document.sha256
    path = storage.document_path(env.id, document.id)
    failing_commit(session, monkeypatch)

    with pytest.raises(OperationalError):
        service.new_version(session, document, staged(pdfs.pdf("v2")))

    session.rollback()
    session.refresh(document)
    assert (document.sha256, document.status) == (old_sha, "ready")
    assert storage.fingerprint(path) == old_sha
    assert files_of(env) == [path.name]  # nothing left set aside


def test_a_new_version_that_commits_replaces_the_file(
    session: Session, session_factory
):
    env = environment(session)
    document = process(session, session_factory, upload(session, env, pdfs.pdf("v1")))
    new = staged(pdfs.pdf("v2"))

    service.new_version(session, document, new)

    path = storage.document_path(env.id, document.id)
    assert storage.fingerprint(path) == new.sha256 == document.sha256
    assert files_of(env) == [path.name]


def test_a_file_that_is_not_the_recorded_version_is_never_read(
    session: Session, session_factory
):
    env = environment(session)
    document = upload(session, env, pdfs.pdf("The version the row records."))
    # As after a crash between replacing the file and committing its row.
    storage.document_path(env.id, document.id).write_bytes(pdfs.pdf("Another file."))

    document = process(session, session_factory, document)

    assert document.status == "failed"
    assert document.error == (
        "The stored file is not the version this document records. Upload it again."
    )


def test_a_document_delete_whose_commit_fails_removes_nothing(
    session: Session, monkeypatch
):
    env = environment(session)
    document = upload(session, env, pdfs.pdf("Keep me."))
    document_id = document.id
    failing_commit(session, monkeypatch)

    with pytest.raises(OperationalError):
        service.delete_document(session, document)

    session.rollback()
    assert session.get(Document, document_id) is not None
    assert storage.document_path(env.id, document_id).exists()


def test_an_environment_delete_whose_commit_fails_removes_nothing(
    session: Session, monkeypatch
):
    env = environment(session)
    upload(session, env, pdfs.pdf("Keep me too."))
    failing_commit(session, monkeypatch)

    with pytest.raises(OperationalError):
        environment_service.delete_environment(session, env)

    session.rollback()
    assert session.get(Environment, env.id) is not None
    assert len(files_of(env)) == 1


def test_a_job_whose_outcome_cannot_be_recorded_is_run_again(
    session: Session, session_factory, monkeypatch
):
    monkeypatch.setitem(jobs.STEPS, "note", lambda tools, args: None)
    env = environment(session)
    job = queue(session, session_factory, env, "Unlucky", [note("a")])
    worker = Worker(
        jobs.Tools(session_factory, MockProvider()),
        "redis://localhost:6379/15",
        name="w1",
    )

    def unrecordable(session, job):
        raise OperationalError("UPDATE", {}, Exception("the database went away"))

    monkeypatch.setattr(jobs, "_outcome", unrecordable)

    with pytest.raises(OperationalError):
        worker.run_one("model")

    session.expire_all()
    stuck = session.get(Job, job.id)
    assert stuck.status == "running"  # its outcome was never written
    assert worker.running == {}  # but the worker no longer runs it
    # The same worker goes on to run another job, which it keeps alive.
    other = queue(session, session_factory, env, "Next", [note("b")])
    jobs.claim(session, "model", "w1")
    worker.running["model"] = other.id
    later = datetime.now(UTC) + timedelta(minutes=3)
    jobs.beat(session, "w1", worker.running.values(), now=later)

    assert jobs.recover(session, now=later) == 1  # the stuck one, not the other
    session.expire_all()
    assert session.get(Job, job.id).status == "queued"
    assert session.get(Job, other.id).status == "running"
