"""POST /api/search: find the passages in one environment that best answer a
query.

Purpose
-------
Translate a search request into a hybrid search, keyword and semantic search
merged and reranked, and its result into the response, with every stage's
scores when the request asks for them.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.db import SessionDep
from app.embedding import Embedder, EmbeddingError, default_embedder
from app.reranking import Reranker, RerankError, default_reranker
from app.schemas import (
    SearchCandidate,
    SearchDebug,
    SearchRequest,
    SearchResponse,
    SearchResult,
)
from app.services import environments as environment_service
from app.services import search as search_service
from app.services import sources as source_service

router = APIRouter(tags=["search"])


def get_embedder() -> Embedder:
    """The embedder queries and documents are embedded with. Tests swap it."""
    return default_embedder()


EmbedderDep = Annotated[Embedder, Depends(get_embedder)]


def get_reranker() -> Reranker:
    """The reranker search results are ordered by. Tests swap it."""
    return default_reranker()


RerankerDep = Annotated[Reranker, Depends(get_reranker)]


@router.post("/search", response_model=SearchResponse)
def search(
    request: SearchRequest,
    session: SessionDep,
    embedder: EmbedderDep,
    reranker: RerankerDep,
) -> SearchResponse:
    if environment_service.get_environment(session, request.environment_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Environment not found")
    sizes = search_service.RetrievalSizes.from_settings(final_k=request.top_k)
    try:
        found = search_service.hybrid_search(
            session, request.environment_id, request.query, embedder, reranker, sizes
        )
    except (EmbeddingError, RerankError) as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    citations = source_service.cite_all(session, [c.chunk for c in found.results])
    return SearchResponse(
        results=[
            SearchResult(citation=citation, score=round(c.rerank_score, 4))
            for c, citation in zip(found.results, citations, strict=True)
        ],
        debug=_debug(found) if request.debug else None,
    )


def _debug(found: search_service.HybridResult) -> SearchDebug:
    return SearchDebug(
        top_k_lexical=found.sizes.top_k_lexical,
        top_k_dense=found.sizes.top_k_dense,
        candidate_pool=found.sizes.candidate_pool,
        final_k=found.sizes.final_k,
        candidates=[
            SearchCandidate(
                chunk_id=c.chunk.id,
                document_id=c.chunk.document_id,
                filename=c.filename,
                page_start=c.chunk.page_start,
                page_end=c.chunk.page_end,
                heading=c.chunk.heading,
                lexical_rank=c.lexical_rank,
                lexical_score=c.lexical_score,
                semantic_rank=c.semantic_rank,
                semantic_score=c.semantic_score,
                fusion_score=c.fusion_score,
                rerank_score=c.rerank_score,
                final_rank=c.final_rank,
            )
            for c in found.candidates
        ],
    )
