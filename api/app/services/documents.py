"""Uploading, parsing, reprocessing and deleting documents.

Purpose
-------
The rules for documents live here, between the HTTP layer and the database.
Nothing in this module knows about requests or status codes; failures are
raised as exceptions the router translates.

A document moves through four statuses:

    uploaded     stored and waiting for a background task to parse it
    processing   a task is parsing it now
    ready        parsed; its pages and chunks are stored
    failed       could not be parsed; error says why

Only a document in uploaded can be claimed for parsing. Reprocessing puts a
document back into uploaded, which is how a failed parse is retried and how a
document abandoned in processing by a server restart is recovered.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, literal_column, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import storage
from app.chunking import Chunk, chunk_document
from app.db import SessionFactory
from app.models import Document, DocumentChunk, DocumentPage, Environment
from app.parsing import ParsedDocument, ParseError, Parser

logger = logging.getLogger(__name__)

# How long a document may sit in processing before reprocess treats it as
# abandoned, for example by a server restart in the middle of a parse.
STALE_PROCESSING = timedelta(minutes=10)


class DuplicateDocument(Exception):
    """The same file is already in this environment."""

    def __init__(self, existing: Document):
        super().__init__(
            f'This file is already in this environment as "{existing.filename}".'
        )
        self.existing = existing


class StillProcessing(Exception):
    """The document is being parsed right now."""


def list_documents(session: Session, environment_id: uuid.UUID) -> list[Document]:
    """An environment's documents, newest first, id breaking ties."""
    query = (
        select(Document)
        .where(Document.environment_id == environment_id)
        .order_by(Document.created_at.desc(), Document.id)
    )
    return list(session.scalars(query))


def get_document(session: Session, document_id: uuid.UUID) -> Document | None:
    return session.get(Document, document_id)


def get_pages(session: Session, document_id: uuid.UUID) -> list[DocumentPage]:
    """A document's pages in reading order. Empty until a parse succeeds."""
    query = (
        select(DocumentPage)
        .where(DocumentPage.document_id == document_id)
        .order_by(DocumentPage.page_number)
    )
    return list(session.scalars(query))


def _find_duplicate(
    session: Session, environment_id: uuid.UUID, sha256: str
) -> Document | None:
    query = select(Document).where(
        Document.environment_id == environment_id, Document.sha256 == sha256
    )
    return session.scalars(query).first()


def create_document(
    session: Session,
    environment: Environment,
    staged: storage.StagedUpload,
    filename: str,
) -> Document:
    """Record a received upload and move its file into place.

    Raises DuplicateDocument when the environment already holds a file with
    the same fingerprint. The unique constraint on (environment_id, sha256)
    backs this check up: if two identical uploads pass it at the same moment,
    the database refuses the second insert.
    """
    existing = _find_duplicate(session, environment.id, staged.sha256)
    if existing is not None:
        storage.discard(staged)
        raise DuplicateDocument(existing)

    document = Document(
        environment_id=environment.id,
        filename=filename,
        size_bytes=staged.size_bytes,
        sha256=staged.sha256,
    )
    session.add(document)
    try:
        # Insert now, so the database assigns the id the file is named after.
        session.flush()
    except IntegrityError:
        session.rollback()
        storage.discard(staged)
        winner = _find_duplicate(session, environment.id, staged.sha256)
        if winner is None:
            raise
        raise DuplicateDocument(winner) from None

    storage.store(staged, environment.id, document.id)
    try:
        session.commit()
    except Exception:
        storage.delete_document_file(environment.id, document.id)
        raise
    return document


def _lock(session: Session, document_id: uuid.UUID) -> Document | None:
    """Load a document fresh from the database and lock its row.

    FOR UPDATE makes anyone else who tries to change this row, or delete it,
    wait until this transaction ends.
    """
    return session.get(
        Document, document_id, with_for_update=True, populate_existing=True
    )


def process_document(
    session_factory: SessionFactory, document_id: uuid.UUID, parser: Parser
) -> None:
    """Parse a document's file and store its pages. Runs as a background task.

    It first claims the document by moving it from uploaded to processing; a
    document in any other status was claimed already, or deleted, and is left
    alone. The parse itself happens without holding the lock, so the document
    is locked and read again before the result is written: it may have been
    deleted in the meantime.

    Whatever goes wrong, the document ends ready or failed, never stuck in
    processing: a failed parse and a failed write both mark it failed.
    """
    with session_factory() as session:
        document = _lock(session, document_id)
        if document is None or document.status != "uploaded":
            session.rollback()
            return
        document.status = "processing"
        document.error = None
        session.commit()
        path = storage.document_path(document.environment_id, document.id)

        parsed: ParsedDocument | None = None
        chunks: list[Chunk] = []
        error: str | None = None
        try:
            parsed = parser.parse(path)
            chunks = chunk_document(document_id, parsed)
        except ParseError as exc:
            parsed, error = None, str(exc)
        except Exception:
            logger.exception("Unexpected error while parsing document %s", document_id)
            parsed = None
            error = "An unexpected error occurred while reading the PDF."

        try:
            _store_result(session, document_id, parsed, chunks, error)
        except Exception:
            # Storing the result failed, so nothing of it was kept. Record the
            # failure in a fresh transaction rather than leaving the document
            # in processing until the stale timeout frees it.
            session.rollback()
            logger.exception("Could not store the parse of document %s", document_id)
            _store_result(
                session,
                document_id,
                None,
                [],
                "The PDF was read, but its text could not be stored.",
            )


def _store_result(
    session: Session,
    document_id: uuid.UUID,
    parsed: ParsedDocument | None,
    chunks: list[Chunk],
    error: str | None,
) -> None:
    """Write a parse's outcome: ready with its pages and chunks, or failed."""
    document = _lock(session, document_id)
    if document is None:  # deleted while it was being parsed
        session.rollback()
        return

    # A document's pages are replaced as a whole, inside this transaction:
    # readers see the old set or the new one, never a mixture.
    session.execute(delete(DocumentPage).where(DocumentPage.document_id == document_id))
    _sync_chunks(session, document_id, chunks)
    if parsed is None:
        document.status = "failed"
        document.error = error
        document.page_count = None
        document.pages_with_text = None
        document.repaired = False
    else:
        session.add_all(
            DocumentPage(
                document_id=document_id, page_number=page.number, content=page.text
            )
            for page in parsed.pages
        )
        document.status = "ready"
        document.error = None
        document.page_count = len(parsed.pages)
        document.pages_with_text = parsed.pages_with_text
        document.repaired = parsed.repaired
    session.commit()


# The chunk fields that may change while its content, and so its id, stays the
# same: text added or removed earlier in the document moves it.
_CHUNK_POSITION = (
    "ordinal",
    "page_start",
    "char_start",
    "page_end",
    "char_end",
    "heading",
)


def _sync_chunks(session: Session, document_id: uuid.UUID, chunks: list[Chunk]) -> None:
    """Make the stored chunks match the given ones, touching only what changed.

    A chunk's id is derived from its content, so a chunk produced again keeps
    its row: anything stored on it later, such as an embedding, survives a
    reprocess. Only its position is updated if it moved. Chunks no longer
    produced are deleted and new ones inserted. Passing no chunks deletes them
    all, as for a failed parse.
    """
    query = select(DocumentChunk).where(DocumentChunk.document_id == document_id)
    stored = {row.id: row for row in session.scalars(query)}
    wanted = {chunk.id for chunk in chunks}

    for chunk_id, row in stored.items():
        if chunk_id not in wanted:
            session.delete(row)
    for chunk in chunks:
        row = stored.get(chunk.id)
        if row is None:
            session.add(
                DocumentChunk(
                    id=chunk.id,
                    document_id=document_id,
                    content=chunk.content,
                    content_hash=chunk.content_hash,
                    **{field: getattr(chunk, field) for field in _CHUNK_POSITION},
                )
            )
            continue
        for field in _CHUNK_POSITION:
            if getattr(row, field) != getattr(chunk, field):
                setattr(row, field, getattr(chunk, field))


def get_chunks(session: Session, document_id: uuid.UUID) -> list[DocumentChunk]:
    """A document's chunks in reading order. Empty until a parse succeeds."""
    query = (
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.ordinal)
    )
    return list(session.scalars(query))


# The text-search configuration chunks are indexed with. Must match the one in
# models.SEARCH_VECTOR, or queries would be stemmed differently from the text.
_SEARCH_CONFIG = literal_column("'english'::regconfig")


def search_chunks(
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


def request_reprocess(session: Session, document: Document) -> Document:
    """Put a document back in the queue to be parsed again.

    Allowed in every status except a live processing. A document that has
    been processing for longer than STALE_PROCESSING was abandoned, most
    likely by a server restart, and may be reprocessed too.
    """
    recently_claimed = datetime.now(UTC) - document.updated_at < STALE_PROCESSING
    if document.status == "processing" and recently_claimed:
        raise StillProcessing("This document is being processed right now.")
    document.status = "uploaded"
    document.error = None
    session.commit()
    return document


def delete_document(session: Session, document: Document) -> None:
    """Remove a document, its pages and its file.

    The pages go with the row, through ON DELETE CASCADE. The file goes only
    after the commit, so a failed delete never leaves a row without its file.
    """
    environment_id, document_id = document.environment_id, document.id
    session.delete(document)
    session.commit()
    storage.delete_document_file(environment_id, document_id)
