"""Finding chunks in an environment: by keyword, by meaning, and both.

Purpose
-------
Three ways of searching one environment's chunks, all limited to that
environment:

- keyword_search uses Postgres full-text search: word forms, phrases, OR and
  excluded words, ranked by how well the words match.
- semantic_search compares embeddings: it finds passages about the same idea
  even when they share no words with the query.
- hybrid_search, the one the search endpoint uses, runs both, merges their
  rankings with Reciprocal Rank Fusion, and lets a cross-encoder reorder the
  best of the merged list. It keeps every stage's scores, so a search can be
  inspected.

None of them knows anything about HTTP.
"""

import re
import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import Text, cast, func, literal_column, select, text
from sqlalchemy.dialects.postgresql import TSQUERY
from sqlalchemy.orm import Session

from app.config import settings
from app.embedding import Embedder
from app.models import Document, DocumentChunk
from app.reranking import Reranker

# The text-search configuration chunks are indexed with. Must match the one in
# models.SEARCH_VECTOR, or queries would be stemmed differently from the text.
_SEARCH_CONFIG = literal_column("'english'::regconfig")

# A query written in search syntax: a "quoted phrase", the word OR, or a
# -word to exclude. A hyphen inside a word, as in C-SCAN, does not count.
_SEARCH_SYNTAX = re.compile(r'"|\bOR\b|(?:^|\s)-\w')


def _ts_query(query: str):
    """The full-text query for what was typed.

    Written in search syntax, a query means exactly what it says, as
    websearch_to_tsquery reads it. Otherwise any of its words may match:
    requiring all of them would find nothing for most questions people ask,
    such as "what decides which task runs next". plainto_tsquery joins the
    words with & (and), and turning each & into | (or) lets any one match.
    A query of only stop words, such as "the", has no words left; the empty
    text becomes NULL, which matches nothing.
    """
    if _SEARCH_SYNTAX.search(query):
        return func.websearch_to_tsquery(_SEARCH_CONFIG, query)
    all_words = cast(func.plainto_tsquery(_SEARCH_CONFIG, query), Text)
    return cast(func.nullif(func.replace(all_words, " & ", " | "), ""), TSQUERY)


@dataclass(frozen=True)
class KeywordHit:
    chunk: DocumentChunk
    filename: str
    score: float  # ts_rank: higher means more, and more important, words matched


def keyword_search(
    session: Session, environment_id: uuid.UUID, query: str, limit: int = 10
) -> list[KeywordHit]:
    """Full-text search over one environment's chunks, best match first.

    Words match in any form ("processes" finds "process"). ts_rank scores a
    chunk by how many of the query's words it contains and how often, and a
    match in a heading counts for more than one in body text. Ties are broken
    by id so results are stable.
    """
    if not query.strip():
        return []
    ts_query = _ts_query(query)
    rank = func.ts_rank(DocumentChunk.search_vector, ts_query)
    statement = (
        select(DocumentChunk, Document.filename, rank)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            Document.environment_id == environment_id,
            DocumentChunk.search_vector.bool_op("@@")(ts_query),
        )
        .order_by(rank.desc(), DocumentChunk.id)
        .limit(limit)
    )
    return [
        KeywordHit(chunk=chunk, filename=filename, score=float(score))
        for chunk, filename, score in session.execute(statement)
    ]


@dataclass(frozen=True)
class SemanticHit:
    chunk: DocumentChunk
    filename: str
    score: float  # cosine similarity: 1 means the same direction, higher is closer


def semantic_search(
    session: Session,
    environment_id: uuid.UUID,
    query: str,
    embedder: Embedder,
    limit: int = 10,
) -> list[SemanticHit]:
    """The chunks closest in meaning to the query, closest first.

    Only chunks embedded by the configured model count: a chunk without an
    embedding, or with one from another model, is left out until a reprocess
    computes a current one.
    """
    if not query.strip():
        return []
    query_vector = embedder.embed_query(query)

    # The vector index finds a fixed number of nearest candidates and only
    # then applies the environment filter. If another environment holds most
    # of the chunks, few or none of those candidates would survive. pgvector's
    # iterative scan keeps searching the index until enough rows pass the
    # filter.
    #
    # ef_search is how many candidates the index keeps in view while it
    # searches, 40 by default. The index is approximate, and a wider view
    # finds the true nearest chunks more reliably. Twice the number asked for,
    # and at least 100, costs little at this project's size; pgvector accepts
    # up to 1000. SET LOCAL lasts until this transaction ends.
    ef_search = min(1000, max(100, 2 * limit))
    session.execute(text("SET LOCAL hnsw.iterative_scan = strict_order"))
    session.execute(text(f"SET LOCAL hnsw.ef_search = {ef_search}"))

    distance = DocumentChunk.embedding.cosine_distance(query_vector)
    statement = (
        select(DocumentChunk, Document.filename, distance)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            Document.environment_id == environment_id,
            DocumentChunk.embedding_model == embedder.model_name,
            DocumentChunk.embedding.is_not(None),
        )
        # Distance alone, with no tie-breaker: the vector index can only serve
        # an ORDER BY on the distance itself, and a second sort key would turn
        # every search into a full scan.
        .order_by(distance)
        .limit(limit)
    )
    return [
        SemanticHit(chunk=chunk, filename=filename, score=1.0 - float(d))
        for chunk, filename, d in session.execute(statement)
    ]


# --- hybrid search -----------------------------------------------------------

# The constant from the paper that introduced Reciprocal Rank Fusion (Cormack,
# Clarke and Büttcher, 2009), and the usual choice since. It narrows the gap
# between first and second place, so one list's top result cannot outweigh
# agreement between the lists.
RRF_K = 60


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[uuid.UUID]], k: int = RRF_K
) -> list[tuple[uuid.UUID, float]]:
    """Merge several rankings into one, best first.

    An item earns 1 / (k + rank) from every list it appears in, and its
    earnings add up, so an item near the top of both lists beats one at the
    top of only one. Only positions count, never the lists' own scores, so a
    keyword score and a cosine similarity never need a common scale. An item
    missing from a list simply earns nothing there. Ties are broken by id, so
    the order is always the same.
    """
    scores: dict[uuid.UUID, float] = defaultdict(float)
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] += 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))


@dataclass(frozen=True)
class RetrievalSizes:
    """How many chunks each stage of a hybrid search considers.

    top_k_lexical and top_k_dense: how many each search contributes.
    candidate_pool: how many of the merged list the reranker reads.
    final_k: how many results come back.

    The settings never allow 0, but here a size of 0 switches that search
    off, which is how the evaluation measures each search on its own.
    """

    top_k_lexical: int
    top_k_dense: int
    candidate_pool: int
    final_k: int

    @classmethod
    def from_settings(cls, final_k: int | None = None) -> "RetrievalSizes":
        return cls(
            top_k_lexical=settings.retrieval_top_k_lexical,
            top_k_dense=settings.retrieval_top_k_dense,
            candidate_pool=settings.retrieval_candidate_pool,
            final_k=final_k or settings.retrieval_final_k,
        )


@dataclass
class Candidate:
    """One chunk found by either search, with its place at every stage.

    Ranks count from 1. A stage that never saw the chunk leaves its fields as
    None: a chunk only keyword search found has no semantic rank, and one
    outside the candidate pool has no rerank score.
    """

    chunk: DocumentChunk
    filename: str
    lexical_rank: int | None = None
    lexical_score: float | None = None
    semantic_rank: int | None = None
    semantic_score: float | None = None
    fusion_score: float = 0.0
    rerank_score: float | None = None
    final_rank: int | None = None


@dataclass(frozen=True)
class HybridResult:
    results: list[Candidate]  # the answer: best first, at most final_k
    candidates: list[Candidate]  # every chunk either search found, merged order
    sizes: RetrievalSizes


def _rerank_text(chunk: DocumentChunk) -> str:
    """What the reranker reads for a chunk: its text, with its section heading
    in front when the text does not already start with it, so a passage from
    the middle of a section keeps its context."""
    if chunk.heading and not chunk.content.startswith(chunk.heading):
        return f"{chunk.heading}\n\n{chunk.content}"
    return chunk.content


def hybrid_search(
    session: Session,
    environment_id: uuid.UUID,
    query: str,
    embedder: Embedder,
    reranker: Reranker,
    sizes: RetrievalSizes,
) -> HybridResult:
    """Keyword and semantic search together, reranked.

    1. Keyword search and semantic search each find their best chunks.
       Keywords catch exact terms, names and numbers; meaning catches
       paraphrases. A chunk without an embedding can still be found by its
       words.
    2. Reciprocal Rank Fusion merges the two rankings into one.
    3. The reranker reads the query with each of the best merged chunks, the
       candidate pool, or final_k of them if that is more, and scores them.
    4. The results are the best final_k by that score.
    """
    if not query.strip():
        return HybridResult(results=[], candidates=[], sizes=sizes)

    lexical = (
        keyword_search(session, environment_id, query, sizes.top_k_lexical)
        if sizes.top_k_lexical > 0
        else []
    )
    dense = (
        semantic_search(session, environment_id, query, embedder, sizes.top_k_dense)
        if sizes.top_k_dense > 0
        else []
    )

    found: dict[uuid.UUID, Candidate] = {}
    for rank, hit in enumerate(lexical, start=1):
        candidate = found.setdefault(hit.chunk.id, Candidate(hit.chunk, hit.filename))
        candidate.lexical_rank, candidate.lexical_score = rank, hit.score
    for rank, hit in enumerate(dense, start=1):
        candidate = found.setdefault(hit.chunk.id, Candidate(hit.chunk, hit.filename))
        candidate.semantic_rank, candidate.semantic_score = rank, hit.score

    fused = reciprocal_rank_fusion(
        [[hit.chunk.id for hit in lexical], [hit.chunk.id for hit in dense]]
    )
    candidates = []
    for chunk_id, fusion_score in fused:
        found[chunk_id].fusion_score = fusion_score
        candidates.append(found[chunk_id])

    pool = candidates[: max(sizes.candidate_pool, sizes.final_k)]
    if not pool:
        # Nothing matched, so the reranker, and its model, are never needed.
        return HybridResult(results=[], candidates=[], sizes=sizes)
    scores = reranker.score(query, [_rerank_text(c.chunk) for c in pool])
    for candidate, score in zip(pool, scores, strict=True):
        candidate.rerank_score = score
    # sorted() keeps equal scores in their merged order.
    order = sorted(range(len(pool)), key=lambda i: -scores[i])
    results = [pool[i] for i in order[: sizes.final_k]]
    for rank, candidate in enumerate(results, start=1):
        candidate.final_rank = rank
    return HybridResult(results=results, candidates=candidates, sizes=sizes)
