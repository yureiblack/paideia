"""Tests for citations and source previews in app/services/sources.py.

Purpose: a citation names exactly where its passage came from, down to the
version of the file; a preview's highlights rebuild the cited passage exactly,
whether it sits inside one page, runs across several, or shares a page with
the next passage; and a passage that no longer exists has no preview.
"""

import asyncio
import hashlib
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import storage
from app.models import Document, DocumentChunk, Environment
from app.parsing import PARAGRAPH_BREAK
from app.schemas import EnvironmentCreate
from app.services import documents as document_service
from app.services import environments as environment_service
from app.services import sources
from tests import pdfs
from tests.fakes import FakeEmbedder
from tests.parsed import H, P, Returns, document, words

LECTURE = document(
    [H("Scheduling"), P("Round robin gives every task a time quantum.")],
    [H("Paging"), P("Paging maps pages to frames.")],
    [H("Deadlock"), P("Four conditions cause a deadlock.")],
)
FILE = pdfs.pdf("placeholder")


def environment(session: Session, name: str = "Operating Systems") -> Environment:
    return environment_service.create_environment(session, EnvironmentCreate(name=name))


def processed(
    session, session_factory, parsed=LECTURE, env=None, data=FILE
) -> Document:
    async def chunks():
        yield data

    staged = asyncio.run(storage.stage_upload(chunks(), max_bytes=10_000_000))
    document_id = document_service.create_document(
        session, env or environment(session), staged, "lecture.pdf"
    ).id
    document_service.process_document(
        session_factory, document_id, Returns(parsed), FakeEmbedder()
    )
    session.expire_all()
    return session.get(Document, document_id)


def chunks_of(session: Session, document: Document) -> list[DocumentChunk]:
    query = select(DocumentChunk).where(DocumentChunk.document_id == document.id)
    return list(session.scalars(query.order_by(DocumentChunk.ordinal)))


def test_a_citation_names_the_file_version_pages_and_passage(
    session: Session, session_factory
):
    env = environment(session)
    lecture = processed(session, session_factory, env=env)
    deadlock = next(c for c in chunks_of(session, lecture) if c.heading == "Deadlock")

    citation = sources.cite(deadlock, lecture)

    assert citation.environment_id == env.id
    assert citation.document_id == lecture.id
    # The version is the fingerprint of the exact file that was uploaded.
    assert citation.document_version == hashlib.sha256(FILE).hexdigest()
    assert citation.filename == "lecture.pdf"
    assert citation.chunk_id == deadlock.id
    assert (citation.page_start, citation.page_end) == (3, 3)
    assert citation.heading == "Deadlock"
    assert citation.excerpt == "Deadlock\n\nFour conditions cause a deadlock."


def test_citing_several_chunks_keeps_their_order_across_documents(
    session: Session, session_factory
):
    env = environment(session)
    first = processed(session, session_factory, env=env)
    second = processed(
        session,
        session_factory,
        document([P("Sockets carry bytes.")]),
        env,
        data=pdfs.pdf("another file"),
    )
    # Interleaved, so grouping by document would change the order.
    one, _, three = chunks_of(session, first)
    picked = [three, chunks_of(session, second)[0], one]

    citations = sources.cite_all(session, picked)

    assert [c.chunk_id for c in citations] == [c.id for c in picked]
    assert [c.document_id for c in citations] == [c.document_id for c in picked]
    assert sources.cite_all(session, []) == []


def flowing_document(seed: int):
    """Pages of plain paragraphs and no headings, so passages run across page
    breaks, with an empty page in the middle."""
    pages = [
        [P(words((p * 7 + n * 13 + seed) % 500 + 60, f"t{p}{n}")) for n in range(2)]
        for p in range(7)
    ]
    pages.insert(3, [])
    return document(*pages)


@pytest.mark.parametrize("seed", range(5))
def test_a_preview_highlights_exactly_the_cited_passage(
    session: Session, session_factory, seed: int
):
    lecture = processed(session, session_factory, flowing_document(seed))
    chunks = chunks_of(session, lecture)
    # The cases worth checking are really there.
    assert any(c.page_start != c.page_end for c in chunks)
    assert any(c.page_start < 4 < c.page_end for c in chunks)  # across the empty one

    for chunk in chunks:
        found = sources.preview(session, chunk.id)

        assert found.citation == sources.cite(chunk, lecture)
        numbers = [page.page_number for page in found.pages]
        assert numbers == [
            n for n in range(chunk.page_start, chunk.page_end + 1) if n != 4
        ]
        assert found.pages[0].highlight_start == chunk.char_start
        assert found.pages[-1].highlight_end == chunk.char_end
        for middle in found.pages[1:-1]:
            assert (middle.highlight_start, middle.highlight_end) == (
                0,
                len(middle.content),
            )
        highlighted = PARAGRAPH_BREAK.join(
            page.content[page.highlight_start : page.highlight_end]
            for page in found.pages
        )
        assert highlighted == found.citation.excerpt


def test_a_passage_starting_part_way_down_a_page_runs_on_correctly(
    session: Session, session_factory
):
    # The first passage fills most of page 1. The second starts after it, on
    # the same page, runs through all of page 2 and ends on page 3.
    lecture = processed(
        session,
        session_factory,
        document(
            [P(words(850, "aa")), P(words(300, "bb"))],
            [P(words(300, "cc"))],
            [P(words(300, "dd"))],
        ),
    )
    first, second = chunks_of(session, lecture)[:2]
    assert (first.page_start, first.page_end) == (1, 1)
    assert (second.page_start, second.page_end) == (1, 3)
    assert second.char_start > 0

    one = sources.preview(session, first.id).pages
    page_1, page_2, page_3 = sources.preview(session, second.id).pages

    # Page 1 is shared: each passage highlights its own part of it.
    assert one[0].highlight_end <= page_1.highlight_start == second.char_start
    assert page_1.highlight_end == len(page_1.content)
    assert (page_2.highlight_start, page_2.highlight_end) == (0, len(page_2.content))
    assert (page_3.highlight_start, page_3.highlight_end) == (0, second.char_end)
    assert PARAGRAPH_BREAK.join(
        page.content[page.highlight_start : page.highlight_end]
        for page in (page_1, page_2, page_3)
    ) == (second.content)


def test_a_passage_that_no_longer_exists_has_no_preview(
    session: Session, session_factory
):
    lecture = processed(session, session_factory)
    chunk_id = chunks_of(session, lecture)[0].id
    assert sources.preview(session, chunk_id) is not None

    document_service.delete_document(session, lecture)

    assert sources.preview(session, chunk_id) is None
    assert sources.preview(session, uuid.uuid4()) is None
