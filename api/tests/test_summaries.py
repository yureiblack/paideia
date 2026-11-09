"""Tests for document summaries in app/services/summaries.py.

Purpose: with a stand-in model, the plumbing around it: passages numbered in
reading order, answers that may only cite numbers they were given, those
numbers turned back into the passages' citations, long documents read in
sections and combined, and refusals that come before any model call.
"""

import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import storage
from app.models import Document, DocumentChunk, Environment
from app.schemas import EnvironmentCreate
from app.services import documents as document_service
from app.services import environments as environment_service
from app.services import sources, summaries
from tests import pdfs
from tests.fakes import FakeEmbedder, MockProvider, allowed_numbers
from tests.parsed import H, P, Returns, document, words

LECTURE = document(
    [H("Scheduling"), P("Round robin gives every task a time quantum.")],
    [H("Paging"), P("Paging maps pages to frames.")],
    [H("Deadlock"), P("Four conditions cause a deadlock.")],
)


def environment(session: Session) -> Environment:
    return environment_service.create_environment(
        session, EnvironmentCreate(name="Operating Systems")
    )


def uploaded(session: Session) -> Document:
    async def chunks():
        yield pdfs.pdf("placeholder")

    staged = asyncio.run(storage.stage_upload(chunks(), max_bytes=10_000_000))
    return document_service.create_document(
        session, environment(session), staged, "Lecture 4.pdf"
    )


def processed(session, session_factory, parsed=LECTURE) -> Document:
    document_id = uploaded(session).id
    document_service.process_document(
        session_factory, document_id, Returns(parsed), FakeEmbedder()
    )
    session.expire_all()
    return session.get(Document, document_id)


def chunks_of(session: Session, doc: Document) -> list[DocumentChunk]:
    query = select(DocumentChunk).where(DocumentChunk.document_id == doc.id)
    return list(session.scalars(query.order_by(DocumentChunk.ordinal)))


def citing(*points: list[int]):
    """An answer whose key points cite these passage numbers."""
    return lambda prompt, schema: {
        "overview": "Three topics.",
        "key_points": [
            {"point": f"Point {i}.", "sources": s} for i, s in enumerate(points)
        ],
    }


def test_passages_are_numbered_in_reading_order_and_cited_back(
    session: Session, session_factory
):
    lecture = processed(session, session_factory)
    llm = MockProvider(answer=citing([3], [1, 2], [2]))

    summary = summaries.summarize_document(session, lecture, llm)

    [(prompt, schema)] = llm.calls
    assert prompt.id == "document_summary/v1"
    assert "Document: Lecture 4.pdf" in prompt.user
    first, second, third = (prompt.user.index(f"[{n}] ") for n in (1, 2, 3))
    assert first < second < third
    assert "[1] Scheduling\n\nRound robin" in prompt.user
    assert allowed_numbers(schema) == [1, 2, 3]

    chunks = chunks_of(session, lecture)
    assert [[c.chunk_id for c in p.citations] for p in summary.key_points] == [
        [chunks[2].id],
        [chunks[0].id, chunks[1].id],
        [chunks[1].id],
    ]
    assert summary.key_points[1].citations[0] == sources.cite(chunks[0], lecture)
    assert summary.overview == "Three topics."
    assert (summary.model, summary.prompt_versions, summary.sections) == (
        "mock-llm",
        ["document_summary/v1"],
        1,
    )
    assert summary.seconds == 1.5


def test_a_passage_cited_twice_by_one_point_is_listed_once(
    session: Session, session_factory
):
    lecture = processed(session, session_factory)

    summary = summaries.summarize_document(
        session, lecture, MockProvider(answer=citing([2, 2, 1], [3], [1]))
    )

    assert [c.page_start for c in summary.key_points[0].citations] == [2, 1]


def test_a_long_document_is_read_in_sections_then_combined(
    session: Session, session_factory, monkeypatch
):
    # Six passages of about 1000 characters, sections of about 600 tokens:
    # two passages fit in each section, so three sections.
    monkeypatch.setattr(summaries, "SECTION_TOKENS", 600)
    pages = [[H(f"Topic {n}"), P(words(950, f"w{n}"))] for n in range(6)]
    lecture = processed(session, session_factory, document(*pages))
    llm = MockProvider()

    summary = summaries.summarize_document(session, lecture, llm)

    *section_calls, (combine, combine_schema) = llm.calls
    assert [p.id for p, _ in section_calls] == ["document_summary/v1"] * 3
    # Each section keeps the document-wide numbers and may cite only its own.
    assert [allowed_numbers(s) for _, s in section_calls] == [[1, 2], [3, 4], [5, 6]]
    assert "[3] Topic 2" in section_calls[1][0].user
    assert "[1] " not in section_calls[1][0].user
    # The combining call sees every section's notes and may cite only the
    # numbers those notes cited.
    assert combine.id == "combine_summaries/v1"
    for n in (1, 2, 3):
        assert f"Section {n} (passages {2 * n - 1} to {2 * n})" in combine.user
    assert allowed_numbers(combine_schema) == [1, 2, 3, 4, 5, 6]
    assert summary.sections == 3
    assert summary.prompt_versions == ["document_summary/v1", "combine_summaries/v1"]
    assert summary.seconds == 4 * 1.5


def test_the_combining_call_may_cite_only_what_the_notes_cited(
    session: Session, session_factory, monkeypatch
):
    monkeypatch.setattr(summaries, "SECTION_TOKENS", 600)
    pages = [[H(f"Topic {n}"), P(words(950, f"w{n}"))] for n in range(6)]
    lecture = processed(session, session_factory, document(*pages))

    def first_of_each_section(prompt, schema):
        n = allowed_numbers(schema)[0]
        least = schema.model_json_schema()["properties"]["key_points"]["minItems"]
        return {
            "overview": "Notes.",
            "key_points": [{"point": "A point.", "sources": [n]}] * least,
        }

    llm = MockProvider(answer=first_of_each_section)
    summaries.summarize_document(session, lecture, llm)

    _, combine_schema = llm.calls[-1]
    assert allowed_numbers(combine_schema) == [1, 3, 5]


def test_a_document_too_long_is_refused_before_any_model_call(
    session: Session, session_factory, monkeypatch
):
    # Each of the lecture's three passages becomes a section of its own, one
    # more than allowed.
    monkeypatch.setattr(summaries, "SECTION_TOKENS", 20)
    monkeypatch.setattr(summaries, "MAX_SECTIONS", 2)
    lecture = processed(session, session_factory)
    llm = MockProvider()

    with pytest.raises(summaries.CannotSummarize, match="too long to summarize"):
        summaries.summarize_document(session, lecture, llm)
    assert llm.calls == []


def test_a_document_not_read_yet_is_refused(session: Session):
    llm = MockProvider()

    with pytest.raises(summaries.NotReadyToSummarize):
        summaries.summarize_document(session, uploaded(session), llm)
    assert llm.calls == []


def test_a_document_without_text_is_refused(session: Session, session_factory):
    blank = processed(session, session_factory, document([], []))

    with pytest.raises(summaries.CannotSummarize, match="no text"):
        summaries.summarize_document(session, blank, MockProvider())


def test_the_answer_schema_allows_only_the_given_numbers_and_bounds_every_list():
    consecutive = summaries.answer_schema([4, 5, 6]).model_json_schema()
    scattered = summaries.answer_schema([1, 3, 5]).model_json_schema()

    sources_of = lambda schema: schema["$defs"]["KeyPoint"]["properties"]["sources"]
    assert sources_of(consecutive)["items"] == {
        "minimum": 4,
        "maximum": 6,
        "type": "integer",
    }
    assert sources_of(scattered)["items"]["enum"] == [1, 3, 5]
    # Without limits, a constrained model can keep writing until its context
    # is full (decision record 08).
    assert sources_of(consecutive)["maxItems"] == summaries.MAX_SOURCES
    assert consecutive["properties"]["key_points"]["maxItems"] == summaries.MAX_POINTS
    assert consecutive["properties"]["key_points"]["minItems"] == 3
    # A document of one passage is not asked for three points about it.
    one = summaries.answer_schema([1]).model_json_schema()
    assert one["properties"]["key_points"]["minItems"] == 1


def test_an_answer_citing_a_number_it_was_not_given_is_rejected():
    schema = summaries.answer_schema([1, 2])

    with pytest.raises(ValueError):
        schema.model_validate(
            {"overview": "x", "key_points": [{"point": "y", "sources": [3]}]}
        )
