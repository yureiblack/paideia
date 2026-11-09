"""Tests for document summaries in app/services/summaries.py.

Purpose: with a stand-in model, everything around it. Writing: passages
numbered in reading order, answers that may only cite numbers they were
given, numbers turned back into citations, long documents read in sections
and combined. Keeping: one summary per document text, model and prompt, so
asking twice writes once; new text or a new model writes a new one and keeps
the old; failures retried in the same row; abandoned work retried; summaries
written one at a time; nothing written for a document that has changed.
"""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app import storage
from app.models import Document, DocumentChunk, Environment, GeneratedArtifact
from app.schemas import EnvironmentCreate
from app.services import documents as document_service
from app.services import environments as environment_service
from app.services import sources, summaries
from tests import pdfs
from tests.fakes import FailingProvider, FakeEmbedder, MockProvider, allowed_numbers
from tests.parsed import H, P, Returns, document, words

LECTURE = document(
    [H("Scheduling"), P("Round robin gives every task a time quantum.")],
    [H("Paging"), P("Paging maps pages to frames.")],
    [H("Deadlock"), P("Four conditions cause a deadlock.")],
)
SIX_LONG_TOPICS = document(
    *[[H(f"Topic {n}"), P(words(950, f"w{n}"))] for n in range(6)]
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


def process(session, session_factory, document_id, parsed) -> Document:
    document_service.process_document(
        session_factory, document_id, Returns(parsed), FakeEmbedder()
    )
    session.expire_all()
    return session.get(Document, document_id)


def processed(session, session_factory, parsed=LECTURE) -> Document:
    return process(session, session_factory, uploaded(session).id, parsed)


def reprocessed(session, session_factory, doc: Document, parsed) -> Document:
    document_service.request_reprocess(session, doc)
    return process(session, session_factory, doc.id, parsed)


def summarize(session, session_factory, doc: Document, llm) -> GeneratedArtifact:
    """Ask for the document's summary and write it if it needs writing, as the
    background task does."""
    artifact, write_now = summaries.request_summary(session, doc, llm)
    if write_now:
        summaries.write_summary(session_factory, artifact.id, llm)
    session.expire_all()
    return session.get(GeneratedArtifact, artifact.id)


def written_earlier(session: Session, artifact: GeneratedArtifact) -> None:
    """Date a summary a minute back. created_at defaults to Postgres's now(),
    which is frozen for a whole transaction, and each test is one transaction,
    so summaries written in one test would otherwise share a creation time."""
    session.execute(
        update(GeneratedArtifact)
        .where(GeneratedArtifact.id == artifact.id)
        .values(created_at=datetime.now(UTC) - timedelta(minutes=1))
    )


def chunks_of(session: Session, doc: Document) -> list[DocumentChunk]:
    query = select(DocumentChunk).where(DocumentChunk.document_id == doc.id)
    return list(session.scalars(query.order_by(DocumentChunk.ordinal)))


def rows(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(GeneratedArtifact))


def citing(*points: list[int]):
    """An answer whose key points cite these passage numbers."""
    return lambda prompt, schema: {
        "overview": "Three topics.",
        "key_points": [
            {"point": f"Point {i}.", "sources": s} for i, s in enumerate(points)
        ],
    }


# --- writing --------------------------------------------------------------------


def test_passages_are_numbered_in_reading_order_and_cited_back(
    session: Session, session_factory
):
    lecture = processed(session, session_factory)
    llm = MockProvider(answer=citing([3], [1, 2], [2]))

    artifact = summarize(session, session_factory, lecture, llm)

    [(prompt, schema)] = llm.calls
    assert prompt.id == "document_summary/v1"
    assert "Document: Lecture 4.pdf" in prompt.user
    first, second, third = (prompt.user.index(f"[{n}] ") for n in (1, 2, 3))
    assert first < second < third
    assert "[1] Scheduling\n\nRound robin" in prompt.user
    assert allowed_numbers(schema) == [1, 2, 3]

    chunks = chunks_of(session, lecture)
    summary = summaries.to_read(artifact, current=True)
    assert summary.status == "ready"
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
    llm = MockProvider(answer=citing([2, 2, 1], [3], [1]))

    artifact = summarize(session, session_factory, lecture, llm)

    pages = [c["page_start"] for c in artifact.content["key_points"][0]["citations"]]
    assert pages == [2, 1]


def test_a_long_document_is_read_in_sections_then_combined(
    session: Session, session_factory, monkeypatch
):
    # Six passages of about 1000 characters, sections of about 600 tokens:
    # two passages fit in each section, so three sections.
    monkeypatch.setattr(summaries, "SECTION_TOKENS", 600)
    lecture = processed(session, session_factory, SIX_LONG_TOPICS)
    llm = MockProvider()

    artifact = summarize(session, session_factory, lecture, llm)

    *section_calls, (combine, combine_schema) = llm.calls
    assert [p.id for p, _ in section_calls] == ["document_summary/v1"] * 3
    # Each section keeps the document-wide numbers and may cite only its own.
    assert [allowed_numbers(s) for _, s in section_calls] == [[1, 2], [3, 4], [5, 6]]
    assert "[3] Topic 2" in section_calls[1][0].user
    assert "[1] " not in section_calls[1][0].user
    # The combining call sees every section's notes.
    assert combine.id == "combine_summaries/v1"
    for n in (1, 2, 3):
        assert f"Section {n} (passages {2 * n - 1} to {2 * n})" in combine.user
    assert allowed_numbers(combine_schema) == [1, 2, 3, 4, 5, 6]
    summary = summaries.to_read(artifact, current=True)
    assert summary.sections == 3
    assert summary.prompt_versions == ["document_summary/v1", "combine_summaries/v1"]
    assert summary.seconds == 4 * 1.5


def test_the_combining_call_may_cite_only_what_the_notes_cited(
    session: Session, session_factory, monkeypatch
):
    monkeypatch.setattr(summaries, "SECTION_TOKENS", 600)
    lecture = processed(session, session_factory, SIX_LONG_TOPICS)

    def first_of_each_section(prompt, schema):
        n = allowed_numbers(schema)[0]
        least = schema.model_json_schema()["properties"]["key_points"]["minItems"]
        return {
            "overview": "Notes.",
            "key_points": [{"point": "A point.", "sources": [n]}] * least,
        }

    llm = MockProvider(answer=first_of_each_section)
    summarize(session, session_factory, lecture, llm)

    _, combine_schema = llm.calls[-1]
    assert allowed_numbers(combine_schema) == [1, 3, 5]


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


def test_summaries_are_written_one_at_a_time(session: Session, session_factory):
    lecture = processed(session, session_factory)
    held = []

    def answer(prompt, schema):
        held.append(summaries._ONE_AT_A_TIME.locked())
        return citing([1], [2], [3])(prompt, schema)

    summarize(session, session_factory, lecture, MockProvider(answer=answer))

    assert held == [True]


# --- keeping -----------------------------------------------------------------


def test_asking_twice_writes_once(session: Session, session_factory):
    lecture = processed(session, session_factory)
    llm = MockProvider()
    first = summarize(session, session_factory, lecture, llm)

    again, write_now = summaries.request_summary(session, lecture, llm)

    assert (again.id, write_now) == (first.id, False)
    assert len(llm.calls) == 1
    assert rows(session) == 1


def test_reprocessing_unchanged_text_keeps_the_summary(
    session: Session, session_factory
):
    lecture = processed(session, session_factory)
    llm = MockProvider()
    first = summarize(session, session_factory, lecture, llm)

    lecture = reprocessed(session, session_factory, lecture, LECTURE)
    again, write_now = summaries.request_summary(session, lecture, llm)

    assert (again.id, write_now) == (first.id, False)


def test_new_text_means_a_new_summary_and_the_old_one_is_kept_readable(
    session: Session, session_factory
):
    lecture = processed(session, session_factory)
    llm = MockProvider()
    old = summarize(session, session_factory, lecture, llm)
    old_excerpt = old.content["key_points"][0]["citations"][0]["excerpt"]
    written_earlier(session, old)

    changed = document([H("Threads"), P("Threads share an address space.")])
    lecture = reprocessed(session, session_factory, lecture, changed)
    new = summarize(session, session_factory, lecture, llm)

    assert new.id != old.id
    assert new.source_version != old.source_version
    assert [a.id for a in summaries.history(session, lecture)] == [new.id, old.id]
    assert summaries.current_summary(session, lecture, llm).id == new.id
    # The old summary's passages are gone from the document, but it still
    # reads as it did: its citations were stored in full.
    session.refresh(old)
    assert old.status == "ready"
    assert old.content["key_points"][0]["citations"][0]["excerpt"] == old_excerpt


def test_a_new_model_means_a_new_summary_and_the_old_one_is_kept(
    session: Session, session_factory
):
    lecture = processed(session, session_factory)
    old = summarize(session, session_factory, lecture, MockProvider())

    new = summarize(session, session_factory, lecture, MockProvider(model_name="newer"))

    assert new.id != old.id
    assert (new.model_name, new.source_version) == ("newer", old.source_version)
    assert rows(session) == 2


def test_a_failed_summary_is_tried_again_in_the_same_row(
    session: Session, session_factory
):
    lecture = processed(session, session_factory)
    failed = summarize(session, session_factory, lecture, FailingProvider())
    assert (failed.status, failed.error) == (
        "failed",
        "Could not reach Ollama. Is it running?",
    )

    retried = summarize(session, session_factory, lecture, MockProvider())

    assert retried.id == failed.id
    assert (retried.status, retried.error) == ("ready", None)
    assert rows(session) == 1


def test_a_summary_abandoned_while_generating_can_be_tried_again(
    session: Session, session_factory
):
    lecture = processed(session, session_factory)
    llm = MockProvider()
    artifact, _ = summaries.request_summary(session, lecture, llm)

    def generating_since(ago: timedelta):
        session.execute(
            update(GeneratedArtifact)
            .where(GeneratedArtifact.id == artifact.id)
            .values(status="generating", updated_at=datetime.now(UTC) - ago)
        )
        session.expire_all()

    generating_since(timedelta(minutes=5))
    assert summaries.request_summary(session, lecture, llm)[1] is False

    generating_since(summaries.STALE_GENERATING + timedelta(minutes=1))
    again, write_now = summaries.request_summary(session, lecture, llm)
    assert (again.id, write_now, again.status) == (artifact.id, True, "pending")


def test_a_document_too_long_gets_a_failed_summary_and_no_model_call(
    session: Session, session_factory, monkeypatch
):
    # Each of the lecture's three passages becomes a section of its own, one
    # more than allowed.
    monkeypatch.setattr(summaries, "SECTION_TOKENS", 20)
    monkeypatch.setattr(summaries, "MAX_SECTIONS", 2)
    lecture = processed(session, session_factory)
    llm = MockProvider()

    artifact = summarize(session, session_factory, lecture, llm)
    again, write_now = summaries.request_summary(session, lecture, llm)

    assert artifact.status == "failed"
    assert "too long to summarize" in artifact.error
    assert (again.id, write_now) == (artifact.id, False)
    assert llm.calls == []


def test_a_document_without_text_gets_a_failed_summary(
    session: Session, session_factory
):
    blank = processed(session, session_factory, document([], []))

    artifact = summarize(session, session_factory, blank, MockProvider())

    assert (artifact.status, artifact.error) == (
        "failed",
        "This document has no text to summarize.",
    )


def test_a_document_not_read_yet_is_refused(session: Session):
    with pytest.raises(summaries.NotReadyToSummarize):
        summaries.request_summary(session, uploaded(session), MockProvider())


def test_a_summary_waiting_for_text_that_has_changed_is_not_written(
    session: Session, session_factory
):
    lecture = processed(session, session_factory)
    llm = MockProvider()
    waiting, _ = summaries.request_summary(session, lecture, llm)
    changed = document([H("Threads"), P("Threads share an address space.")])
    reprocessed(session, session_factory, lecture, changed)

    summaries.write_summary(session_factory, waiting.id, llm)

    session.expire_all()
    stale = session.get(GeneratedArtifact, waiting.id)
    assert (stale.status, stale.error) == (
        "failed",
        "The document changed before this summary was written.",
    )
    assert llm.calls == []


def test_a_summary_already_being_written_is_left_alone(
    session: Session, session_factory
):
    lecture = processed(session, session_factory)
    llm = MockProvider()
    artifact, _ = summaries.request_summary(session, lecture, llm)
    session.execute(
        update(GeneratedArtifact)
        .where(GeneratedArtifact.id == artifact.id)
        .values(status="generating")
    )

    summaries.write_summary(session_factory, artifact.id, llm)

    assert llm.calls == []


def test_deleting_a_document_deletes_its_summaries(session: Session, session_factory):
    lecture = processed(session, session_factory)
    summarize(session, session_factory, lecture, MockProvider())

    document_service.delete_document(session, lecture)

    assert rows(session) == 0
