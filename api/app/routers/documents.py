"""HTTP endpoints for documents.

Purpose
-------
Upload and list live under the environment they belong to:

    POST   /api/environments/{environment_id}/documents?filename=...
    GET    /api/environments/{environment_id}/documents

Everything about one document lives at its own id:

    GET    /api/documents/{document_id}
    GET    /api/documents/{document_id}/pages
    GET    /api/documents/{document_id}/chunks
    POST   /api/documents/{document_id}/reprocess
    DELETE /api/documents/{document_id}

The upload is the raw PDF as the request body, not a multipart form. FastAPI
writes a form-uploaded file to disk in full before any of this code runs, so a
size limit could only be checked afterwards. Reading the raw body in chunks
lets the limit stop the transfer.
"""

import uuid
from pathlib import PurePosixPath
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Request,
    status,
)

from app import storage
from app.config import settings
from app.db import SessionDep, SessionFactoryDep
from app.models import Document
from app.parsing import Parser, PyMuPDFParser
from app.routers.deps import LLMDep
from app.routers.environments import EnvironmentDep
from app.routers.search import EmbedderDep
from app.schemas import ChunkRead, DocumentRead, PageRead
from app.services import concepts as concept_service
from app.services import documents as service
from app.services import environment_summaries as environment_summary_service
from app.services import graph as graph_service
from app.services import summaries as summary_service

router = APIRouter(tags=["documents"])


def get_parser() -> Parser:
    """The parser documents are read with. Tests can swap in another."""
    return PyMuPDFParser()


ParserDep = Annotated[Parser, Depends(get_parser)]


def document_or_404(document_id: uuid.UUID, session: SessionDep) -> Document:
    """Load the document named in the URL, or stop the request with a 404."""
    document = service.get_document(session, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document


DocumentDep = Annotated[Document, Depends(document_or_404)]


def _display_name(filename: str) -> str:
    """Keep only the last part of the name a client sent.

    A browser sends a bare name, but nothing stops another client sending a
    path. The name is only ever displayed, since files on disk are named by
    document id, but storing "../../secret" would still be misleading.
    """
    name = PurePosixPath(filename.replace("\\", "/")).name.strip()
    if not name:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail="filename must name a file"
        )
    return name


# Describes the raw-body upload in /docs, which cannot infer it, so the page
# offers a file picker.
UPLOAD_BODY = {
    "requestBody": {
        "required": True,
        "content": {
            "application/pdf": {"schema": {"type": "string", "format": "binary"}}
        },
    }
}


@router.post(
    "/environments/{environment_id}/documents",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
    openapi_extra=UPLOAD_BODY,
)
async def upload_document(
    request: Request,
    environment: EnvironmentDep,
    filename: Annotated[
        str, Query(min_length=1, max_length=255, description="The file's original name")
    ],
    session: SessionDep,
    session_factory: SessionFactoryDep,
    parser: ParserDep,
    embedder: EmbedderDep,
    llm: LLMDep,
    background: BackgroundTasks,
) -> Document:
    name = _display_name(filename)

    # Browsers announce a file's size before sending it, so an oversized file
    # can be refused before a single byte of it travels.
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > settings.max_upload_bytes:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"The file is larger than the {settings.max_upload_mb} MB limit.",
        )

    try:
        staged = await storage.stage_upload(
            request.stream(), max_bytes=settings.max_upload_bytes
        )
    except storage.UploadTooLarge as exc:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, detail=str(exc)) from exc
    except storage.NotAPdf as exc:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)
        ) from exc

    try:
        document = service.create_document(session, environment, staged, name)
    except service.DuplicateDocument as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    # Parsing happens after the response is sent; the client polls the status.
    # Background tasks run in order, so the summary is asked for once parsing
    # has finished.
    background.add_task(
        service.process_document, session_factory, document.id, parser, embedder
    )
    # Concepts are queued at once so they show as waiting while the summary,
    # which comes first, is written. Each later step follows straight after
    # the one it is built from, so no page sees a gap between them: the
    # environment's summary after the document's, the graph after concepts.
    background.add_task(
        concept_service.queue_when_ready, session_factory, document.id, llm
    )
    background.add_task(
        summary_service.summarize_when_ready, session_factory, document.id, llm
    )
    background.add_task(
        environment_summary_service.refresh_environment_summary,
        session_factory,
        document.environment_id,
        llm,
    )
    background.add_task(
        concept_service.extract_when_ready, session_factory, document.id, llm
    )
    background.add_task(
        graph_service.refresh_graph, session_factory, document.environment_id, llm
    )
    return document


@router.get(
    "/environments/{environment_id}/documents", response_model=list[DocumentRead]
)
def list_documents(environment: EnvironmentDep, session: SessionDep) -> list[Document]:
    return service.list_documents(session, environment.id)


@router.get("/documents/{document_id}", response_model=DocumentRead)
def read_document(document: DocumentDep) -> Document:
    return document


@router.get("/documents/{document_id}/pages", response_model=list[PageRead])
def read_pages(document: DocumentDep, session: SessionDep) -> list:
    return service.get_pages(session, document.id)


@router.get("/documents/{document_id}/chunks", response_model=list[ChunkRead])
def read_chunks(document: DocumentDep, session: SessionDep) -> list:
    """The passages a document was cut into, in reading order."""
    return service.get_chunks(session, document.id)


@router.post(
    "/documents/{document_id}/reprocess",
    response_model=DocumentRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def reprocess_document(
    document: DocumentDep,
    session: SessionDep,
    session_factory: SessionFactoryDep,
    parser: ParserDep,
    embedder: EmbedderDep,
    llm: LLMDep,
    background: BackgroundTasks,
) -> Document:
    try:
        service.request_reprocess(session, document)
    except service.StillProcessing as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    background.add_task(
        service.process_document, session_factory, document.id, parser, embedder
    )
    # Concepts are queued at once so they show as waiting while the summary,
    # which comes first, is written. Each later step follows straight after
    # the one it is built from, so no page sees a gap between them: the
    # environment's summary after the document's, the graph after concepts.
    background.add_task(
        concept_service.queue_when_ready, session_factory, document.id, llm
    )
    background.add_task(
        summary_service.summarize_when_ready, session_factory, document.id, llm
    )
    background.add_task(
        environment_summary_service.refresh_environment_summary,
        session_factory,
        document.environment_id,
        llm,
    )
    background.add_task(
        concept_service.extract_when_ready, session_factory, document.id, llm
    )
    background.add_task(
        graph_service.refresh_graph, session_factory, document.environment_id, llm
    )
    return document


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document: DocumentDep,
    session: SessionDep,
    session_factory: SessionFactoryDep,
    llm: LLMDep,
    background: BackgroundTasks,
) -> None:
    environment_id = document.environment_id
    service.delete_document(session, document)
    # Its concept links went with it; concepts no document mentions now go too.
    concept_service.refresh_concepts(session, environment_id)
    session.commit()
    # The environment's summary was built from this document: rebuild it from
    # what is left, or leave it as history if nothing is.
    background.add_task(
        environment_summary_service.refresh_environment_summary,
        session_factory,
        environment_id,
        llm,
    )
    # Its concepts' relationships went with them; the graph is rebuilt from
    # what is left, with remembered decisions only.
    background.add_task(
        graph_service.refresh_graph, session_factory, environment_id, llm
    )
