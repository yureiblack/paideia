"""Finding chunks in an environment: by keyword and by meaning.

Purpose
-------
Two ways of searching one environment's chunks, both always limited to that
environment:

- keyword_search uses Postgres full-text search: word forms, phrases, OR and
  excluded words, ranked by how well the words match.
- semantic_search compares embeddings: it finds passages about the same idea
  even when they share no words with the query.

Phase 06 combines the two. Neither knows anything about HTTP.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import func, literal_column, select, text
from sqlalchemy.orm import Session

from app.embedding import Embedder
from app.models import Document, DocumentChunk

# The text-search configuration chunks are indexed with. Must match the one in
# models.SEARCH_VECTOR, or queries would be stemmed differently from the text.
_SEARCH_CONFIG = literal_column("'english'::regconfig")


def keyword_search(
    session: Session, environment_id: uuid.UUID, query: str, limit: int = 10
) -> list[tuple[DocumentChunk, float]]:
    """Full-text search over one environment's chunks, best match first.

    websearch_to_tsquery accepts what people type: plain words, "quoted
    phrases", OR, and -excluded words. ts_rank_cd scores by how many query
    terms appear and how close together; a heading counts for more than body
    text. Ties are broken by id so results are stable. A query of only stop
    words, such as "the", matches nothing.
    """
    if not query.strip():
        return []
    ts_query = func.websearch_to_tsquery(_SEARCH_CONFIG, query)
    rank = func.ts_rank_cd(DocumentChunk.search_vector, ts_query)
    statement = (
        select(DocumentChunk, rank)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            Document.environment_id == environment_id,
            DocumentChunk.search_vector.bool_op("@@")(ts_query),
        )
        .order_by(rank.desc(), DocumentChunk.id)
        .limit(limit)
    )
    return [(chunk, score) for chunk, score in session.execute(statement)]


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
    # finds the true nearest chunks more reliably. 100 covers the largest
    # top_k, 50, twice over, and the extra work is small at this project's
    # size. SET LOCAL lasts until this transaction ends.
    session.execute(text("SET LOCAL hnsw.iterative_scan = strict_order"))
    session.execute(text("SET LOCAL hnsw.ef_search = 100"))

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
