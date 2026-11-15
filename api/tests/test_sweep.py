"""Tests for storage.sweep() and the worker's sweep (decision record 21).

Purpose: a crash can leave files no document accounts for: part of an upload
that never finished arriving, a stored file whose row was never committed,
or the files of a deletion that stopped halfway. The sweep removes them, and
only them, sparing anything changed recently, since an upload in progress
has its file in place a moment before its row is committed.
"""

import os
import time
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from app import storage
from app.services import jobs
from app.worker import Worker
from tests import pdfs
from tests.fakes import MockProvider
from tests.test_documents_api import new_environment, uploaded

NOW = time.time()
HOUR = 60 * 60


def put(path: Path, age: float, data: bytes = b"%PDF-1.7") -> Path:
    """A file whose last change was age seconds ago."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    os.utime(path, (NOW - age, NOW - age))
    return path


def age_folder(path: Path, age: float) -> None:
    os.utime(path, (NOW - age, NOW - age))


def test_only_old_files_no_document_accounts_for_are_removed(data_dir: Path):
    env, other_env, gone_env = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    doc = uuid.uuid4()
    kept = put(storage.document_path(env, doc), age=30 * HOUR)
    orphan = put(storage.document_path(env, uuid.uuid4()), age=2 * HOUR)
    arriving = put(storage.document_path(env, uuid.uuid4()), age=60)
    junk = put(storage.uploads_dir(env) / "notes.txt", age=2 * HOUR)
    stale_part = put(data_dir / "tmp" / "a.part", age=25 * HOUR)
    # Older than an hour but not a day: a slow upload may still be arriving.
    fresh_part = put(data_dir / "tmp" / "b.part", age=2 * HOUR)
    # The files of a deleted environment, whose deletion stopped halfway.
    leftover = put(storage.document_path(gone_env, uuid.uuid4()), age=3 * HOUR)
    age_folder(storage.uploads_dir(gone_env), 3 * HOUR)
    # An environment's empty folder, changed a moment ago: an upload may be
    # about to move its file in.
    storage.uploads_dir(other_env).mkdir(parents=True)

    swept = storage.sweep({(env, doc)}, now=NOW)

    assert sorted(swept.files) == sorted([orphan, junk, leftover])
    assert swept.parts == [stale_part]
    # The folder's time changed when its file went; the next sweep, an hour
    # on, removes it.
    assert swept.folders == []
    assert all(p.exists() for p in (kept, arriving, fresh_part))
    assert not any(p.exists() for p in (orphan, junk, stale_part, leftover))
    assert storage.uploads_dir(other_env).exists()

    later = storage.sweep({(env, doc)}, now=NOW + 2 * HOUR)

    assert storage.uploads_dir(gone_env) in later.folders
    assert storage.uploads_dir(other_env) in later.folders
    assert storage.uploads_dir(env) not in later.folders  # it has a document
    # Two hours on, the file that was arriving never got its row: an orphan.
    assert later.files == [arriving]
    assert kept.exists()


def test_a_sweep_with_nothing_to_do_removes_nothing(data_dir: Path):
    swept = storage.sweep(set(), now=NOW)

    assert not swept
    assert (swept.parts, swept.files, swept.folders) == ([], [], [])


def test_the_worker_keeps_every_documents_file_and_removes_the_rest(
    client: TestClient, session_factory, data_dir: Path
):
    env = new_environment(client)
    document = uploaded(client, env, pdfs.pdf("Threads."))
    stored = storage.document_path(uuid.UUID(env), uuid.UUID(document["id"]))
    orphan = put(storage.document_path(uuid.UUID(env), uuid.uuid4()), age=2 * HOUR)
    os.utime(stored, (NOW - 2 * HOUR, NOW - 2 * HOUR))
    worker = Worker(
        jobs.Tools(session_factory, MockProvider()),
        "redis://localhost:6379/15",
        name="sweeper",
    )

    swept = worker.sweep()

    assert swept.files == [orphan]
    assert stored.exists() and not orphan.exists()
