"""POST /api/search: find the passages in one environment closest in meaning.

Purpose
-------
Translate a search request into a semantic search and its result into the
response. Phase 06 extends this same endpoint with keyword search, fusion and
reranking.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.db import SessionDep
from app.embedding import Embedder, EmbeddingError, default_embedder
from app.schemas import SearchRequest, SearchResponse, SearchResult
from app.services import environments as environment_service
from app.services import search as search_service

router = APIRouter(tags=["search"])


def get_embedder() -> Embedder:
    """The embedder queries and documents are embedded with. Tests swap it."""
    return default_embedder()


EmbedderDep = Annotated[Embedder, Depends(get_embedder)]


@router.post("/search", response_model=SearchResponse)
def search(
    request: SearchRequest, session: SessionDep, embedder: EmbedderDep
) -> SearchResponse:
    if environment_service.get_environment(session, request.environment_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Environment not found")
    try:
        hits = search_service.semantic_search(
            session, request.environment_id, request.query, embedder, request.top_k
        )
    except EmbeddingError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    return SearchResponse(
        results=[
            SearchResult(
                chunk_id=hit.chunk.id,
                document_id=hit.chunk.document_id,
                filename=hit.filename,
                page_start=hit.chunk.page_start,
                page_end=hit.chunk.page_end,
                heading=hit.chunk.heading,
                text=hit.chunk.content,
                score=round(hit.score, 4),
            )
            for hit in hits
        ]
    )
