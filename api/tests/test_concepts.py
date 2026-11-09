"""Tests for concept extraction in app/services/concepts.py, with mocked
model responses.

Purpose: the model proposes, the backend validates and persists. Proposals
are numbered passages turned into evidence; malformed or untrustworthy
proposals never reach the concept tables; concepts merge by normalized name
across sections and documents, with stable ids; extracting twice writes
once; new text replaces a document's links; concepts no document mentions
are removed; what a concept shows comes from its best-evidenced document.
"""

import asyncio
import itertools
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import storage
from app.llm import ONE_AT_A_TIME
from app.models import (
    Concept,
    ConceptEvidence,
    Document,
    DocumentChunk,
    DocumentConcept,
    Environment,
    GeneratedArtifact,
)
from app.schemas import EnvironmentCreate
from app.services import concepts, summaries
from app.services import documents as document_service
from app.services import environments as environment_service
from tests import pdfs
from tests.fakes import FakeEmbedder, MockProvider
from tests.parsed import H, P, Returns, document, words

MEMORY = document(
    [H("Paging"), P("Paging maps pages to frames.")],
    [H("TLB"), P("The TLB caches page translations.")],
)
VIRTUAL = document(
    [H("Demand paging"), P("Pages load when first touched.")],
    [H("Paging"), P("Paging divides memory into frames.")],
)
ADDED = datetime(2026, 1, 1, tzinfo=UTC)
_ORDER = itertools.count()


def environment(session: Session) -> Environment:
    return environment_service.create_environment(
        session, EnvironmentCreate(name="Operating Systems")
    )


def add(session, session_factory, env, name, parsed) -> Document:
    async def chunks():
        yield pdfs.pdf(name)

    staged = asyncio.run(storage.stage_upload(chunks(), max_bytes=10_000_000))
    doc = document_service.create_document(session, env, staged, name)
    doc.created_at = ADDED + timedelta(minutes=next(_ORDER))  # frozen now()
    session.commit()
    document_service.process_document(
        session_factory, doc.id, Returns(parsed), FakeEmbedder()
    )
    session.expire_all()
    return session.get(Document, doc.id)


def concept(name, sources, definition=None, aliases=()):
    return {
        "name": name,
        "definition": definition or f"The meaning of {name}.",
        "aliases": list(aliases),
        "sources": list(sources),
    }


def answering(*by_document):
    """A model that answers each extraction with the next scripted list of
    concepts (dicts as above), and anything else simply."""
    scripts = iter(by_document)

    def answer(prompt, schema):
        if prompt.name == "concept_extraction":
            return {"concepts": next(scripts)}
        from tests.fakes import simple_answer

        return simple_answer(prompt, schema)

    return MockProvider(answer=answer)


def extract(session, session_factory, doc, llm) -> GeneratedArtifact:
    artifact, write_now = concepts.request_extraction(session, doc, llm)
    if write_now:
        concepts.write_extraction(session_factory, artifact.id, llm)
    session.expire_all()
    return session.get(GeneratedArtifact, artifact.id)


def chunks_of(session, doc) -> list[DocumentChunk]:
    query = select(DocumentChunk).where(DocumentChunk.document_id == doc.id)
    return list(session.scalars(query.order_by(DocumentChunk.ordinal)))


def by_name(session, env) -> dict[str, Concept]:
    rows = session.scalars(select(Concept).where(Concept.environment_id == env.id))
    return {c.normalized_name: c for c in rows}


def count(session, model) -> int:
    return session.scalar(select(func.count()).select_from(model))


def test_proposals_become_concepts_with_their_passages_as_evidence(
    session: Session, session_factory
):
    env = environment(session)
    memory = add(session, session_factory, env, "memory.pdf", MEMORY)
    llm = answering(
        [concept("Paging", [1]), concept("Translation Lookaside Buffer (TLB)", [2, 1])]
    )

    artifact = extract(session, session_factory, memory, llm)

    [(prompt, schema)] = [
        (p, s) for p, s in llm.calls if p.name == "concept_extraction"
    ]
    assert "[1] Paging\n\nPaging maps pages to frames." in prompt.user
    assert allowed_numbers_of(schema) == [1, 2]
    assert artifact.status == "ready"
    assert artifact.metadata_json["proposed"] == 2
    assert artifact.metadata_json["kept"] == 2
    concepts_ = by_name(session, env)
    tlb = concepts_["translation lookaside buffer"]
    assert (tlb.name, tlb.aliases) == ("Translation Lookaside Buffer", ["TLB"])
    evidence = session.scalars(
        select(ConceptEvidence.chunk_id).where(ConceptEvidence.concept_id == tlb.id)
    ).all()
    chunks = chunks_of(session, memory)
    assert set(evidence) == {chunks[1].id, chunks[0].id}


def allowed_numbers_of(schema) -> list[int]:
    item = schema.model_json_schema()["$defs"]["ProposedConcept"]["properties"]
    numbers = item["sources"]["items"]
    return list(range(numbers["minimum"], numbers["maximum"] + 1))


def test_untrustworthy_proposals_never_reach_the_concept_tables(
    session: Session, session_factory
):
    env = environment(session)
    memory = add(session, session_factory, env, "memory.pdf", MEMORY)
    llm = answering(
        [
            concept("Paging", [1], aliases=["", "dividing memory into frames", "PG"]),
            concept("(TLB)", [2]),  # nothing left of the name
            concept("42", [2]),  # no letters
            concept("Frames", [1], definition="  "),  # no definition
        ]
    )

    artifact = extract(session, session_factory, memory, llm)

    assert (artifact.metadata_json["kept"], artifact.metadata_json["dropped"]) == (1, 3)
    [paging] = by_name(session, env).values()
    assert paging.aliases == ["PG"]


def test_a_reply_that_breaks_the_schema_fails_and_writes_nothing(
    session: Session, session_factory
):
    env = environment(session)
    memory = add(session, session_factory, env, "memory.pdf", MEMORY)
    llm = answering([concept("Paging", [1]), concept("TLB", [7])])  # 7 was not given

    artifact = extract(session, session_factory, memory, llm)

    # The whole reply is refused, not just the bad concept: the real provider
    # retries a reply that breaks the schema, then reports it (test_llm.py).
    assert artifact.status == "failed"
    assert artifact.content is None
    assert count(session, Concept) == 0
    assert count(session, DocumentConcept) == 0
    assert count(session, ConceptEvidence) == 0


def test_concepts_merge_by_normalized_name_across_documents(
    session: Session, session_factory
):
    env = environment(session)
    memory = add(session, session_factory, env, "memory.pdf", MEMORY)
    virtual = add(session, session_factory, env, "virtual.pdf", VIRTUAL)
    llm = answering(
        [concept("Paging", [1]), concept("Page Tables", [1])],
        [
            concept("paging", [2]),
            concept("Page table", [2]),
            concept("Demand Paging", [1]),
        ],
    )

    extract(session, session_factory, memory, llm)
    first_id = by_name(session, env)["paging"].id
    extract(session, session_factory, virtual, llm)

    concepts_ = by_name(session, env)
    assert sorted(concepts_) == ["demand paging", "page table", "paging"]
    assert concepts_["paging"].id == first_id  # stable for the knowledge graph
    linked = session.scalars(
        select(DocumentConcept.document_id).where(
            DocumentConcept.concept_id == concepts_["page table"].id
        )
    ).all()
    assert set(linked) == {memory.id, virtual.id}


def test_a_concept_shows_its_best_evidenced_documents_wording(
    session: Session, session_factory
):
    env = environment(session)
    memory = add(session, session_factory, env, "memory.pdf", MEMORY)
    virtual = add(session, session_factory, env, "virtual.pdf", VIRTUAL)
    llm = answering(
        [concept("Paging", [1], definition="From the first document.")],
        [concept("Paging", [1, 2], definition="From the second, with more evidence.")],
    )

    extract(session, session_factory, memory, llm)
    assert by_name(session, env)["paging"].definition == "From the first document."
    extract(session, session_factory, virtual, llm)

    assert by_name(session, env)["paging"].definition == (
        "From the second, with more evidence."
    )


def test_extracting_twice_writes_once(session: Session, session_factory):
    env = environment(session)
    memory = add(session, session_factory, env, "memory.pdf", MEMORY)
    llm = answering([concept("Paging", [1])])
    first = extract(session, session_factory, memory, llm)

    again, write_now = concepts.request_extraction(session, memory, llm)

    assert (again.id, write_now) == (first.id, False)
    assert len([c for c in llm.calls if c[0].name == "concept_extraction"]) == 1


def test_new_text_replaces_the_documents_concepts_and_orphans_go(
    session: Session, session_factory
):
    env = environment(session)
    memory = add(session, session_factory, env, "memory.pdf", MEMORY)
    llm = answering(
        [concept("Paging", [1]), concept("TLB", [2])],
        [concept("Threads", [1])],
    )
    old = extract(session, session_factory, memory, llm)

    document_service.request_reprocess(session, memory)
    document_service.process_document(
        session_factory,
        memory.id,
        Returns(document([H("Threads"), P("Threads share an address space.")])),
        FakeEmbedder(),
    )
    session.expire_all()
    new = extract(session, session_factory, session.get(Document, memory.id), llm)

    assert new.id != old.id
    assert sorted(by_name(session, env)) == ["thread"]
    assert count(session, ConceptEvidence) == 1
    # The earlier extraction is kept as it was.
    session.refresh(old)
    assert [c["name"] for c in old.content["concepts"]] == ["Paging", "TLB"]


def test_deleting_a_document_leaves_shared_concepts_and_removes_its_own(
    session: Session, session_factory
):
    env = environment(session)
    memory = add(session, session_factory, env, "memory.pdf", MEMORY)
    virtual = add(session, session_factory, env, "virtual.pdf", VIRTUAL)
    llm = answering(
        [concept("Paging", [1]), concept("TLB", [2])],
        [concept("Paging", [2]), concept("Demand Paging", [1])],
    )
    extract(session, session_factory, memory, llm)
    extract(session, session_factory, virtual, llm)

    document_service.delete_document(session, memory)
    concepts.refresh_concepts(session, env.id)

    assert sorted(by_name(session, env)) == ["demand paging", "paging"]


def test_a_long_document_is_read_in_sections_and_merged(
    session: Session, session_factory, monkeypatch
):
    monkeypatch.setattr(summaries, "SECTION_TOKENS", 600)
    env = environment(session)
    long = add(
        session,
        session_factory,
        env,
        "long.pdf",
        document(*[[H(f"Topic {n}"), P(words(950, f"w{n}"))] for n in range(4)]),
    )

    def per_section(prompt, schema):
        n = allowed_numbers_of(schema)[0]
        return {"concepts": [concept("Paging", [n]), concept(f"Topic {n}", [n])]}

    extract(session, session_factory, long, MockProvider(answer=per_section))

    concepts_ = by_name(session, env)
    assert sorted(concepts_) == ["paging", "topic 1", "topic 3"]
    paging_evidence = session.scalar(
        select(func.count())
        .select_from(ConceptEvidence)
        .where(ConceptEvidence.concept_id == concepts_["paging"].id)
    )
    assert paging_evidence == 2  # one passage from each of the two sections


def test_queued_concepts_wait_visibly_and_are_extracted_afterwards(
    session: Session, session_factory
):
    env = environment(session)
    memory = add(session, session_factory, env, "memory.pdf", MEMORY)
    llm = answering([concept("Paging", [1])])

    concepts.queue_when_ready(session_factory, memory.id, llm)
    session.expire_all()
    waiting = concepts.document_concepts(session, memory, llm).extraction
    assert waiting.status == "pending"
    assert llm.calls == []

    concepts.extract_when_ready(session_factory, memory.id, llm)
    session.expire_all()
    assert concepts.document_concepts(session, memory, llm).extraction.status == "ready"
    assert sorted(by_name(session, env)) == ["paging"]


def test_a_document_without_text_fails_with_the_reason(
    session: Session, session_factory
):
    env = environment(session)
    blank = add(session, session_factory, env, "blank.pdf", document([], []))

    artifact = extract(session, session_factory, blank, MockProvider())

    assert (artifact.status, artifact.error) == (
        "failed",
        "This document has no text to extract concepts from.",
    )


def test_extraction_holds_the_one_at_a_time_lock(session: Session, session_factory):
    env = environment(session)
    memory = add(session, session_factory, env, "memory.pdf", MEMORY)
    held = []

    def answer(prompt, schema):
        held.append(ONE_AT_A_TIME.locked())
        return {"concepts": [concept("Paging", [1])]}

    extract(session, session_factory, memory, MockProvider(answer=answer))

    assert held == [True]


def test_the_schema_bounds_every_list_and_string():
    schema = concepts.answer_schema([3, 4, 5]).model_json_schema()
    item = schema["$defs"]["ProposedConcept"]["properties"]

    assert schema["properties"]["concepts"]["maxItems"] == concepts.MAX_CONCEPTS
    assert item["sources"]["maxItems"] == concepts.MAX_SOURCES
    assert item["sources"]["items"] == {"minimum": 3, "maximum": 5, "type": "integer"}
    assert item["name"]["maxLength"] == 80
    assert item["definition"]["maxLength"] == 300
    assert item["aliases"]["maxItems"] == 5
