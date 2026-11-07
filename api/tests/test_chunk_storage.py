"""Tests for storing chunks during processing, and for full-text search.

Purpose: prove the roadmap's acceptance test, that processing the same PDF
again keeps the same chunk identities with no duplicates, and more: unchanged
chunks keep their very rows, so anything stored on them later survives. Then
prove search finds word forms, stays inside one environment, ranks headings
first and understands what people type.
"""

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import storage
from app.chunking import chunk_document
from app.models import Document, DocumentChunk, Environment
from app.parsing import ParseError, PyMuPDFParser
from app.schemas import EnvironmentCreate
from app.services import documents as service
from app.services import environments as environment_service
from app.services import search as search_service
from tests import pdfs
from tests.fakes import FakeEmbedder
from tests.parsed import H, P, Returns, document, words

OLD = datetime(2000, 1, 1, tzinfo=UTC)

LECTURE = document(
    [H("3.1 Process states"), P(words(500, "ready")), P(words(500, "running"))],
    [H("3.2 Scheduling"), P(words(400, "quantum"))],
)


def environment(session: Session, name: str = "Operating Systems") -> Environment:
    return environment_service.create_environment(session, EnvironmentCreate(name=name))


def upload(session: Session, env: Environment, data: bytes | None = None) -> Document:
    async def chunks():
        yield data or pdfs.pdf("placeholder")

    staged = asyncio.run(storage.stage_upload(chunks(), max_bytes=10_000_000))
    return service.create_document(session, env, staged, "lecture.pdf")


def run(session: Session, session_factory, document_id: uuid.UUID, parser) -> None:
    """Process, or reprocess, a document with the given parser."""
    row = session.get(Document, document_id)
    if row.status != "uploaded":
        service.request_reprocess(session, row)
    service.process_document(session_factory, document_id, parser, FakeEmbedder())
    session.expire_all()


@dataclass(frozen=True)
class Snapshot:
    """A chunk row's values copied out.

    The test session keeps one object per row. A list of rows taken before a
    reprocess would show the new values afterwards, or fail for deleted rows,
    so comparisons are made on copies.
    """

    id: uuid.UUID
    ordinal: int
    page_start: int
    heading: str | None
    content: str
    created_at: datetime


def chunks_of(session: Session, document_id: uuid.UUID) -> list[Snapshot]:
    session.expire_all()
    return [
        Snapshot(r.id, r.ordinal, r.page_start, r.heading, r.content, r.created_at)
        for r in service.get_chunks(session, document_id)
    ]


def stamp_old(session: Session, document_id: uuid.UUID) -> None:
    """Give every chunk row an old created_at. A row that survives a reprocess
    keeps it; a deleted and reinserted one would come back with today's date."""
    for row in service.get_chunks(session, document_id):
        row.created_at = OLD
    session.commit()


def processed(session: Session, session_factory, parsed=LECTURE, env=None) -> uuid.UUID:
    document_id = upload(session, env or environment(session)).id
    run(session, session_factory, document_id, Returns(parsed))
    return document_id


# --- storing ----------------------------------------------------------------


def test_processing_stores_exactly_the_chunkers_chunks(
    session: Session, session_factory
):
    document_id = processed(session, session_factory)

    expected = chunk_document(document_id, LECTURE)
    stored = chunks_of(session, document_id)
    assert [c.id for c in stored] == [c.id for c in expected]
    assert [c.content for c in stored] == [c.content for c in expected]
    assert [c.ordinal for c in stored] == list(range(len(expected)))


def test_reprocessing_the_same_pdf_keeps_ids_rows_and_count(
    session: Session, session_factory
):
    # The roadmap's acceptance test, with a real PDF through the real parser.
    lecture = pdfs.html_pdf(
        "<h1>Processes</h1><p>A process is a program in execution.</p>"
        "<h2>States</h2><p>New, ready, running, waiting, terminated.</p>",
        "<h2>Scheduling</h2><p>The scheduler picks the next ready process.</p>",
    )
    document_id = upload(session, environment(session), lecture).id
    run(session, session_factory, document_id, PyMuPDFParser())
    stamp_old(session, document_id)
    first = chunks_of(session, document_id)

    run(session, session_factory, document_id, PyMuPDFParser())

    second = chunks_of(session, document_id)
    assert len(first) == 3
    assert [c.id for c in second] == [c.id for c in first]
    assert all(c.created_at == OLD for c in second)  # the very same rows


def test_a_changed_section_replaces_only_its_own_chunks(
    session: Session, session_factory
):
    document_id = processed(session, session_factory)
    stamp_old(session, document_id)
    before = chunks_of(session, document_id)
    edited = document(
        [H("3.1 Process states"), P(words(500, "blocked")), P(words(500, "running"))],
        [H("3.2 Scheduling"), P(words(400, "quantum"))],
    )

    run(session, session_factory, document_id, Returns(edited))

    after = {c.id: c for c in chunks_of(session, document_id)}
    untouched = [c for c in before if c.heading == "3.2 Scheduling"]
    assert untouched and all(after[c.id].created_at == OLD for c in untouched)
    assert before[0].id not in after
    assert set(after) == {c.id for c in chunk_document(document_id, edited)}


def test_a_chunk_that_moves_keeps_its_row_and_updates_its_place(
    session: Session, session_factory
):
    document_id = processed(session, session_factory)
    stamp_old(session, document_id)
    last = chunks_of(session, document_id)[-1]
    with_preface = document(
        [H("Preface"), P("Read this first.")],
        [H("3.1 Process states"), P(words(500, "ready")), P(words(500, "running"))],
        [H("3.2 Scheduling"), P(words(400, "quantum"))],
    )

    run(session, session_factory, document_id, Returns(with_preface))

    moved = {c.id: c for c in chunks_of(session, document_id)}[last.id]
    assert moved.created_at == OLD
    assert moved.ordinal == last.ordinal + 1
    assert moved.page_start == last.page_start + 1


def test_a_failed_reprocess_removes_the_chunks(session: Session, session_factory):
    document_id = processed(session, session_factory)

    class Fails:
        def parse(self, path):
            raise ParseError("The PDF is password-protected.")

    run(session, session_factory, document_id, Fails())

    assert session.get(Document, document_id).status == "failed"
    assert chunks_of(session, document_id) == []


def test_deleting_documents_and_environments_removes_their_chunks(
    session: Session, session_factory
):
    env_a, env_b = environment(session, "A"), environment(session, "B")
    doc_a = processed(session, session_factory, env=env_a)
    processed(session, session_factory, env=env_b)
    count = select(func.count()).select_from(DocumentChunk)
    total = session.scalar(count)

    service.delete_document(session, session.get(Document, doc_a))
    assert session.scalar(count) == total // 2

    environment_service.delete_environment(session, env_b)
    session.expire_all()
    assert session.scalar(count) == 0


# --- search -----------------------------------------------------------------


@pytest.fixture
def library(session: Session, session_factory):
    """Two environments with known text."""
    os_env, other_env = (
        environment(session, "Operating Systems"),
        environment(session, "Other"),
    )
    os_text = document(
        [H("Process scheduling"), P("Round robin gives every task a time quantum.")],
        [
            H("Memory"),
            P("Paging maps virtual pages to frames. Each process has a page table."),
        ],
        [H("Deadlock"), P("Four conditions must hold for a deadlock to occur.")],
    )
    processed(session, session_factory, os_text, env=os_env)
    other_text = document([P("Many processes appear in this other environment too.")])
    processed(session, session_factory, other_text, env=other_env)
    return os_env, other_env


def search(
    session: Session, env: Environment, query: str, limit: int = 10
) -> list[str]:
    results = search_service.keyword_search(session, env.id, query, limit)
    return [hit.chunk.heading or hit.chunk.content for hit in results]


def test_search_matches_word_forms(session: Session, library):
    os_env, _ = library

    assert search(session, os_env, "processes") == ["Process scheduling", "Memory"]


def test_search_stays_inside_one_environment(session: Session, library):
    os_env, other_env = library
    other_only = "Many processes appear in this other environment too."

    assert search(session, other_env, "processes") == [other_only]
    assert search(session, other_env, "deadlock") == []
    assert other_only not in search(session, os_env, "processes")


def test_a_match_in_a_heading_ranks_first(session: Session, library):
    os_env, _ = library

    results = search_service.keyword_search(session, os_env.id, "process")

    assert results[0].chunk.heading == "Process scheduling"
    assert results[0].score > results[1].score
    assert results[0].filename == "lecture.pdf"


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        pytest.param('"page table"', ["Memory"], id="quoted phrase"),
        pytest.param(
            "deadlock OR quantum", ["Process scheduling", "Deadlock"], id="or"
        ),
        pytest.param("process -paging", ["Process scheduling"], id="excluded word"),
        pytest.param("   ", [], id="blank"),
        pytest.param("the and of", [], id="only stop words"),
        pytest.param("nonexistentterm", [], id="no match"),
    ],
)
def test_search_understands_what_people_type(
    session: Session, library, query, expected
):
    os_env, _ = library

    assert sorted(search(session, os_env, query)) == sorted(expected)


def test_any_word_of_a_question_can_match(session: Session, library):
    # Requiring every word would find nothing here: no chunk mentions
    # "decides" or "next". Without search syntax, any word may match.
    os_env, _ = library

    assert search(session, os_env, "what decides which task runs next") == [
        "Process scheduling"
    ]


def test_more_matching_words_rank_higher(session: Session, library):
    # All three words sit in body text, two in Memory's and one in
    # scheduling's, so no heading weight tips the balance.
    os_env, _ = library

    assert search(session, os_env, "virtual frames quantum") == [
        "Memory",
        "Process scheduling",
    ]


def test_search_respects_the_limit(session: Session, library):
    os_env, _ = library

    assert len(search(session, os_env, "process OR deadlock OR quantum", limit=2)) == 2
