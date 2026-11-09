"""Concepts: proposed by the language model, validated and stored by us.

Purpose
-------
Each document's passages, numbered as for summaries, are given to the model
section by section; it proposes up to MAX_CONCEPTS concepts per section, each
with a name, a definition, aliases and the numbers of the passages that
explain it. The answer's shape is enforced while it is written, then
app/concepts.py validates and names what was proposed. The model never
writes to the concept tables: the backend does, from a validated extraction
(decision record 11).

An extraction is stored as a generated artifact per document text, model and
prompt, like a summary: the same again finds it, new text extracts anew, and
earlier extractions are kept. When one is ready, that document's links to
concepts are replaced in one transaction. Concepts are found or created by
normalized name, so their ids stay stable for the knowledge graph, and a
concept no document mentions any more is deleted. What a concept shows (its
name, definition and aliases) comes from the document with the most evidence
for it, then the earliest.
"""

import logging
import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Annotated

from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import concepts as naming
from app import prompting
from app.db import SessionFactory
from app.llm import ONE_AT_A_TIME, LLMError, LLMProvider
from app.models import (
    Concept,
    ConceptEvidence,
    Document,
    DocumentChunk,
    DocumentConcept,
    GeneratedArtifact,
)
from app.schemas import (
    ConceptDocument,
    ConceptInventory,
    ConceptRead,
    DocumentConceptsRead,
    ExtractionState,
)
from app.services import sources, summaries

logger = logging.getLogger(__name__)

ARTIFACT_TYPE = "concept_extraction"
PROMPT = ("concept_extraction", "v1")
MAX_CONCEPTS = 12  # per section
MAX_SOURCES = 4  # passages one concept may cite


def answer_schema(numbers: Sequence[int]) -> type[BaseModel]:
    """The shape the model must answer in. Passage numbers can only be ones
    it was given, and every list and string has a limit (decision record 08)."""
    Number = Annotated[int, Field(ge=numbers[0], le=numbers[-1])]

    class ProposedConcept(BaseModel):
        name: str = Field(min_length=1, max_length=naming.MAX_NAME)
        definition: str = Field(min_length=1, max_length=naming.MAX_DEFINITION)
        aliases: list[Annotated[str, Field(max_length=naming.MAX_NAME)]] = Field(
            max_length=naming.MAX_ALIASES
        )
        sources: list[Number] = Field(min_length=1, max_length=MAX_SOURCES)

    class Answer(BaseModel):
        concepts: list[ProposedConcept] = Field(max_length=MAX_CONCEPTS)

    return Answer


def _prompt_id() -> str:
    return "/".join(PROMPT)


def _find(session: Session, document: Document, source_version: str, model: str):
    return session.scalar(
        select(GeneratedArtifact).where(
            GeneratedArtifact.document_id == document.id,
            GeneratedArtifact.artifact_type == ARTIFACT_TYPE,
            GeneratedArtifact.source_version == source_version,
            GeneratedArtifact.model_name == model,
            GeneratedArtifact.prompt_version == _prompt_id(),
        )
    )


def current_extraction(
    session: Session, document: Document, llm: LLMProvider
) -> GeneratedArtifact | None:
    """The extraction of the document as it is now, if one was asked for."""
    if document.status != "ready":
        return None
    plan = summaries.plan(session, document)
    return _find(session, document, plan.source_version, llm.model_name)


def _problem(plan: summaries.Plan) -> str | None:
    """Why a document's concepts cannot be extracted, if they cannot: the
    same limits as summaries, in words about concepts."""
    if plan.problem is None:
        return None
    if not plan.chunks:
        return "This document has no text to extract concepts from."
    return (
        f"This document is too long to extract concepts from: it has "
        f"{len(plan.sections)} sections' worth of text, and at most "
        f"{summaries.MAX_SECTIONS} are read."
    )


def request_extraction(
    session: Session, document: Document, llm: LLMProvider
) -> tuple[GeneratedArtifact, bool]:
    """Make sure the document's concepts, as it is now, are extracted or on
    their way. Same rules as summaries: the same text, model and prompt find
    the same row; failed or abandoned extractions are tried again; a document
    without text, or too long, fails at once with the reason."""
    plan = summaries.plan(session, document)
    artifact = _find(session, document, plan.source_version, llm.model_name)
    if artifact is None:
        artifact = GeneratedArtifact(
            environment_id=document.environment_id,
            document_id=document.id,
            artifact_type=ARTIFACT_TYPE,
            source_version=plan.source_version,
            model_name=llm.model_name,
            prompt_version=_prompt_id(),
            status="failed" if plan.problem else "pending",
            error=_problem(plan),
            metadata_json={"sections": len(plan.sections)},
        )
        session.add(artifact)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            return _find(session, document, plan.source_version, llm.model_name), False
        return artifact, plan.problem is None
    abandoned = (
        artifact.status == "generating"
        and datetime.now(UTC) - artifact.updated_at > summaries.STALE_GENERATING
    )
    if (artifact.status == "failed" and plan.problem is None) or abandoned:
        artifact.status, artifact.error = "pending", None
        session.commit()
        return artifact, True
    return artifact, False


def _propose(
    filename: str, sections: list[list[tuple[int, str]]], llm: LLMProvider
) -> tuple[list, set[int], float]:
    """Ask the model for each section's concepts. Returns every proposal, the
    passage numbers given, and the seconds the model took."""
    proposals, given, seconds = [], set(), 0.0
    for section in sections:
        numbers = [n for n, _ in section]
        prompt = prompting.render(
            *PROMPT,
            filename=filename,
            passages="\n\n".join(f"[{n}] {text}" for n, text in section),
            max_concepts=MAX_CONCEPTS,
        )
        generated = llm.generate_structured(prompt, answer_schema(numbers))
        proposals += generated.value.concepts
        given.update(numbers)
        seconds += generated.seconds
    return proposals, given, seconds


def write_extraction(
    session_factory: SessionFactory, artifact_id: uuid.UUID, llm: LLMProvider
) -> None:
    """Extract a pending document's concepts and store them. Runs as a
    background task, one model task at a time. The model works outside any
    transaction; the validated result, and the document's concept links, are
    written together in one, so the concept tables only ever hold validated
    extractions."""
    with ONE_AT_A_TIME:
        with session_factory() as session:
            artifact = session.get(GeneratedArtifact, artifact_id, with_for_update=True)
            if artifact is None or artifact.status != "pending":
                return
            document = session.get(Document, artifact.document_id)
            plan = (
                summaries.plan(session, document)
                if document.status == "ready"
                else None
            )
            if (
                plan is None
                or plan.source_version != artifact.source_version
                or llm.model_name != artifact.model_name
            ):
                artifact.status = "failed"
                artifact.error = (
                    "The document changed before its concepts were extracted."
                )
                session.commit()
                return
            filename = document.filename
            chunk_ids = [
                chunk.id for chunk in plan.chunks
            ]  # passage n is chunk_ids[n - 1]
            sections = [
                [(n, sources.with_heading(chunk)) for n, chunk in section]
                for section in plan.sections
            ]
            artifact.status = "generating"
            session.commit()

        problem, kept, proposed_count, dropped, seconds = None, [], 0, 0, None
        try:
            proposals, given, seconds = _propose(filename, sections, llm)
            kept, dropped = naming.validate(proposals, given)
            proposed_count = len(proposals)
        except LLMError as exc:
            problem = str(exc)
        except Exception:
            logger.exception("Extracting concepts for %s failed", artifact_id)
            problem = "An unexpected error occurred while extracting concepts."

        with session_factory() as session:
            artifact = session.get(GeneratedArtifact, artifact_id, with_for_update=True)
            if artifact is None or artifact.status != "generating":
                return
            document = session.get(Document, artifact.document_id)
            if problem is None and (
                document.status != "ready"
                or summaries.plan(session, document).source_version
                != artifact.source_version
            ):
                problem = "The document changed before its concepts were extracted."
            if problem is not None:
                artifact.status, artifact.error = "failed", problem
                session.commit()
                return
            artifact.status = "ready"
            artifact.content = {
                "concepts": [
                    {
                        "name": c.name,
                        "normalized_name": c.normalized_name,
                        "definition": c.definition,
                        "aliases": c.aliases,
                        "chunk_ids": [str(chunk_ids[n - 1]) for n in c.passages],
                    }
                    for c in kept
                ]
            }
            artifact.metadata_json = {
                **artifact.metadata_json,
                "seconds": round(seconds, 1),
                # How much of what the model proposed survived validation:
                # proposed = kept + dropped + duplicates merged into others.
                "proposed": proposed_count,
                "kept": len(kept),
                "dropped": dropped,
            }
            _replace_links(session, document, artifact.content["concepts"])
            session.commit()


def _replace_links(session: Session, document: Document, extracted: list[dict]) -> None:
    """Make the concept tables say what this extraction says about this
    document, and nothing else: its old links go, concepts are found or
    created by normalized name, its new links and evidence are written, and
    what every concept in the environment shows is brought up to date."""
    session.execute(
        delete(ConceptEvidence).where(ConceptEvidence.document_id == document.id)
    )
    session.execute(
        delete(DocumentConcept).where(DocumentConcept.document_id == document.id)
    )
    for item in extracted:
        concept = session.scalar(
            select(Concept).where(
                Concept.environment_id == document.environment_id,
                Concept.normalized_name == item["normalized_name"],
            )
        )
        if concept is None:
            concept = Concept(
                environment_id=document.environment_id,
                name=item["name"],
                normalized_name=item["normalized_name"],
                definition=item["definition"],
                aliases=item["aliases"],
            )
            session.add(concept)
            session.flush()
        session.add(
            DocumentConcept(
                document_id=document.id,
                concept_id=concept.id,
                name=item["name"],
                definition=item["definition"],
                aliases=item["aliases"],
            )
        )
        for chunk_id in item["chunk_ids"]:
            session.add(
                ConceptEvidence(
                    concept_id=concept.id,
                    chunk_id=uuid.UUID(chunk_id),
                    document_id=document.id,
                )
            )
    session.flush()
    refresh_concepts(session, document.environment_id)


def refresh_concepts(session: Session, environment_id: uuid.UUID) -> None:
    """Bring every concept of the environment in line with its documents:
    delete those no document mentions, and show for the rest the name,
    definition and aliases of the document with the most evidence for them,
    then the earliest document."""
    links = session.execute(
        select(
            DocumentConcept,
            func.count(ConceptEvidence.chunk_id),
            Document.created_at,
        )
        .join(Document, Document.id == DocumentConcept.document_id)
        .outerjoin(
            ConceptEvidence,
            (ConceptEvidence.concept_id == DocumentConcept.concept_id)
            & (ConceptEvidence.document_id == DocumentConcept.document_id),
        )
        .where(Document.environment_id == environment_id)
        .group_by(
            DocumentConcept.document_id, DocumentConcept.concept_id, Document.created_at
        )
    ).all()
    best: dict[uuid.UUID, tuple] = {}
    for link, evidence, created in links:
        rank = (-evidence, created, str(link.document_id))
        if link.concept_id not in best or rank < best[link.concept_id][0]:
            best[link.concept_id] = (rank, link)
    for concept in session.scalars(
        select(Concept).where(Concept.environment_id == environment_id)
    ):
        if concept.id not in best:
            session.delete(concept)
            continue
        link = best[concept.id][1]
        concept.name, concept.definition, concept.aliases = (
            link.name,
            link.definition,
            link.aliases,
        )
    session.flush()


def queue_when_ready(
    session_factory: SessionFactory, document_id: uuid.UUID, llm: LLMProvider
) -> None:
    """After processing: ask for the document's concepts at once, without
    extracting them yet. The document's summary is written first; queuing
    now means the extraction shows as waiting meanwhile, instead of looking
    as if none was coming. Runs as a background task."""
    with session_factory() as session:
        document = session.get(Document, document_id)
        if document is not None and document.status == "ready":
            request_extraction(session, document, llm)


def extract_when_ready(
    session_factory: SessionFactory, document_id: uuid.UUID, llm: LLMProvider
) -> None:
    """Extract the document's concepts if they are waiting, asking for them
    first if no one has. Runs as a background task, after the summary."""
    with session_factory() as session:
        document = session.get(Document, document_id)
        if document is None or document.status != "ready":
            return
        artifact, _ = request_extraction(session, document, llm)
        artifact_id, waiting = artifact.id, artifact.status == "pending"
    if waiting:
        write_extraction(session_factory, artifact_id, llm)


def _state(document: Document, artifact: GeneratedArtifact | None) -> ExtractionState:
    meta = artifact.metadata_json if artifact else {}
    return ExtractionState(
        document_id=document.id,
        filename=document.filename,
        document_status=document.status,
        status=artifact.status if artifact else "none",
        error=artifact.error if artifact else None,
        model=artifact.model_name if artifact else None,
        prompt_version=artifact.prompt_version if artifact else None,
        proposed=meta.get("proposed"),
        kept=meta.get("kept"),
    )


def _read(session: Session, concepts: list[Concept]) -> list[ConceptRead]:
    """Concepts as the API shows them, with documents and evidence, in two
    queries however many concepts there are."""
    ids = [c.id for c in concepts]
    documents: dict[uuid.UUID, list[ConceptDocument]] = defaultdict(list)
    for concept_id, doc_id, filename in session.execute(
        select(DocumentConcept.concept_id, Document.id, Document.filename)
        .join(Document, Document.id == DocumentConcept.document_id)
        .where(DocumentConcept.concept_id.in_(ids))
        .order_by(Document.created_at, Document.id)
    ):
        documents[concept_id].append(
            ConceptDocument(document_id=doc_id, filename=filename)
        )
    evidence_rows = session.execute(
        select(ConceptEvidence.concept_id, DocumentChunk)
        .join(DocumentChunk, DocumentChunk.id == ConceptEvidence.chunk_id)
        .where(ConceptEvidence.concept_id.in_(ids))
        .order_by(DocumentChunk.document_id, DocumentChunk.ordinal)
    ).all()
    citations = sources.cite_all(session, [chunk for _, chunk in evidence_rows])
    evidence = defaultdict(list)
    for (concept_id, _), citation in zip(evidence_rows, citations, strict=True):
        evidence[concept_id].append(citation)
    return [
        ConceptRead(
            id=c.id,
            name=c.name,
            normalized_name=c.normalized_name,
            definition=c.definition,
            aliases=c.aliases,
            documents=documents[c.id],
            evidence=evidence[c.id],
        )
        for c in concepts
    ]


def inventory(
    session: Session, environment_id: uuid.UUID, llm: LLMProvider
) -> ConceptInventory:
    """Every concept in the environment, by name, and every document's
    extraction state."""
    concepts = list(
        session.scalars(
            select(Concept)
            .where(Concept.environment_id == environment_id)
            .order_by(Concept.normalized_name)
        )
    )
    documents = session.scalars(
        select(Document)
        .where(Document.environment_id == environment_id)
        .order_by(Document.created_at, Document.id)
    )
    return ConceptInventory(
        concepts=_read(session, concepts),
        documents=[_state(d, current_extraction(session, d, llm)) for d in documents],
    )


def document_concepts(
    session: Session, document: Document, llm: LLMProvider
) -> DocumentConceptsRead:
    """One document's extraction state and the concepts it contributes."""
    concepts = list(
        session.scalars(
            select(Concept)
            .join(DocumentConcept, DocumentConcept.concept_id == Concept.id)
            .where(DocumentConcept.document_id == document.id)
            .order_by(Concept.normalized_name)
        )
    )
    return DocumentConceptsRead(
        extraction=_state(document, current_extraction(session, document, llm)),
        concepts=_read(session, concepts),
    )
