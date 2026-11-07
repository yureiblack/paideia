"""Tests for hybrid search in app/services/search.py.

Purpose: Reciprocal Rank Fusion's arithmetic, and the hybrid pipeline's
plumbing with the fast fakes: the size of each stage, what the reranker reads,
the order it decides, every stage's scores, chunks only one search can find,
and the environment boundary. Retrieval quality with the real models is
tested in test_retrieval_quality.py.
"""

import asyncio
import uuid

import pytest
from sqlalchemy import update
from sqlalchemy.orm import Session

from app import storage
from app.models import DocumentChunk, Environment
from app.schemas import EnvironmentCreate
from app.services import documents as document_service
from app.services import environments as environment_service
from app.services.search import (
    RetrievalSizes,
    hybrid_search,
    keyword_search,
    reciprocal_rank_fusion,
    semantic_search,
)
from tests import pdfs
from tests.fakes import BrokenReranker, FakeEmbedder, FakeReranker
from tests.parsed import H, P, Returns, document, words

LECTURE = document(
    [H("Scheduling"), P("Round robin gives every task a time quantum.")],
    [H("Paging"), P("Paging maps pages to frames.")],
    [H("Deadlock"), P("Four conditions cause a deadlock.")],
)
# Six one-chunk topics that every search finds for "task".
SIX_TOPICS = document(*[[H(f"Topic {n}"), P(f"task {n}.")] for n in "abcdef"])
ROOMY = RetrievalSizes(top_k_lexical=30, top_k_dense=30, candidate_pool=30, final_k=10)


def environment(session: Session, name: str = "Operating Systems") -> Environment:
    return environment_service.create_environment(session, EnvironmentCreate(name=name))


def processed(session, session_factory, parsed=LECTURE, env=None) -> uuid.UUID:
    async def chunks():
        yield pdfs.pdf("placeholder")

    staged = asyncio.run(storage.stage_upload(chunks(), max_bytes=10_000_000))
    document_id = document_service.create_document(
        session, env or environment(session), staged, "os.pdf"
    ).id
    document_service.process_document(
        session_factory, document_id, Returns(parsed), FakeEmbedder()
    )
    session.expire_all()
    return document_id


def search(session, env, query, reranker=None, sizes=ROOMY):
    return hybrid_search(
        session, env.id, query, FakeEmbedder(), reranker or FakeReranker(), sizes
    )


class Prefers:
    """A reranker that only likes passages containing one word."""

    model_name = "prefers"

    def __init__(self, word: str):
        self.word = word

    def score(self, query, passages):
        return [1.0 if self.word in passage else 0.0 for passage in passages]


# --- Reciprocal Rank Fusion -------------------------------------------------


def test_fusion_rewards_agreement_and_counts_items_from_one_list():
    a, b, c = (uuid.UUID(int=n) for n in (1, 2, 3))

    fused = reciprocal_rank_fusion([[a, b], [b, c]])

    # b is second in one list and first in the other; a and c are in one each.
    assert fused == [
        (b, pytest.approx(1 / 62 + 1 / 61)),
        (a, pytest.approx(1 / 61)),
        (c, pytest.approx(1 / 62)),
    ]


def test_fusion_breaks_ties_by_id():
    first, second = uuid.UUID(int=1), uuid.UUID(int=2)

    assert [item for item, _ in reciprocal_rank_fusion([[second], [first]])] == [
        first,
        second,
    ]


def test_fusion_uses_k_to_soften_the_ranks():
    a, b = uuid.UUID(int=1), uuid.UUID(int=2)

    assert reciprocal_rank_fusion([[a, b]], k=0) == [(a, 1.0), (b, 0.5)]
    assert reciprocal_rank_fusion([[], []]) == []


# --- the pipeline -------------------------------------------------------------


def test_each_search_contributes_only_its_share(session: Session, session_factory):
    env = environment(session)
    processed(session, session_factory, SIX_TOPICS, env)
    sizes = RetrievalSizes(
        top_k_lexical=2, top_k_dense=3, candidate_pool=30, final_k=10
    )

    found = search(session, env, "task", sizes=sizes)

    assert sum(c.lexical_rank is not None for c in found.candidates) == 2
    assert sum(c.semantic_rank is not None for c in found.candidates) == 3
    # How far the two overlap depends on ties among six near-identical
    # chunks; the merged list holds each chunk once either way.
    assert 3 <= len(found.candidates) <= 5


def test_the_reranker_reads_only_the_pool(session: Session, session_factory):
    env = environment(session)
    processed(session, session_factory, SIX_TOPICS, env)
    reranker = FakeReranker()
    sizes = RetrievalSizes(top_k_lexical=6, top_k_dense=6, candidate_pool=4, final_k=1)

    found = search(session, env, "task", reranker, sizes)

    assert len(found.candidates) == 6
    [(_, read)] = reranker.calls
    assert read == [c.chunk.content for c in found.candidates[:4]]
    assert all(c.rerank_score is None for c in found.candidates[4:])
    assert len(found.results) == 1


def test_asking_for_more_results_than_the_pool_reranks_that_many(
    session: Session, session_factory
):
    env = environment(session)
    processed(session, session_factory, SIX_TOPICS, env)
    reranker = FakeReranker()
    sizes = RetrievalSizes(top_k_lexical=6, top_k_dense=6, candidate_pool=2, final_k=5)

    found = search(session, env, "task", reranker, sizes)

    assert len(reranker.calls[0][1]) == 5
    assert len(found.results) == 5


def test_the_reranker_decides_the_final_order(session: Session, session_factory):
    env = environment(session)
    processed(session, session_factory, env=env)

    found = search(session, env, "paging frames", Prefers("deadlock"))

    assert found.candidates[0].chunk.heading == "Paging"  # the searches' favourite
    assert found.results[0].chunk.heading == "Deadlock"  # the reranker's
    assert [c.final_rank for c in found.results] == list(
        range(1, len(found.results) + 1)
    )


def test_every_stage_reports_its_scores(session: Session, session_factory):
    env = environment(session)
    processed(session, session_factory, env=env)
    sizes = RetrievalSizes(
        top_k_lexical=30, top_k_dense=30, candidate_pool=1, final_k=1
    )

    found = search(session, env, "paging", sizes=sizes)

    top = found.candidates[0]
    assert top.chunk.heading == "Paging"
    lexical = keyword_search(session, env.id, "paging")
    dense = semantic_search(session, env.id, "paging", FakeEmbedder())
    assert (top.lexical_rank, top.lexical_score) == (1, lexical[0].score)
    assert (top.semantic_rank, top.semantic_score) == (1, dense[0].score)
    assert top.fusion_score == pytest.approx(2 / 61)
    assert (top.rerank_score, top.final_rank) == (1.0, 1)
    assert top.filename == "os.pdf"
    # Outside the pool of one: found and fused, never reranked.
    rest = found.candidates[1:]
    assert rest and all(c.rerank_score is None and c.final_rank is None for c in rest)
    assert all(c.fusion_score > 0 for c in rest)


def test_a_chunk_without_an_embedding_is_found_by_its_words(
    session: Session, session_factory
):
    env = environment(session)
    document_id = processed(session, session_factory, env=env)
    session.execute(
        update(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .values(embedding=None)
    )

    found = search(session, env, "deadlock")

    assert found.results[0].chunk.heading == "Deadlock"
    assert found.results[0].semantic_rank is None
    assert found.results[0].lexical_rank == 1


def test_another_environments_chunks_are_never_candidates(
    session: Session, session_factory
):
    mine, theirs = environment(session, "Mine"), environment(session, "Theirs")
    theirs_doc = processed(
        session, session_factory, document([P("deadlock deadlock.")]), theirs
    )
    processed(session, session_factory, env=mine)

    found = search(session, mine, "deadlock")

    assert found.candidates
    assert theirs_doc not in {c.chunk.document_id for c in found.candidates}


def test_a_blank_query_or_an_empty_environment_needs_no_model(session: Session):
    env = environment(session)
    reranker = BrokenReranker()  # would fail if it were ever asked

    assert search(session, env, "   ", reranker).results == []
    assert search(session, env, "deadlock", reranker).candidates == []


def test_the_reranker_reads_each_chunk_with_its_heading(
    session: Session, session_factory
):
    # Two paragraphs of about 1000 characters make two chunks under one
    # heading. The second does not start with the heading, so the reranker is
    # given it in front.
    env = environment(session)
    processed(
        session,
        session_factory,
        document([H("Scheduling"), P(words(1000)), P(words(1000))]),
        env,
    )
    reranker = FakeReranker()

    search(session, env, "word", reranker)

    passages = reranker.calls[0][1]
    assert len(passages) == 2
    assert all(passage.startswith("Scheduling\n\nword") for passage in passages)
