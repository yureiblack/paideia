"""Tests for embeddings during processing, and for semantic search.

Purpose: the roadmap's four tests for this phase, with the fast fake embedder:
embedding creation, missing embedding handling, top-k retrieval, and
environment-level filtering, the last under the conditions where a vector
index on its own would fail.
"""

import asyncio
import math
import uuid

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app import storage
from app.models import Document, DocumentChunk, DocumentPage, Environment
from app.schemas import EnvironmentCreate
from app.services import documents as service
from app.services import environments as environment_service
from app.services import search as search_service
from tests import pdfs
from tests.fakes import BrokenEmbedder, FakeEmbedder
from tests.parsed import H, P, Returns, document

LECTURE = document(
    [H("Scheduling"), P("Round robin gives every task a time quantum.")],
    [H("Paging"), P("Paging maps pages to frames.")],
    [H("Deadlock"), P("Four conditions cause a deadlock.")],
)


def environment(session: Session, name: str = "Operating Systems") -> Environment:
    return environment_service.create_environment(session, EnvironmentCreate(name=name))


def processed(
    session, session_factory, embedder, parsed=LECTURE, env=None
) -> uuid.UUID:
    async def chunks():
        yield pdfs.pdf("placeholder")

    staged = asyncio.run(storage.stage_upload(chunks(), max_bytes=10_000_000))
    document_id = service.create_document(
        session, env or environment(session), staged, "os.pdf"
    ).id
    service.process_document(session_factory, document_id, Returns(parsed), embedder)
    session.expire_all()
    return document_id


def reprocess(session, session_factory, document_id, embedder, parsed=LECTURE) -> None:
    service.request_reprocess(session, session.get(Document, document_id))
    service.process_document(session_factory, document_id, Returns(parsed), embedder)
    session.expire_all()


def stored(session: Session, document_id: uuid.UUID) -> list[DocumentChunk]:
    query = select(DocumentChunk).where(DocumentChunk.document_id == document_id)
    return list(session.scalars(query.order_by(DocumentChunk.ordinal)))


# --- embedding creation -----------------------------------------------------


def test_every_chunk_gets_an_embedding_from_the_model(
    session: Session, session_factory
):
    embedder = FakeEmbedder()
    document_id = processed(session, session_factory, embedder)

    rows = stored(session, document_id)
    assert len(rows) == 3
    assert all(len(row.embedding) == embedder.dimensions for row in rows)
    assert {row.embedding_model for row in rows} == {embedder.model_name}


def test_a_documents_chunks_are_embedded_in_one_batch(
    session: Session, session_factory
):
    calls = []

    class Counting(FakeEmbedder):
        def embed_passages(self, texts):
            calls.append(len(texts))
            return super().embed_passages(texts)

    processed(session, session_factory, Counting())

    assert calls == [3]


def test_reprocessing_an_unchanged_document_embeds_nothing(
    session: Session, session_factory
):
    document_id = processed(session, session_factory, FakeEmbedder())
    again = FakeEmbedder()

    reprocess(session, session_factory, document_id, again)

    assert again.passages_embedded == []
    assert all(row.embedding is not None for row in stored(session, document_id))


def test_an_edit_embeds_only_the_chunks_that_changed(session: Session, session_factory):
    document_id = processed(session, session_factory, FakeEmbedder())
    edited = document(
        [H("Scheduling"), P("Round robin gives every task a time quantum.")],
        [H("Paging"), P("Paging maps pages to frames with a page table.")],
        [H("Deadlock"), P("Four conditions cause a deadlock.")],
    )
    again = FakeEmbedder()

    reprocess(session, session_factory, document_id, again, edited)

    assert again.passages_embedded == [
        "Paging\n\nPaging maps pages to frames with a page table."
    ]


def another(session, session_factory, embedder, parsed, env, name) -> dict:
    """Process one more document, its own file, and return what changed."""

    async def chunks():
        yield pdfs.pdf(name)

    staged = asyncio.run(storage.stage_upload(chunks(), max_bytes=10_000_000))
    document_id = service.create_document(session, env, staged, name).id
    changes = service.process_document(
        session_factory, document_id, Returns(parsed), embedder
    )
    session.expire_all()
    return changes


def test_a_passage_already_embedded_in_any_document_is_reused(
    session: Session, session_factory
):
    first = processed(session, session_factory, FakeEmbedder())
    revised = document(
        [H("Scheduling"), P("Round robin gives every task a time quantum.")],
        [H("Paging"), P("Paging maps pages to frames with a page table.")],
        [H("Deadlock"), P("Four conditions cause a deadlock.")],
    )
    again = FakeEmbedder()

    # In another environment, as a new document: the shared passages are
    # found by their content, and only the edited one is embedded.
    changes = another(
        session, session_factory, again, revised, environment(session, "Copy"), "v2.pdf"
    )

    assert again.passages_embedded == [
        "Paging\n\nPaging maps pages to frames with a page table."
    ]
    assert changes == {
        "passages": 3,
        "new": 3,
        "kept": 0,
        "removed": 0,
        "embedded": 1,
        "reused": 2,
    }
    original = {r.content_hash: r.embedding for r in stored(session, first)}
    copy = session.scalars(
        select(DocumentChunk).where(DocumentChunk.content_hash.in_(original))
    ).all()
    # The first document's three, and the two passages the copy shares,
    # each shared one with the very same vector.
    assert len(copy) == 5
    for row in copy:
        assert list(row.embedding) == list(original[row.content_hash])


def test_a_reprocess_reports_what_it_kept_and_changed(
    session: Session, session_factory
):
    document_id = processed(session, session_factory, FakeEmbedder())
    edited = document(
        [H("Scheduling"), P("Round robin gives every task a time quantum.")],
        [H("Paging"), P("Paging maps pages to frames with a page table.")],
    )

    service.request_reprocess(session, session.get(Document, document_id))
    changes = service.process_document(
        session_factory, document_id, Returns(edited), FakeEmbedder()
    )

    assert changes == {
        "passages": 2,
        "new": 1,
        "kept": 1,
        "removed": 2,
        "embedded": 1,
        "reused": 0,
    }


# --- missing embeddings -----------------------------------------------------


def hits(session, env_id, query, embedder, limit=10) -> list[str]:
    return [
        h.chunk.heading
        for h in search_service.semantic_search(session, env_id, query, embedder, limit)
    ]


def test_a_chunk_without_an_embedding_is_left_out_then_filled_in(
    session: Session, session_factory
):
    embedder = FakeEmbedder()
    env = environment(session)
    document_id = processed(session, session_factory, embedder, env=env)
    paging = next(
        row for row in stored(session, document_id) if row.heading == "Paging"
    )
    paging.embedding, paging.embedding_model = None, None
    session.commit()

    assert "Paging" not in hits(session, env.id, "paging frames", embedder)

    again = FakeEmbedder()
    reprocess(session, session_factory, document_id, again)

    assert again.passages_embedded == ["Paging\n\nPaging maps pages to frames."]
    assert hits(session, env.id, "paging frames", embedder)[0] == "Paging"


def test_embeddings_from_another_model_count_as_missing(
    session: Session, session_factory
):
    embedder = FakeEmbedder()
    env = environment(session)
    document_id = processed(session, session_factory, embedder, env=env)
    for row in stored(session, document_id):
        row.embedding_model = "an-older-model"
    session.commit()

    assert hits(session, env.id, "deadlock", embedder) == []

    again = FakeEmbedder()
    reprocess(session, session_factory, document_id, again)

    assert len(again.passages_embedded) == 3
    assert hits(session, env.id, "deadlock", embedder)[0] == "Deadlock"


def test_an_embedding_failure_fails_the_document_with_its_reason(
    session: Session, session_factory
):
    document_id = processed(session, session_factory, BrokenEmbedder())

    row = session.get(Document, document_id)
    assert row.status == "failed"
    assert "No internet connection" in row.error
    assert stored(session, document_id) == []
    pages = select(DocumentPage).where(DocumentPage.document_id == document_id)
    assert list(session.scalars(pages)) == []


# --- top-k retrieval --------------------------------------------------------


def test_results_are_ordered_by_similarity_and_limited_to_top_k(
    session: Session, session_factory
):
    embedder = FakeEmbedder()
    env = environment(session)
    processed(session, session_factory, embedder, env=env)

    results = search_service.semantic_search(
        session, env.id, "deadlock conditions", embedder, 2
    )

    assert len(results) == 2
    assert results[0].chunk.heading == "Deadlock"
    assert results[0].score >= results[1].score
    assert all(-1.0 <= r.score <= 1.0 for r in results)
    assert results[0].filename == "os.pdf"


def test_a_blank_query_finds_nothing(session: Session, session_factory):
    env = environment(session)
    processed(session, session_factory, FakeEmbedder(), env=env)

    assert search_service.semantic_search(session, env.id, "   ", FakeEmbedder()) == []


# --- environment filtering --------------------------------------------------


def test_a_small_environment_is_not_crowded_out_by_a_large_one(
    session: Session, session_factory
):
    # The vector index first gathers a fixed number of nearest candidates, the
    # hnsw.ef_search setting, and only then applies the environment filter.
    # Here 300 chunks in another environment all sit closer to the query than
    # any of this environment's three, so every first candidate belongs
    # elsewhere. Without pgvector's iterative scan this search returns nothing;
    # with it, the index keeps going until three survive the filter.
    #
    # The vectors are placed by hand on a quarter circle around the query,
    # each at its own angle, so every distance is different. Word-hash vectors
    # would tie by the hundred, and the index, being approximate, then
    # sometimes loses track of the outnumbered few.
    embedder = FakeEmbedder()
    query = embedder.embed_query("apples")
    a = query.index(1.0)
    b = (a + 1) % embedder.dimensions

    def at_angle(degrees: float) -> list[float]:
        vector = [0.0] * embedder.dimensions
        vector[a] = math.cos(math.radians(degrees))
        vector[b] = math.sin(math.radians(degrees))
        return vector

    small, large = environment(session, "Small"), environment(session, "Large")
    small_docs = []
    for degrees in (65, 70, 75):
        doc_id = processed(
            session, session_factory, embedder, document([P("apples.")]), small
        )
        session.execute(
            update(DocumentChunk)
            .where(DocumentChunk.document_id == doc_id)
            .values(embedding=at_angle(degrees))
        )
        small_docs.append(doc_id)
    big_doc = processed(
        session, session_factory, embedder, document([P("filler.")]), large
    )
    session.add_all(
        DocumentChunk(
            id=uuid.uuid4(),
            document_id=big_doc,
            ordinal=n + 1,
            page_start=1,
            char_start=0,
            page_end=1,
            char_end=1,
            content="crowd",
            content_hash="0" * 64,
            embedding=at_angle(1 + 59 * n / 299),  # 1 to 60 degrees
            embedding_model=embedder.model_name,
        )
        for n in range(300)
    )
    session.commit()
    # Force the plan a large table would get: the vector index first, the
    # filter after. Dropping an index inside this test's transaction is rolled
    # back with everything else.
    session.execute(text("DROP INDEX ix_document_chunks_document_id"))
    session.execute(text("SET LOCAL enable_seqscan = off"))
    session.execute(text("SET LOCAL enable_bitmapscan = off"))

    results = search_service.semantic_search(session, small.id, "apples", embedder, 3)

    assert [r.chunk.document_id for r in results] == small_docs


def test_search_never_returns_another_environments_chunks(
    session: Session, session_factory
):
    embedder = FakeEmbedder()
    mine, theirs = environment(session, "Mine"), environment(session, "Theirs")
    processed(
        session, session_factory, embedder, document([P("deadlock deadlock.")]), theirs
    )
    processed(session, session_factory, embedder, LECTURE, mine)

    results = search_service.semantic_search(session, mine.id, "deadlock", embedder, 50)

    assert len(results) == 3
    assert {r.chunk.heading for r in results} == {"Scheduling", "Paging", "Deadlock"}


@pytest.mark.parametrize("limit", [1, 3])
def test_top_k_never_exceeds_what_exists(session: Session, session_factory, limit: int):
    env = environment(session)
    processed(session, session_factory, FakeEmbedder(), env=env)

    assert (
        len(
            search_service.semantic_search(
                session, env.id, "task", FakeEmbedder(), limit
            )
        )
        == limit
    )
