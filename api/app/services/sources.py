"""Citations: where a piece of evidence came from, and how to show it.

Purpose
-------
Search results now, and summaries and answers later, all cite their sources
the same way. A Citation names the environment, the document and the exact
version of its file, the chunk, its pages and heading, and the passage itself.
This module is the only place citations and source previews are built, so
every part of the app cites identically (decision record 07).

The version of a document is the SHA-256 of its file. A document's file never
changes; when its text changes on reprocessing, the changed chunks get new
ids, because a chunk id is derived from its text. A document version and a
chunk id together therefore pin one exact passage.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Document, DocumentChunk, DocumentPage
from app.schemas import Citation, SourcePage, SourcePreview


def with_heading(chunk: DocumentChunk) -> str:
    """A chunk's text with its section heading in front, unless the text
    already starts with it, so a passage from the middle of a section keeps
    its context when a model reads it on its own."""
    if chunk.heading and not chunk.content.startswith(chunk.heading):
        return f"{chunk.heading}\n\n{chunk.content}"
    return chunk.content


def cite(chunk: DocumentChunk, document: Document) -> Citation:
    """The citation for one chunk of a document."""
    return Citation(
        environment_id=document.environment_id,
        document_id=document.id,
        document_version=document.sha256,
        filename=document.filename,
        chunk_id=chunk.id,
        page_start=chunk.page_start,
        page_end=chunk.page_end,
        heading=chunk.heading,
        excerpt=chunk.content,
    )


def cite_all(session: Session, chunks: Sequence[DocumentChunk]) -> list[Citation]:
    """Citations for several chunks, in order, reading their documents in one
    query rather than one each."""
    ids = {chunk.document_id for chunk in chunks}
    documents = {
        document.id: document
        for document in session.scalars(select(Document).where(Document.id.in_(ids)))
    }
    return [cite(chunk, documents[chunk.document_id]) for chunk in chunks]


def preview(session: Session, chunk_id: uuid.UUID) -> SourcePreview | None:
    """A chunk's citation and every page it touches, each with the range the
    passage covers; None if the chunk no longer exists.

    A passage can start part-way through one page and end part-way through a
    later one, so the first page is highlighted from the chunk's start, the
    last up to its end, and any page between them entirely. A page without
    text is left out, as it is when the chunk's text is assembled. Joined with
    the blank line that separates pages, the highlighted parts are exactly
    the excerpt.
    """
    chunk = session.get(DocumentChunk, chunk_id)
    if chunk is None:
        return None
    document = session.get(Document, chunk.document_id)
    stored = session.scalars(
        select(DocumentPage)
        .where(
            DocumentPage.document_id == chunk.document_id,
            DocumentPage.page_number.between(chunk.page_start, chunk.page_end),
        )
        .order_by(DocumentPage.page_number)
    )
    pages = []
    for page in stored:
        if not page.content:
            continue
        first, last = (
            page.page_number == chunk.page_start,
            page.page_number == chunk.page_end,
        )
        pages.append(
            SourcePage(
                page_number=page.page_number,
                content=page.content,
                highlight_start=chunk.char_start if first else 0,
                highlight_end=chunk.char_end if last else len(page.content),
            )
        )
    return SourcePreview(citation=cite(chunk, document), pages=pages)
