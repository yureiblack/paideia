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
    POST   /api/documents/{document_id}/versions   a new version, raw PDF body
    GET    /api/documents/{document_id}/maths      its maths pages, how far read
    POST   /api/documents/{document_id}/maths      read the maths of some pages
    GET    /api/documents/{document_id}/figures    its figures, how far read
    POST   /api/documents/{document_id}/figures    read the figures of some pages
    DELETE /api/documents/{document_id}
    GET    /api/figures/{figure_id}/image          a figure read, as a PNG

Each upload, new version, reprocess, maths or figure reading and deletion
records an update (record 17) whose steps follow the background work.

The upload is the raw file as the request body, a PDF or a picture (PNG or
JPEG, stored as a one-page PDF, record 29), not a multipart form. FastAPI
writes a form-uploaded file to disk in full before any of this code runs, so a
size limit could only be checked afterwards. Reading the raw body in chunks
lets the limit stop the transfer.
"""

import uuid
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)

from app import filenames, storage
from app.config import settings
from app.db import SessionDep, SessionFactoryDep
from app.models import Document
from app.parsing import ParseError, Parser, PyMuPDFParser
from app.routers.deps import DispatcherDep, LLMDep
from app.routers.environments import EnvironmentDep
from app.routers.search import EmbedderDep
from app.schemas import (
    ChunkRead,
    DocumentRead,
    FiguresRead,
    FiguresRequest,
    FoundFigure,
    JobRead,
    KeptFigure,
    KeptPage,
    MathsRead,
    MathsRequest,
    PageRead,
)
from app.services import concepts as concept_service
from app.services import documents as service
from app.services import figures as figure_service
from app.services import jobs, maths_reading, updates

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
    """The cleaned name the document is shown by (app/filenames.py)."""
    try:
        return filenames.display_name(filename)
    except filenames.BadFilename as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


def _not_queued_already(session, document: Document) -> None:
    """Refuse to read a document again while it is queued to be read, so a
    second click never queues a second chain (record 21)."""
    if jobs.reading(session, document.id) is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="This document is already queued to be read.",
        )


# Describes the raw-body upload in /docs, which cannot infer it, so the page
# offers a file picker.
UPLOAD_BODY = {
    "requestBody": {
        "required": True,
        "content": {
            kind: {"schema": {"type": "string", "format": "binary"}}
            for kind in ("application/pdf", "image/png", "image/jpeg")
        },
    }
}


async def _stage(request: Request) -> storage.StagedUpload:
    """Receive a PDF sent as the raw request body, refusing it early when it
    is too large or not a PDF."""
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
    return staged


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
    dispatcher: DispatcherDep,
    background: BackgroundTasks,
) -> Document:
    name = _display_name(filename)

    staged = await _stage(request)

    try:
        document = service.create_document(session, environment, staged, name)
    except service.DuplicateDocument as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    # Reading happens after the response is sent; the client polls the update.
    _queue_chain(
        background,
        session,
        session_factory,
        document,
        parser,
        embedder,
        llm,
        "added",
        dispatcher,
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
def read_pages(document: DocumentDep, session: SessionDep) -> list[PageRead]:
    pages = service.get_pages(session, document.id)
    figures = figure_service.page_figures(session, pages)
    return [
        PageRead(
            page_number=page.page_number,
            content=page.content,
            figures=figures.get(page.page_number, []),
        )
        for page in pages
    ]


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
    dispatcher: DispatcherDep,
    background: BackgroundTasks,
) -> Document:
    _not_queued_already(session, document)
    try:
        service.request_reprocess(session, document)
    except service.StillProcessing as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    _queue_chain(
        background,
        session,
        session_factory,
        document,
        parser,
        embedder,
        llm,
        "reprocessed",
        dispatcher,
    )
    return document


def _ready(document: Document) -> None:
    if document.status != "ready":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="The document has to be read before its maths can be.",
        )


@router.get("/documents/{document_id}/maths", response_model=MathsRead)
def read_maths(document: DocumentDep, session: SessionDep) -> MathsRead:
    """The pages of the document that hold maths, which of them have been
    read and which keep the PDF's own text, and how long a page takes."""
    _ready(document)
    try:
        found = maths_reading.overview(session, document)
    except ParseError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return MathsRead(
        maths_pages=sorted(found.maths_pages),
        read=found.read,
        waiting=found.waiting,
        kept_text=[
            KeptPage(page=page, reason=reason)
            for page, reason in sorted(found.kept_text.items())
        ],
        seconds_per_page=round(found.seconds_per_page, 1),
    )


@router.post(
    "/documents/{document_id}/maths",
    response_model=JobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def read_maths_pages(
    body: MathsRequest,
    document: DocumentDep,
    session: SessionDep,
    session_factory: SessionFactoryDep,
    parser: ParserDep,
    embedder: EmbedderDep,
    llm: LLMDep,
    dispatcher: DispatcherDep,
    background: BackgroundTasks,
) -> JobRead:
    """Read the maths of the pages from first_page to last_page with the
    vision model (decision record 26), then read the document again with
    them. Never done unasked: it takes about a minute a page."""
    _ready(document)
    pages = document.page_count or 0
    if not 1 <= body.first_page <= body.last_page <= pages:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Choose pages from 1 to {pages}, the first no later than the last.",
        )
    # Its chain includes reading the document again, which also refuses a
    # second reading of its maths while the first is queued.
    _not_queued_already(session, document)
    try:
        to_read = maths_reading.to_read(
            session, document, llm, body.first_page, body.last_page
        )
    except maths_reading.NothingToRead as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ParseError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    update = updates.begin(
        session, document.environment_id, "maths", document, llm, updates.MATHS_STEPS
    )
    common: dict[str, Any] = {
        "environment_id": document.environment_id,
        "tools": jobs.Tools(session_factory, llm, embedder, parser),
        "dispatcher": dispatcher,
        "background": background,
        "update_id": update.id,
    }
    reading_maths = jobs.start(
        session,
        kind="maths",
        title=f"Reading the maths of {document.filename}",
        lane="model",
        steps=jobs.maths_steps(
            document.id, update.id, to_read, body.first_page, body.last_page
        ),
        **common,
    )
    read, derive = jobs.document_steps(document.id, document.environment_id, update.id)
    reading = jobs.start(
        session,
        kind="read",
        title=f"Reading {document.filename}",
        lane="read",
        steps=read,
        after=reading_maths,
        **common,
    )
    jobs.start(
        session,
        kind="derive",
        title=f"Updating from {document.filename}",
        lane="model",
        steps=derive,
        after=reading,
        **common,
    )
    return jobs.to_read(reading_maths)


@router.get("/documents/{document_id}/figures", response_model=FiguresRead)
def read_figures(document: DocumentDep, session: SessionDep) -> FiguresRead:
    """The document's figures, which of them have been read and which keep
    the PDF's own text, and how long a figure takes (decision record 29)."""
    if document.status != "ready":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="The document has to be read before its figures can be.",
        )
    try:
        found = figure_service.overview(session, document)
    except ParseError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    by_key = {f.key: f for f in found.figures}
    return FiguresRead(
        figures=[
            FoundFigure(key=f.key, page=f.page, caption=f.caption)
            for f in found.figures
        ],
        read=found.read,
        waiting=found.waiting,
        kept=[
            KeptFigure(
                key=key,
                page=by_key[key].page if key in by_key else int(key.split(":")[0]),
                caption=by_key[key].caption if key in by_key else None,
                reason=reason,
            )
            for key, reason in sorted(found.kept.items())
        ],
        seconds_per_figure=round(found.seconds_per_figure, 1),
    )


@router.post(
    "/documents/{document_id}/figures",
    response_model=JobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def read_figures_of_pages(
    body: FiguresRequest,
    document: DocumentDep,
    session: SessionDep,
    session_factory: SessionFactoryDep,
    parser: ParserDep,
    embedder: EmbedderDep,
    llm: LLMDep,
    dispatcher: DispatcherDep,
    background: BackgroundTasks,
) -> JobRead:
    """Read the figures on the pages from first_page to last_page with the
    vision model (decision record 29), then read the document again with
    them. Never done unasked: it takes about a quarter of a minute a figure."""
    if document.status != "ready":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="The document has to be read before its figures can be.",
        )
    pages = document.page_count or 0
    if not 1 <= body.first_page <= body.last_page <= pages:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Choose pages from 1 to {pages}, the first no later than the last.",
        )
    _not_queued_already(session, document)
    try:
        to_read = figure_service.to_read(
            session, document, llm, body.first_page, body.last_page
        )
    except (figure_service.NothingToRead, ParseError) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    update = updates.begin(
        session, document.environment_id, "figures", document, llm, updates.FIGURE_STEPS
    )
    common: dict[str, Any] = {
        "environment_id": document.environment_id,
        "tools": jobs.Tools(session_factory, llm, embedder, parser),
        "dispatcher": dispatcher,
        "background": background,
        "update_id": update.id,
    }
    reading_figures = jobs.start(
        session,
        kind="figures",
        title=f"Reading the figures of {document.filename}",
        lane="model",
        steps=jobs.figure_steps(
            document.id, update.id, to_read, body.first_page, body.last_page
        ),
        **common,
    )
    read, derive = jobs.document_steps(document.id, document.environment_id, update.id)
    reading = jobs.start(
        session,
        kind="read",
        title=f"Reading {document.filename}",
        lane="read",
        steps=read,
        after=reading_figures,
        **common,
    )
    jobs.start(
        session,
        kind="derive",
        title=f"Updating from {document.filename}",
        lane="model",
        steps=derive,
        after=reading,
        **common,
    )
    return jobs.to_read(reading_figures)


@router.get(
    "/figures/{figure_id}/image",
    response_class=Response,
    responses={200: {"content": {"image/png": {}}}},
)
def figure_image(figure_id: uuid.UUID, session: SessionDep) -> Response:
    """A figure the model read, with its caption, drawn from the document's
    file (decision record 29). The same figure of the same file is always
    the same picture, so browsers may keep it."""
    try:
        image = figure_service.image(session, figure_id)
    except ParseError:
        image = None
    if image is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such figure.")
    return Response(
        image,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=86400, immutable"},
    )


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document: DocumentDep,
    session: SessionDep,
    session_factory: SessionFactoryDep,
    llm: LLMDep,
    dispatcher: DispatcherDep,
    background: BackgroundTasks,
) -> None:
    environment_id = document.environment_id
    update = updates.begin(
        session, environment_id, "deleted", document, llm, updates.DELETION_STEPS
    )
    service.delete_document(session, document)
    # Its concept links went with it; concepts no document mentions now go too.
    concept_service.refresh_concepts(session, environment_id)
    session.commit()
    # The environment's summary was built from this document: rebuild it from
    # what is left, or leave it as history if nothing is. Its concepts'
    # relationships went with them; the graph is rebuilt from what is left,
    # with remembered decisions only; then the roadmap.
    jobs.start(
        session,
        environment_id=environment_id,
        kind="derive",
        title=f"Updating after removing {update.filename}",
        lane="model",
        steps=jobs.deletion_steps(environment_id, update.id),
        tools=jobs.Tools(session_factory, llm),
        dispatcher=dispatcher,
        background=background,
        update_id=update.id,
    )


@router.post(
    "/documents/{document_id}/versions",
    response_model=DocumentRead,
    status_code=status.HTTP_202_ACCEPTED,
    openapi_extra=UPLOAD_BODY,
)
async def upload_new_version(
    request: Request,
    document: DocumentDep,
    session: SessionDep,
    session_factory: SessionFactoryDep,
    parser: ParserDep,
    embedder: EmbedderDep,
    llm: LLMDep,
    dispatcher: DispatcherDep,
    background: BackgroundTasks,
) -> Document:
    """A new version of a document, as the raw PDF body: the document keeps
    its id, name and place, and only what changed is redone (record 17)."""
    _not_queued_already(session, document)
    staged = await _stage(request)
    try:
        service.new_version(session, document, staged)
    except (
        service.SameVersion,
        service.DuplicateDocument,
        service.StillProcessing,
    ) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    _queue_chain(
        background,
        session,
        session_factory,
        document,
        parser,
        embedder,
        llm,
        "new_version",
        dispatcher,
    )
    return document


def _queue_chain(
    background: BackgroundTasks,
    session,
    session_factory,
    document: Document,
    parser: Parser,
    embedder,
    llm,
    kind: str,
    dispatcher,
) -> None:
    """Record an update for a document added, read again or replaced, and
    queue it as two jobs (decision record 18): reading it, then, once read,
    everything derived from it, each step recording itself on the update.
    Concepts are queued first so they show as waiting while the summary is
    written; each later step follows straight after what it is built from:
    the environment's summary after the document's, the graph after
    concepts, the roadmap after the graph."""
    update = updates.begin(
        session, document.environment_id, kind, document, llm, updates.DOCUMENT_STEPS
    )
    tools = jobs.Tools(session_factory, llm, embedder, parser)
    read, derive = jobs.document_steps(document.id, document.environment_id, update.id)
    common = {
        "environment_id": document.environment_id,
        "tools": tools,
        "dispatcher": dispatcher,
        "background": background,
        "update_id": update.id,
    }
    reading = jobs.start(
        session,
        kind="read",
        title=f"Reading {document.filename}",
        lane="read",
        steps=read,
        **common,
    )
    jobs.start(
        session,
        kind="derive",
        title=f"Updating from {document.filename}",
        lane="model",
        steps=derive,
        after=reading,
        **common,
    )
