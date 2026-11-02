"""Tests for app/services/documents.py, called directly with no HTTP.

Purpose: prove the document lifecycle. Uploads are stored once per environment,
parsing moves a document to ready or failed with its pages, reprocessing
recovers failures and abandoned parses, and deleting removes rows and files
without touching anything else.
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import storage
from app.models import Document, DocumentPage, Environment
from app.parsing import ParsedDocument, ParsedPage, PyMuPDFParser
from app.schemas import EnvironmentCreate
from app.services import documents as service
from app.services import environments as environment_service
from tests import pdfs


def environment(session: Session, name: str = "Operating Systems") -> Environment:
    return environment_service.create_environment(session, EnvironmentCreate(name=name))


def upload(
    session: Session, env: Environment, data: bytes, filename: str = "lecture.pdf"
):
    async def chunks():
        yield data

    staged = asyncio.run(storage.stage_upload(chunks(), max_bytes=10_000_000))
    return service.create_document(session, env, staged, filename)


def process(
    session: Session, session_factory, document: Document, parser=None
) -> Document:
    service.process_document(session_factory, document.id, parser or PyMuPDFParser())
    session.refresh(document)
    return document


def page_count_in_db(session: Session, document_id: uuid.UUID) -> int:
    query = select(func.count()).where(DocumentPage.document_id == document_id)
    return session.scalar(query)


# --- create -----------------------------------------------------------------


def test_upload_stores_the_file_named_by_id(session: Session, data_dir: Path):
    env = environment(session)
    data = pdfs.pdf("Processes")

    document = upload(session, env, data)

    assert document.status == "uploaded"
    assert document.size_bytes == len(data)
    assert len(document.sha256) == 64
    path = data_dir / "uploads" / str(env.id) / f"{document.id}.pdf"
    assert path.read_bytes() == data


def test_the_same_file_twice_in_one_environment_is_refused(
    session: Session, data_dir: Path
):
    # One set of bytes, sent twice. Two separately generated PDFs are different
    # files, because each carries a random file id.
    env, data = environment(session), pdfs.pdf("Processes")
    first = upload(session, env, data, "first.pdf")

    with pytest.raises(service.DuplicateDocument, match='"first.pdf"') as caught:
        upload(session, env, data, "again.pdf")

    assert caught.value.existing.id == first.id
    assert list((data_dir / "tmp").glob("*")) == []


def test_the_same_file_in_another_environment_is_allowed(session: Session):
    data = pdfs.pdf("Processes")
    upload(session, environment(session, "A"), data)

    assert upload(session, environment(session, "B"), data).status == "uploaded"


def test_the_database_catches_a_duplicate_the_code_check_missed(
    session: Session, monkeypatch: pytest.MonkeyPatch
):
    # Two identical uploads at the same instant can both pass the check in
    # code; the unique constraint must stop the second. Simulated by making
    # the check miss once.
    env, data = environment(session), pdfs.pdf("Processes")
    first = upload(session, env, data)
    real_check = service._find_duplicate
    calls = []

    def misses_the_first_time(*args):
        calls.append(args)
        return None if len(calls) == 1 else real_check(*args)

    monkeypatch.setattr(service, "_find_duplicate", misses_the_first_time)

    with pytest.raises(service.DuplicateDocument) as caught:
        upload(session, env, data)

    assert caught.value.existing.id == first.id
    # The first check missed, so only the database could have caught it.
    assert len(calls) == 2


# --- process ----------------------------------------------------------------


def test_processing_stores_every_page_and_marks_ready(
    session: Session, session_factory
):
    document = upload(session, environment(session), pdfs.pdf("One", "", "Three"))

    process(session, session_factory, document)

    assert document.status == "ready"
    assert document.error is None
    assert (document.page_count, document.pages_with_text, document.repaired) == (
        3,
        2,
        False,
    )
    pages = service.get_pages(session, document.id)
    assert [page.page_number for page in pages] == [1, 2, 3]
    assert [page.content.strip() for page in pages] == ["One", "", "Three"]


def test_an_unreadable_file_marks_the_document_failed(
    session: Session, session_factory
):
    document = upload(session, environment(session), pdfs.encrypted_pdf())

    process(session, session_factory, document)

    assert document.status == "failed"
    assert document.error == "The PDF is password-protected."
    assert document.page_count is None
    assert page_count_in_db(session, document.id) == 0


def test_an_unexpected_parser_crash_marks_failed(session: Session, session_factory):
    class Broken:
        def parse(self, path):
            raise RuntimeError("boom")

    document = upload(session, environment(session), pdfs.pdf("x"))

    process(session, session_factory, document, Broken())

    assert document.status == "failed"
    assert document.error == "An unexpected error occurred while reading the PDF."


def test_a_failure_to_store_the_result_marks_failed_not_stuck(
    session: Session, session_factory
):
    # A parser bug that lets a NUL through makes Postgres refuse the write.
    # The document must end failed, not sit in processing.
    class LeaksNul:
        def parse(self, path):
            return ParsedDocument(pages=[ParsedPage(1, "a\x00b")], repaired=False)

    document = upload(session, environment(session), pdfs.pdf("x"))

    process(session, session_factory, document, LeaksNul())

    assert document.status == "failed"
    assert document.error == "The PDF was read, but its text could not be stored."
    assert page_count_in_db(session, document.id) == 0


def test_a_document_not_waiting_to_be_parsed_is_left_alone(
    session: Session, session_factory
):
    document = upload(session, environment(session), pdfs.pdf("x"))
    process(session, session_factory, document)
    stamp = document.updated_at

    process(session, session_factory, document)

    assert document.status == "ready"
    assert document.updated_at == stamp


def test_a_document_deleted_mid_parse_is_dropped_quietly(
    session: Session, session_factory
):
    document = upload(session, environment(session), pdfs.pdf("x"))
    document_id = document.id

    class DeletesWhileParsing:
        def parse(self, path):
            with session_factory() as other:
                service.delete_document(other, other.get(Document, document_id))
            return ParsedDocument(pages=[ParsedPage(1, "x")], repaired=False)

    service.process_document(session_factory, document_id, DeletesWhileParsing())

    session.expire_all()
    assert session.get(Document, document_id) is None
    assert page_count_in_db(session, document_id) == 0


# --- reprocess --------------------------------------------------------------


def test_reprocessing_a_failure_queues_it_again(session: Session, session_factory):
    document = upload(session, environment(session), pdfs.encrypted_pdf())
    process(session, session_factory, document)

    service.request_reprocess(session, document)

    assert (document.status, document.error) == ("uploaded", None)


def test_reprocessing_replaces_pages_instead_of_adding_more(
    session: Session, session_factory
):
    document = upload(session, environment(session), pdfs.pdf("One", "Two"))
    process(session, session_factory, document)

    service.request_reprocess(session, document)
    process(session, session_factory, document)

    assert document.status == "ready"
    assert page_count_in_db(session, document.id) == 2


def test_a_live_parse_cannot_be_reprocessed(session: Session):
    document = upload(session, environment(session), pdfs.pdf("x"))
    document.status = "processing"
    session.commit()

    with pytest.raises(service.StillProcessing):
        service.request_reprocess(session, document)


def test_an_abandoned_parse_can_be_reprocessed(session: Session):
    document = upload(session, environment(session), pdfs.pdf("x"))
    document.status = "processing"
    session.commit()
    # As if a server restart had left it processing for an hour.
    document.updated_at = datetime.now(UTC) - timedelta(hours=1)

    service.request_reprocess(session, document)

    assert document.status == "uploaded"


# --- delete -----------------------------------------------------------------


def test_deleting_a_document_removes_its_row_pages_and_file(
    session: Session, session_factory, data_dir: Path
):
    env = environment(session)
    doomed = process(session, session_factory, upload(session, env, pdfs.pdf("a", "b")))
    kept = process(session, session_factory, upload(session, env, pdfs.pdf("c")))
    doomed_id = doomed.id

    service.delete_document(session, doomed)

    assert session.get(Document, doomed_id) is None
    assert page_count_in_db(session, doomed_id) == 0
    assert not storage.document_path(env.id, doomed_id).exists()
    assert page_count_in_db(session, kept.id) == 1
    assert storage.document_path(env.id, kept.id).exists()


def test_deleting_an_environment_removes_its_documents_pages_and_folder(
    session: Session, session_factory
):
    doomed_env, kept_env = environment(session, "Doomed"), environment(session, "Kept")
    doomed = process(
        session, session_factory, upload(session, doomed_env, pdfs.pdf("a"))
    )
    kept = process(session, session_factory, upload(session, kept_env, pdfs.pdf("b")))
    doomed_id, doomed_env_id = doomed.id, doomed_env.id

    environment_service.delete_environment(session, doomed_env)

    session.expire_all()
    assert session.get(Document, doomed_id) is None
    assert page_count_in_db(session, doomed_id) == 0
    assert not storage.uploads_dir(doomed_env_id).exists()
    assert session.get(Document, kept.id) is not None
    assert page_count_in_db(session, kept.id) == 1
    assert storage.document_path(kept_env.id, kept.id).exists()
