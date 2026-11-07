"""Scoring each way of searching against the labelled fixture.

Purpose
-------
Loads tests/retrieval_fixture.py into an environment, asks every question
through each method, and reports how high the right passage comes back:

- keyword search alone, semantic search alone, and their fusion, before any
  reranking;
- the reranker fed by semantic search alone, by keyword search alone, and by
  the fusion of both, which is hybrid search as the app runs it.

Scores, over the top five results:

- MRR, mean reciprocal rank: 1 when the right passage is always first, 0.5
  when it is always second, 0 when it is never in the top five;
- hit@1: how often the right passage is first;
- reached: for the reranked methods, how often the right passage was among
  the candidates the reranker read at all.

tests/test_retrieval_quality.py asserts on these. To print the table, from
api/ with the development database running:

    python -m tests.retrieval_eval

That run works inside a transaction it rolls back, so it leaves nothing in
the database.
"""

import hashlib
import uuid
from collections import defaultdict
from dataclasses import dataclass, replace

from sqlalchemy.orm import Session

from app.embedding import Embedder
from app.models import Document, DocumentChunk, Environment
from app.reranking import Reranker
from app.services.search import RetrievalSizes, hybrid_search
from tests.retrieval_fixture import PASSAGES, QUESTIONS

# Scaled to the fixture. With only 28 passages the app's pool of 30 would hand
# the reranker everything and hide whether the searches found the right
# passage at all. A pool of 5 keeps the reranker, as in a real environment,
# reading only a small share of the passages.
EVAL_SIZES = RetrievalSizes(
    top_k_lexical=10, top_k_dense=10, candidate_pool=5, final_k=5
)

METHODS = {
    "keyword": "keyword search alone",
    "semantic": "semantic search alone",
    "fusion": "keyword + semantic, fused",
    "keyword+rerank": "keyword search, reranked",
    "semantic+rerank": "semantic search, reranked",
    "hybrid": "fused, reranked (the app)",
}
KINDS = ("term", "meaning", "mixed")


@dataclass(frozen=True)
class Score:
    mrr: float
    hit_at_1: float
    mrr_by_kind: dict[str, float]
    reached: float | None  # None for methods without a reranker


def load_fixture(
    session: Session, environment_id: uuid.UUID, embedder: Embedder
) -> dict[uuid.UUID, str]:
    """Store every passage as one chunk of one ready document, embedded, and
    return which chunk holds which passage."""
    document = Document(
        environment_id=environment_id,
        filename="operating-systems.pdf",
        size_bytes=1,
        sha256="0" * 64,
        status="ready",
        page_count=len(PASSAGES),
        pages_with_text=len(PASSAGES),
    )
    session.add(document)
    session.flush()
    contents = [f"{heading}\n\n{text}" for heading, text in PASSAGES.values()]
    vectors = embedder.embed_passages(contents)
    keys = {}
    for page, (key, content, vector) in enumerate(
        zip(PASSAGES, contents, vectors, strict=True), start=1
    ):
        chunk = DocumentChunk(
            id=uuid.uuid4(),
            document_id=document.id,
            ordinal=page,
            page_start=page,
            char_start=0,
            page_end=page,
            char_end=len(content),
            heading=PASSAGES[key][0],
            content=content,
            content_hash=hashlib.sha256(content.encode()).hexdigest(),
            embedding=vector,
            embedding_model=embedder.model_name,
        )
        session.add(chunk)
        keys[chunk.id] = key
    session.flush()
    return keys


def _reciprocal_rank(ranked: list[str], answers: tuple[str, ...]) -> float:
    for rank, key in enumerate(ranked[: EVAL_SIZES.final_k], start=1):
        if key in answers:
            return 1.0 / rank
    return 0.0


def evaluate(
    session: Session,
    environment_id: uuid.UUID,
    embedder: Embedder,
    reranker: Reranker,
    keys: dict[uuid.UUID, str],
) -> dict[str, Score]:
    """Every method's score over every question."""
    reranked = {
        "keyword+rerank": replace(EVAL_SIZES, top_k_dense=0),
        "semantic+rerank": replace(EVAL_SIZES, top_k_lexical=0),
        "hybrid": EVAL_SIZES,
    }
    rr: dict[str, list[float]] = defaultdict(list)
    reached: dict[str, list[bool]] = defaultdict(list)
    for question in QUESTIONS:
        full = hybrid_search(
            session, environment_id, question.text, embedder, reranker, EVAL_SIZES
        )
        # One full run holds both searches' own rankings and their fusion.
        by_lexical = sorted(
            (c for c in full.candidates if c.lexical_rank), key=lambda c: c.lexical_rank
        )
        by_semantic = sorted(
            (c for c in full.candidates if c.semantic_rank),
            key=lambda c: c.semantic_rank,
        )
        rankings = {
            "keyword": [keys[c.chunk.id] for c in by_lexical],
            "semantic": [keys[c.chunk.id] for c in by_semantic],
            "fusion": [keys[c.chunk.id] for c in full.candidates],
        }
        for name, sizes in reranked.items():
            result = (
                full
                if name == "hybrid"
                else hybrid_search(
                    session, environment_id, question.text, embedder, reranker, sizes
                )
            )
            rankings[name] = [keys[c.chunk.id] for c in result.results]
            pool = result.candidates[: max(sizes.candidate_pool, sizes.final_k)]
            reached[name].append(
                any(keys[c.chunk.id] in question.answers for c in pool)
            )
        for name, ranked in rankings.items():
            rr[name].append(_reciprocal_rank(ranked, question.answers))

    scores = {}
    for name in METHODS:
        values = rr[name]
        by_kind = {
            kind: _mean([v for v, q in zip(values, QUESTIONS) if q.kind == kind])
            for kind in KINDS
        }
        scores[name] = Score(
            mrr=_mean(values),
            hit_at_1=_mean([v == 1.0 for v in values]),
            mrr_by_kind=by_kind,
            reached=_mean(reached[name]) if name in reached else None,
        )
    return scores


def _mean(values) -> float:
    values = list(values)
    return sum(values) / len(values)


def format_table(scores: dict[str, Score]) -> str:
    counts = {kind: sum(q.kind == kind for q in QUESTIONS) for kind in KINDS}
    head = (
        f"{'method':28} {'MRR':>5} {'hit@1':>6} "
        + " ".join(f"{f'{kind} ({counts[kind]})':>12}" for kind in KINDS)
        + f" {'reached':>8}"
    )
    title = (
        f"{len(QUESTIONS)} questions, {len(PASSAGES)} passages; MRR over the top "
        f"{EVAL_SIZES.final_k}; the reranker reads {EVAL_SIZES.candidate_pool}"
    )
    lines = [
        title,
        head,
        "-" * len(head),
    ]
    for name, label in METHODS.items():
        s = scores[name]
        reached = "" if s.reached is None else f"{s.reached:.2f}"
        lines.append(
            f"{label:28} {s.mrr:5.3f} {s.hit_at_1:6.2f} "
            + " ".join(f"{s.mrr_by_kind[kind]:12.3f}" for kind in KINDS)
            + f" {reached:>8}"
        )
    return "\n".join(lines)


def main() -> None:
    from app.db import engine
    from app.embedding import default_embedder
    from app.reranking import default_reranker

    embedder, reranker = default_embedder(), default_reranker()
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            session = Session(bind=connection, join_transaction_mode="create_savepoint")
            environment = Environment(name="Retrieval evaluation")
            session.add(environment)
            session.flush()
            keys = load_fixture(session, environment.id, embedder)
            print(
                format_table(
                    evaluate(session, environment.id, embedder, reranker, keys)
                )
            )
        finally:
            transaction.rollback()


if __name__ == "__main__":
    main()
