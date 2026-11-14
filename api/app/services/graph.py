"""The knowledge graph: relationships between an environment's concepts.

Purpose
-------
The backend finds candidate pairs of concepts (app/graph.py); the model only
decides what each pair is: one before the other, one part of the other,
related, or nothing. Every decision is remembered with the pair's
fingerprint, so a rebuild asks the model only about pairs it has not seen.
The graph's edges are then derived from the decisions about the current
pairs, at most one per pair of concepts, each with the passages that showed
it (decision record 12).

Like the environment's summary it is derived state: rebuilt in the
background after concepts change, only when its pairs have changed, and not
while documents are still being read or their concepts extracted.

Traversal runs in Postgres: recursive queries over the adjacency table,
carrying the path walked so far so a cycle can never loop forever.
"""

import hashlib
import logging
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Annotated

from pydantic import BaseModel, Field
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import graph as pairs_
from app import prompting
from app.db import SessionFactory
from app.llm import ONE_AT_A_TIME, LLMError, LLMProvider
from app.models import (
    Concept,
    ConceptEvidence,
    ConceptRelationship,
    Document,
    DocumentChunk,
    Environment,
    GeneratedArtifact,
    RelationshipDecision,
    RelationshipEvidence,
)
from app.schemas import (
    GraphEdge,
    GraphNode,
    GraphState,
    Neighbour,
    Neighbourhood,
)
from app.services import concepts as concept_service
from app.services import sources, summaries

logger = logging.getLogger(__name__)

ARTIFACT_TYPE = "knowledge_graph"
PROMPT = ("relationship", "v1")
BATCH = 30  # pairs per request


def _prompt_id() -> str:
    return "/".join(PROMPT)


def answer_schema(n: int) -> type[BaseModel]:
    """One decision per pair: which pair, which of its six statements, and a
    confidence. Every number is bounded (decision record 08)."""

    class Decision(BaseModel):
        pair: Annotated[int, Field(ge=1, le=n)]
        choice: Annotated[int, Field(ge=1, le=len(pairs_.DECISIONS))]
        confidence: float = Field(ge=0, le=1)

    class Answer(BaseModel):
        decisions: list[Decision] = Field(min_length=n, max_length=n)

    return Answer


# --- what the graph is built from -------------------------------------------


def _pairs(session: Session, environment_id: uuid.UUID) -> list[pairs_.Pair]:
    concepts = [
        pairs_.ConceptInfo(
            c.id, c.name, c.normalized_name, c.definition, tuple(c.aliases)
        )
        for c in session.scalars(
            select(Concept).where(Concept.environment_id == environment_id)
        )
    ]
    evidence: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for concept_id, chunk_id in session.execute(
        select(ConceptEvidence.concept_id, ConceptEvidence.chunk_id)
        .join(Concept, Concept.id == ConceptEvidence.concept_id)
        .where(Concept.environment_id == environment_id)
    ):
        evidence[concept_id].add(chunk_id)
    chunk_ids = {c for ids in evidence.values() for c in ids}
    passages = {
        chunk.id: pairs_.Passage(
            chunk.id,
            chunk.document_id,
            chunk.ordinal,
            sources.with_heading(chunk),
            chunk.content_hash,
        )
        for chunk in session.scalars(
            select(DocumentChunk).where(DocumentChunk.id.in_(chunk_ids))
        )
    }
    return pairs_.find_pairs(concepts, evidence, passages)


def _waiting_for(session: Session, environment: Environment, llm: LLMProvider) -> int:
    """Documents still being read, or whose concepts are still on their way."""
    waiting = 0
    for doc in session.scalars(
        select(Document).where(Document.environment_id == environment.id)
    ):
        if doc.status in ("uploaded", "processing"):
            waiting += 1
        elif doc.status == "ready":
            extraction = concept_service.current_extraction(session, doc, llm)
            if extraction is not None and extraction.status in (
                "pending",
                "generating",
            ):
                waiting += 1
    return waiting


def _version(pairs: list[pairs_.Pair]) -> str:
    return hashlib.sha256("\n".join(sorted(p.key for p in pairs)).encode()).hexdigest()


def _find(session: Session, environment_id: uuid.UUID, version: str, model: str):
    return session.scalar(
        select(GeneratedArtifact).where(
            GeneratedArtifact.environment_id == environment_id,
            GeneratedArtifact.document_id.is_(None),
            GeneratedArtifact.artifact_type == ARTIFACT_TYPE,
            GeneratedArtifact.source_version == version,
            GeneratedArtifact.model_name == model,
            GeneratedArtifact.prompt_version == _prompt_id(),
        )
    )


def request_graph(
    session: Session, environment: Environment, llm: LLMProvider
) -> tuple[GeneratedArtifact | None, bool]:
    """Make sure the graph of the environment's current pairs is built or
    coming. None while documents are still on their way, or when there is no
    pair to build from. The same pairs, model and prompt find the same build,
    so asking again never rebuilds; a failed or abandoned one is tried again."""
    if _waiting_for(session, environment, llm):
        return None, False
    pairs = _pairs(session, environment.id)
    if not pairs:
        _replace_edges(session, environment.id, [], {})  # nothing left to connect
        session.commit()
        return None, False
    version = _version(pairs)
    artifact = _find(session, environment.id, version, llm.model_name)
    if artifact is None:
        artifact = GeneratedArtifact(
            environment_id=environment.id,
            document_id=None,
            artifact_type=ARTIFACT_TYPE,
            source_version=version,
            model_name=llm.model_name,
            prompt_version=_prompt_id(),
            status="pending",
            metadata_json={"pairs": len(pairs)},
        )
        session.add(artifact)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            return _find(session, environment.id, version, llm.model_name), False
        return artifact, True
    abandoned = (
        artifact.status == "generating"
        and datetime.now(UTC) - artifact.updated_at > summaries.STALE_GENERATING
    )
    if artifact.status == "failed" or abandoned:
        artifact.status, artifact.error = "pending", None
        session.commit()
        return artifact, True
    if artifact.status == "ready":
        known = _remembered(session, environment.id, {p.key for p in pairs}, llm)
        if len(known) < len({p.key for p in pairs}):
            # A finished build whose decisions are not all remembered (lost
            # before decisions outlived their concepts): ask only for those.
            artifact.status = "pending"
            session.commit()
            return artifact, True
        # The same pairs as a finished build: make the edges say so again, in
        # case a newer build changed them and its material was later undone.
        _rebuild_edges(session, environment.id, pairs, llm)
        session.commit()
    return artifact, False


# --- asking the model ---------------------------------------------------------


def _ask(pairs: list[pairs_.Pair], llm: LLMProvider) -> dict[str, tuple[str, float]]:
    """The model's decision for each pair, by pair key: asked in batches of
    pairs from the same document, with that document's passages."""
    template = prompting.part(*PROMPT, "pair")
    by_document: dict[uuid.UUID, list[pairs_.Pair]] = defaultdict(list)
    for pair in pairs:
        by_document[pair.document_id].append(pair)
    decided: dict[str, tuple[str, float]] = {}
    for batch_source in by_document.values():
        for start in range(0, len(batch_source), BATCH):
            batch = batch_source[start : start + BATCH]
            passages = sorted(
                {p for pair in batch for p in pair.passages},
                key=lambda p: (str(p.document_id), p.ordinal),
            )
            number = {p.id: n for n, p in enumerate(passages, start=1)}
            blocks = [
                template.substitute(
                    number=i,
                    passages=", ".join(str(number[p.id]) for p in pair.passages),
                    a=pair.a.name,
                    a_definition=pair.a.definition,
                    b=pair.b.name,
                    b_definition=pair.b.definition,
                )
                for i, pair in enumerate(batch, start=1)
            ]
            prompt = prompting.render(
                *PROMPT,
                passages="\n\n".join(f"[{number[p.id]}] {p.text}" for p in passages),
                pairs="\n\n".join(blocks),
            )
            answer = llm.generate_structured(prompt, answer_schema(len(batch))).value
            for decision in answer.decisions:
                pair = batch[decision.pair - 1]
                # A pair answered twice keeps its first answer; one left out
                # is asked again by the next build.
                decided.setdefault(
                    pair.key,
                    (pairs_.DECISIONS[decision.choice - 1], decision.confidence),
                )
    return decided


# --- the edges ------------------------------------------------------------------


def _replace_edges(
    session: Session,
    environment_id: uuid.UUID,
    pairs: list[pairs_.Pair],
    decisions: dict[str, tuple[str, float]],
) -> None:
    """Make the environment's edges exactly those its current pairs'
    decisions stand for: one per pair at most, with the pair's passages as
    evidence."""
    session.execute(
        delete(ConceptRelationship).where(
            ConceptRelationship.environment_id == environment_id
        )
    )
    session.flush()
    for pair in pairs:
        if pair.key not in decisions:
            continue
        edge = pairs_.edge_for(pair, *decisions[pair.key])
        if edge is None:
            continue
        relationship = ConceptRelationship(
            environment_id=environment_id,
            source_concept_id=edge.source,
            target_concept_id=edge.target,
            relationship_type=edge.relationship_type,
            confidence=edge.confidence,
        )
        session.add(relationship)
        session.flush()
        for passage in pair.passages:
            session.add(
                RelationshipEvidence(
                    relationship_id=relationship.id,
                    chunk_id=passage.id,
                    document_id=passage.document_id,
                )
            )
    session.flush()


def _remembered(
    session: Session, environment_id: uuid.UUID, keys: set[str], llm: LLMProvider
) -> dict[str, tuple[str, float]]:
    return {
        d.pair_key: (d.decision, d.confidence)
        for d in session.scalars(
            select(RelationshipDecision).where(
                RelationshipDecision.environment_id == environment_id,
                RelationshipDecision.pair_key.in_(keys),
                RelationshipDecision.model_name == llm.model_name,
                RelationshipDecision.prompt_version == _prompt_id(),
            )
        )
    }


def _rebuild_edges(
    session: Session,
    environment_id: uuid.UUID,
    pairs: list[pairs_.Pair],
    llm: LLMProvider,
) -> None:
    decisions = _remembered(session, environment_id, {p.key for p in pairs}, llm)
    _replace_edges(session, environment_id, pairs, decisions)


def write_graph(
    session_factory: SessionFactory, artifact_id: uuid.UUID, llm: LLMProvider
) -> None:
    """Build a pending graph. Runs as a background task, one model task at a
    time. Only pairs without a remembered decision go to the model, outside
    any transaction; the new decisions and the rebuilt edges are then stored
    together in one."""
    with ONE_AT_A_TIME:
        with session_factory() as session:
            artifact = session.get(GeneratedArtifact, artifact_id, with_for_update=True)
            if artifact is None or artifact.status != "pending":
                return
            environment = session.get(Environment, artifact.environment_id)
            pairs = _pairs(session, environment.id)
            if (
                _waiting_for(session, environment, llm)
                or _version(pairs) != artifact.source_version
                or llm.model_name != artifact.model_name
            ):
                artifact.status = "failed"
                artifact.error = "The concepts changed before the graph was built."
                session.commit()
                return
            known = _remembered(session, environment.id, {p.key for p in pairs}, llm)
            unseen = [p for p in pairs if p.key not in known]
            artifact.status = "generating"
            session.commit()

        problem, decided = None, {}
        try:
            decided = _ask(unseen, llm) if unseen else {}
        except LLMError as exc:
            problem = str(exc)
        except Exception:
            logger.exception("Building the graph %s failed", artifact_id)
            problem = "An unexpected error occurred while building the graph."

        with session_factory() as session:
            artifact = session.get(GeneratedArtifact, artifact_id, with_for_update=True)
            if artifact is None or artifact.status != "generating":
                return
            if problem is not None:
                artifact.status, artifact.error = "failed", problem
                session.commit()
                return
            if (
                _version(_pairs(session, artifact.environment_id))
                != artifact.source_version
            ):
                artifact.status = "failed"
                artifact.error = "The concepts changed before the graph was built."
                session.commit()
                return
            by_key = {p.key: p for p in unseen}
            for key, (decision, confidence) in decided.items():
                pair = by_key[key]
                session.add(
                    RelationshipDecision(
                        environment_id=artifact.environment_id,
                        pair_key=key,
                        concept_a_id=pair.a.id,
                        concept_b_id=pair.b.id,
                        decision=decision,
                        confidence=confidence,
                        model_name=llm.model_name,
                        prompt_version=_prompt_id(),
                    )
                )
            session.flush()
            _rebuild_edges(session, artifact.environment_id, pairs, llm)
            edges = session.scalars(
                select(ConceptRelationship.relationship_type).where(
                    ConceptRelationship.environment_id == artifact.environment_id
                )
            ).all()
            artifact.status = "ready"
            artifact.content = {
                "edges": {kind: edges.count(kind) for kind in sorted(set(edges))}
            }
            artifact.metadata_json = {
                **artifact.metadata_json,
                "asked": len(unseen),
                "remembered": len(pairs) - len(unseen),
                "written_at": datetime.now(UTC).isoformat(),
            }
            session.commit()


def refresh_graph(
    session_factory: SessionFactory, environment_id: uuid.UUID, llm: LLMProvider
) -> None:
    """Bring the environment's graph up to date, if its pairs changed. Runs
    as a background task after concept extractions and deletions."""
    with session_factory() as session:
        environment = session.get(Environment, environment_id)
        if environment is None:
            return
        artifact, write_now = request_graph(session, environment, llm)
        artifact_id = artifact.id if artifact else None
    if write_now:
        write_graph(session_factory, artifact_id, llm)


# --- reading the graph ---------------------------------------------------------


def _expected_edges(
    session: Session,
    environment_id: uuid.UUID,
    pairs: list[pairs_.Pair],
    llm: LLMProvider,
) -> set[tuple[uuid.UUID, uuid.UUID, str]]:
    """The edges the current pairs' remembered decisions stand for."""
    decisions = _remembered(session, environment_id, {p.key for p in pairs}, llm)
    edges = (
        pairs_.edge_for(pair, *decisions[pair.key])
        for pair in pairs
        if pair.key in decisions
    )
    return {(e.source, e.target, e.relationship_type) for e in edges if e is not None}


def state(session: Session, environment: Environment, llm: LLMProvider) -> GraphState:
    """The environment's graph as it stands, and where its build is. Up to
    date only when the stored edges are those the current pairs' decisions
    stand for: a build found ready again is not up to date until its edges
    have been written back, a moment after the concepts changed."""
    waiting = _waiting_for(session, environment, llm)
    pairs = [] if waiting else _pairs(session, environment.id)
    current = (
        _find(session, environment.id, _version(pairs), llm.model_name)
        if pairs
        else None
    )
    relationships = list(
        session.scalars(
            select(ConceptRelationship).where(
                ConceptRelationship.environment_id == environment.id
            )
        )
    )
    if waiting:
        label = "waiting"
    elif not pairs:
        label = "none"
    elif current is None:
        label = "stale"
    elif current.status in ("pending", "generating"):
        label = "updating"
    elif current.status == "failed":
        label = "failed"
    elif _expected_edges(session, environment.id, pairs, llm) != {
        (r.source_concept_id, r.target_concept_id, r.relationship_type)
        for r in relationships
    }:
        label = "stale"
    else:
        label = "up_to_date"
    nodes = [
        GraphNode(id=c.id, name=c.name)
        for c in session.scalars(
            select(Concept)
            .where(Concept.environment_id == environment.id)
            .order_by(Concept.normalized_name)
        )
    ]
    edges = [
        GraphEdge(
            id=r.id,
            source=r.source_concept_id,
            target=r.target_concept_id,
            relationship_type=r.relationship_type,
            confidence=r.confidence,
        )
        for r in relationships
    ]
    meta = current.metadata_json if current else {}
    return GraphState(
        state=label,
        waiting_for=waiting,
        error=current.error if label == "failed" else None,
        nodes=nodes,
        edges=edges,
        pairs=meta.get("pairs"),
        asked=meta.get("asked"),
        updated_at=current.updated_at if current else None,
    )


# Every concept reachable from :start along prerequisite edges, walking
# against (prerequisites) or with (dependents) the arrows, with the fewest
# steps it takes. The path walked so far is carried along, so a cycle in the
# graph ends the walk instead of looping. :limit caps the depth.
_WALK = """
WITH RECURSIVE walk(concept_id, depth, path) AS (
    SELECT {next}, 1, ARRAY[{here}]
    FROM concept_relationships
    WHERE {here} = :start AND relationship_type = 'PREREQUISITE_OF'
  UNION ALL
    SELECT r.{next}, w.depth + 1, w.path || r.{here}
    FROM concept_relationships r
    JOIN walk w ON r.{here} = w.concept_id
    WHERE r.relationship_type = 'PREREQUISITE_OF'
      AND NOT r.{next} = ANY(w.path || r.{here})
      AND w.depth < :limit
)
SELECT concept_id, min(depth) AS depth FROM walk GROUP BY concept_id
"""
_PREREQUISITES = text(_WALK.format(here="target_concept_id", next="source_concept_id"))
_DEPENDENTS = text(_WALK.format(here="source_concept_id", next="target_concept_id"))
MAX_DEPTH = 25


def walk(
    session: Session, concept_id: uuid.UUID, direction: str
) -> dict[uuid.UUID, int]:
    """Concept id to depth, for every concept reachable along prerequisites:
    "prerequisites" for what the concept builds on, "dependents" for what
    builds on it."""
    query = _PREREQUISITES if direction == "prerequisites" else _DEPENDENTS
    rows = session.execute(query, {"start": concept_id, "limit": MAX_DEPTH})
    return {row.concept_id: row.depth for row in rows if row.concept_id != concept_id}


def neighbourhood(session: Session, concept: Concept) -> Neighbourhood:
    """Everything next to a concept in the graph, with evidence for each direct
    relationship."""
    direct = list(
        session.scalars(
            select(ConceptRelationship).where(
                (ConceptRelationship.source_concept_id == concept.id)
                | (ConceptRelationship.target_concept_id == concept.id)
            )
        )
    )
    evidence_rows = session.execute(
        select(RelationshipEvidence.relationship_id, DocumentChunk)
        .join(DocumentChunk, DocumentChunk.id == RelationshipEvidence.chunk_id)
        .where(RelationshipEvidence.relationship_id.in_([r.id for r in direct]))
        .order_by(DocumentChunk.document_id, DocumentChunk.ordinal)
    ).all()
    citations = sources.cite_all(session, [chunk for _, chunk in evidence_rows])
    evidence = defaultdict(list)
    for (relationship_id, _), citation in zip(evidence_rows, citations, strict=True):
        evidence[relationship_id].append(citation)

    prerequisites = walk(session, concept.id, "prerequisites")
    dependents = walk(session, concept.id, "dependents")
    names = {
        c.id: c.name
        for c in session.scalars(
            select(Concept).where(
                Concept.id.in_(
                    {*prerequisites, *dependents}
                    | {r.source_concept_id for r in direct}
                    | {r.target_concept_id for r in direct}
                )
            )
        )
    }
    by_neighbour = {}
    for r in direct:
        other = (
            r.target_concept_id
            if r.source_concept_id == concept.id
            else r.source_concept_id
        )
        by_neighbour[
            (other, r.relationship_type, r.source_concept_id == concept.id)
        ] = r

    def neighbour(other: uuid.UUID, depth: int, relationship=None) -> Neighbour:
        return Neighbour(
            id=other,
            name=names[other],
            depth=depth,
            confidence=relationship.confidence if relationship else None,
            evidence=evidence[relationship.id] if relationship else [],
        )

    def along(found: dict[uuid.UUID, int], as_source: bool) -> list[Neighbour]:
        return [
            neighbour(
                other, depth, by_neighbour.get((other, "PREREQUISITE_OF", as_source))
            )
            for other, depth in sorted(
                found.items(), key=lambda kv: (kv[1], names[kv[0]])
            )
        ]

    def direct_of(kind: str, as_source: bool | None) -> list[Neighbour]:
        chosen = [
            (other, r)
            for (other, k, is_source), r in by_neighbour.items()
            if k == kind and (as_source is None or is_source == as_source)
        ]
        return [
            neighbour(o, 1, r) for o, r in sorted(chosen, key=lambda x: names[x[0]])
        ]

    return Neighbourhood(
        concept=GraphNode(id=concept.id, name=concept.name),
        definition=concept.definition,
        aliases=concept.aliases,
        prerequisites=along(prerequisites, as_source=False),
        dependents=along(dependents, as_source=True),
        part_of=direct_of("PART_OF", as_source=True),
        parts=direct_of("PART_OF", as_source=False),
        related=direct_of("RELATED_TO", as_source=None),
    )
