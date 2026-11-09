"""Tests for the environment's summary in app/services/environment_summaries.py.

Purpose: with a stand-in model, that the summary is derived state. It is
built from the documents' summaries, citations carried through; rebuilt only
when they change, the old one kept; it waits for documents still on their
way; documents that could not be summarized are left out with the reason; a
deletion rebuilds it; large environments are summarized in groups; and
nothing is written for material that changed while it waited.
"""

import asyncio
import hashlib
import itertools
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app import storage
from app.llm import ONE_AT_A_TIME
from app.models import Document, Environment, GeneratedArtifact
from app.schemas import EnvironmentCreate
from app.services import documents as document_service
from app.services import environment_summaries as env_summaries
from app.services import environments as environment_service
from app.services import summaries
from tests import pdfs
from tests.fakes import FailingProvider, FakeEmbedder, MockProvider, allowed_numbers
from tests.parsed import H, P, Returns, document

SCHEDULING = document(
    [H("Round robin"), P("Round robin gives every task a time quantum.")],
    [H("Shortest job first"), P("Shortest job first runs the shortest burst.")],
)
MEMORY = document(
    [H("Paging"), P("Paging maps pages to frames.")],
    [H("TLB"), P("The TLB caches page translations.")],
)
STORAGE = document(
    [H("Journaling"), P("A journal records changes before applying them.")]
)
ADDED = datetime(2026, 1, 1, tzinfo=UTC)
_ORDER = itertools.count()


def environment(session: Session) -> Environment:
    return environment_service.create_environment(
        session, EnvironmentCreate(name="Operating Systems")
    )


def add(session, session_factory, env, name, parsed, read=True) -> Document:
    async def chunks():
        yield pdfs.pdf(name)  # a different file per name

    staged = asyncio.run(storage.stage_upload(chunks(), max_bytes=10_000_000))
    doc = document_service.create_document(session, env, staged, name)
    # Documents are taken in the order they were added. Postgres's now() is
    # frozen for the whole test's transaction, so give each its own time.
    doc.created_at = ADDED + timedelta(minutes=next(_ORDER))
    session.commit()
    if read:
        document_service.process_document(
            session_factory, doc.id, Returns(parsed), FakeEmbedder()
        )
        session.expire_all()
    return session.get(Document, doc.id)


def summarized(session, session_factory, doc, llm) -> GeneratedArtifact:
    artifact, write_now = summaries.request_summary(session, doc, llm)
    if write_now:
        summaries.write_summary(session_factory, artifact.id, llm)
    session.expire_all()
    return session.get(GeneratedArtifact, artifact.id)


def course(session, session_factory, llm, *parts) -> tuple[Environment, list]:
    """An environment with these (name, parsed) documents, each summarized."""
    env = environment(session)
    docs = []
    for name, parsed in parts:
        doc = add(session, session_factory, env, name, parsed)
        summarized(session, session_factory, doc, llm)
        docs.append(doc)
    return env, docs


def refresh(session, session_factory, env, llm):
    env_summaries.refresh_environment_summary(session_factory, env.id, llm)
    session.expire_all()
    return env_summaries.state(session, env, llm)


def environment_calls(llm) -> list:
    return [(p, s) for p, s in llm.calls if p.name == "environment_summary"]


def test_built_from_the_document_summaries_with_their_citations(
    session: Session, session_factory
):
    llm = MockProvider()
    env, (sched, mem) = course(
        session, session_factory, llm, ("a.pdf", SCHEDULING), ("b.pdf", MEMORY)
    )

    state = refresh(session, session_factory, env, llm)

    [(prompt, schema)] = environment_calls(llm)
    assert prompt.id == "environment_summary/v1"
    assert "Subject: Operating Systems" in prompt.user
    assert prompt.user.index("Document: a.pdf") < prompt.user.index("Document: b.pdf")
    # Each document summary cited two passages (one per key point, as the
    # stand-in answers): numbered 1 to 4 across the environment.
    assert allowed_numbers(schema) == [1, 2, 3, 4]
    assert state.state == "up_to_date"
    summary = state.summary
    assert summary.current is True
    assert [(d.filename, d.document_version) for d in summary.based_on] == [
        ("a.pdf", sched.sha256),
        ("b.pdf", mem.sha256),
    ]
    doc_summary = summaries.current_summary(session, sched, llm)
    assert summary.based_on[0].summary_id == doc_summary.id
    stored = doc_summary.content["key_points"][0]["citations"][0]
    assert summary.key_points[0].citations[0].model_dump(mode="json") == stored


def test_a_passage_cited_by_several_points_is_numbered_once(
    session: Session, session_factory
):
    def both_points_cite_the_first_passage(prompt, schema):
        if prompt.name == "environment_summary":
            from tests.fakes import simple_answer

            return simple_answer(prompt, schema)
        return {
            "overview": "Two passages.",
            "key_points": [
                {"point": "One.", "sources": [1]},
                {"point": "Two.", "sources": [1, 2]},
            ],
        }

    llm = MockProvider(answer=both_points_cite_the_first_passage)
    env, _ = course(session, session_factory, llm, ("a.pdf", SCHEDULING))

    refresh(session, session_factory, env, llm)

    [(prompt, schema)] = environment_calls(llm)
    assert allowed_numbers(schema) == [1, 2]
    assert "- One. [1]" in prompt.user
    assert "- Two. [1, 2]" in prompt.user


def test_nothing_changed_nothing_is_rebuilt(session: Session, session_factory):
    llm = MockProvider()
    env, (sched,) = course(session, session_factory, llm, ("a.pdf", SCHEDULING))
    first = refresh(session, session_factory, env, llm)

    # Reading the same document again changes nothing it was built from.
    document_service.request_reprocess(session, sched)
    document_service.process_document(
        session_factory, sched.id, Returns(SCHEDULING), FakeEmbedder()
    )
    session.expire_all()
    summarized(session, session_factory, session.get(Document, sched.id), llm)
    again = refresh(session, session_factory, env, llm)

    assert len(environment_calls(llm)) == 1
    assert again.summary.id == first.summary.id


def test_a_new_document_rebuilds_it_and_the_old_one_is_kept(
    session: Session, session_factory
):
    llm = MockProvider()
    env, _ = course(session, session_factory, llm, ("a.pdf", SCHEDULING))
    first = refresh(session, session_factory, env, llm)
    summarized(
        session,
        session_factory,
        add(session, session_factory, env, "b.pdf", MEMORY),
        llm,
    )

    second = refresh(session, session_factory, env, llm)

    assert second.summary.id != first.summary.id
    assert [d.filename for d in second.summary.based_on] == ["a.pdf", "b.pdf"]
    assert second.earlier_versions == 1
    history = env_summaries.history(session, env)
    assert {a.id for a in history} == {first.summary.id, second.summary.id}


def test_it_waits_while_documents_are_being_read_or_summarized(
    session: Session, session_factory
):
    llm = MockProvider()
    env, _ = course(session, session_factory, llm, ("a.pdf", SCHEDULING))
    unread = add(session, session_factory, env, "b.pdf", MEMORY, read=False)

    assert refresh(session, session_factory, env, llm).state == "waiting"

    document_service.process_document(
        session_factory, unread.id, Returns(MEMORY), FakeEmbedder()
    )
    session.expire_all()
    pending, _ = summaries.request_summary(
        session, session.get(Document, unread.id), llm
    )
    waiting = refresh(session, session_factory, env, llm)
    assert (waiting.state, waiting.waiting_for) == ("waiting", 1)
    assert environment_calls(llm) == []

    summaries.write_summary(session_factory, pending.id, llm)
    done = refresh(session, session_factory, env, llm)
    assert done.state == "up_to_date"
    assert len(done.summary.based_on) == 2
    assert len(environment_calls(llm)) == 1


def test_documents_without_a_ready_summary_are_left_out_with_the_reason(
    session: Session, session_factory
):
    llm = MockProvider()
    env, _ = course(session, session_factory, llm, ("a.pdf", SCHEDULING))
    failed = add(session, session_factory, env, "b.pdf", MEMORY)
    summarized(session, session_factory, failed, FailingProvider())
    add(session, session_factory, env, "c.pdf", STORAGE)  # read, never summarized

    state = refresh(session, session_factory, env, llm)

    assert state.state == "up_to_date"
    assert [d.filename for d in state.summary.based_on] == ["a.pdf"]
    assert [(n.filename, n.reason) for n in state.not_included] == [
        ("b.pdf", "Its summary failed: Could not reach Ollama. Is it running?"),
        ("c.pdf", "It has not been summarized yet."),
    ]


def test_deleting_a_document_rebuilds_it_from_what_is_left(
    session: Session, session_factory
):
    llm = MockProvider()
    env, (_, mem) = course(
        session, session_factory, llm, ("a.pdf", SCHEDULING), ("b.pdf", MEMORY)
    )
    before = refresh(session, session_factory, env, llm)

    document_service.delete_document(session, mem)
    after = refresh(session, session_factory, env, llm)

    assert [d.filename for d in after.summary.based_on] == ["a.pdf"]
    # The earlier summary still says what it was built from, deleted
    # document included.
    old = next(
        a for a in env_summaries.history(session, env) if a.id == before.summary.id
    )
    assert [d["filename"] for d in old.metadata_json["based_on"]] == ["a.pdf", "b.pdf"]


def test_with_nothing_summarized_there_is_no_summary(session: Session, session_factory):
    llm = MockProvider()
    env = environment(session)
    assert refresh(session, session_factory, env, llm).state == "none"

    failed = add(session, session_factory, env, "a.pdf", SCHEDULING)
    summarized(session, session_factory, failed, FailingProvider())
    state = refresh(session, session_factory, env, llm)

    assert (state.state, state.summary) == ("none", None)
    assert environment_calls(llm) == []


def test_a_large_environment_is_summarized_in_groups(
    session: Session, session_factory, monkeypatch
):
    llm = MockProvider()
    env, _ = course(
        session,
        session_factory,
        llm,
        ("a.pdf", SCHEDULING),
        ("b.pdf", MEMORY),
        ("c.pdf", STORAGE),
    )
    monkeypatch.setattr(env_summaries, "NOTES_TOKENS", 1)  # each document alone

    refresh(session, session_factory, env, llm)

    *groups, (final, final_schema) = environment_calls(llm)
    assert len(groups) == 3
    assert "Document: b.pdf" in groups[1][0].user
    assert "Document: a.pdf" not in groups[1][0].user
    assert "Part 1: Document: a.pdf" in final.user
    assert "Part 3: Document: c.pdf" in final.user
    cited_by_groups = sorted({n for _, s in groups for n in allowed_numbers(s)})
    assert set(allowed_numbers(final_schema)) <= set(cited_by_groups)


def test_a_summary_of_material_that_changed_while_it_waited_is_not_written(
    session: Session, session_factory
):
    llm = MockProvider()
    env, _ = course(session, session_factory, llm, ("a.pdf", SCHEDULING))
    waiting, write_now = env_summaries.request_environment_summary(session, env, llm)
    assert write_now
    summarized(
        session,
        session_factory,
        add(session, session_factory, env, "b.pdf", MEMORY),
        llm,
    )

    env_summaries.write_environment_summary(session_factory, waiting.id, llm)

    session.expire_all()
    stale = session.get(GeneratedArtifact, waiting.id)
    assert (stale.status, stale.error) == (
        "failed",
        "The material changed before this summary was written.",
    )
    assert environment_calls(llm) == []


def test_a_failed_summary_is_tried_again_in_the_same_row(
    session: Session, session_factory
):
    llm = MockProvider()
    env, _ = course(session, session_factory, llm, ("a.pdf", SCHEDULING))
    failing = FailingProvider()  # same model name, so the same summary

    failed = refresh(session, session_factory, env, failing)
    assert (failed.state, failed.error) == (
        "failed",
        "Could not reach Ollama. Is it running?",
    )
    retried = refresh(session, session_factory, env, llm)

    assert retried.state == "up_to_date"
    assert len(env_summaries.history(session, env)) == 1


def test_it_is_written_one_at_a_time(session: Session, session_factory):
    held = []

    def answer(prompt, schema):
        if prompt.name == "environment_summary":
            held.append(ONE_AT_A_TIME.locked())
        from tests.fakes import simple_answer

        return simple_answer(prompt, schema)

    llm = MockProvider(answer=answer)
    env, _ = course(session, session_factory, llm, ("a.pdf", SCHEDULING))
    refresh(session, session_factory, env, llm)

    assert held == [True]


def test_source_version_names_the_documents_and_their_exact_summaries(
    session: Session, session_factory
):
    llm = MockProvider()
    env, (sched,) = course(session, session_factory, llm, ("a.pdf", SCHEDULING))

    inputs = env_summaries.gather(session, env, llm)

    doc_summary = summaries.current_summary(session, sched, llm)
    expected = hashlib.sha256(f"{sched.id}:{doc_summary.id}".encode()).hexdigest()
    assert inputs.source_version == expected
