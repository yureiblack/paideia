"""POST /api/documents/{document_id}/summary: a cited summary, on request.

Purpose
-------
Translate a request for a summary into the summary service, and its problems
into status codes: 409 for a document not read yet, 422 for one with no text
or too long to summarize on request, 503 when the language model cannot be
used. The summary is generated afresh each time and not stored.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.db import SessionDep
from app.llm import LLMError, LLMProvider, default_provider
from app.routers.documents import DocumentDep
from app.schemas import DocumentSummary
from app.services import summaries as service

router = APIRouter(tags=["summaries"])


def get_llm() -> LLMProvider:
    """The language model summaries are written with. Tests swap it."""
    return default_provider()


LLMDep = Annotated[LLMProvider, Depends(get_llm)]


@router.post("/documents/{document_id}/summary", response_model=DocumentSummary)
def summarize(
    document: DocumentDep, session: SessionDep, llm: LLMDep
) -> DocumentSummary:
    try:
        return service.summarize_document(session, document, llm)
    except service.NotReadyToSummarize as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except service.CannotSummarize as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    except LLMError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
