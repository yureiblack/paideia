"""The learning roadmap: an environment's concepts as an ordered path.

Purpose
-------
The roadmap's stages and their order come from fixed rules over the
concepts and the knowledge graph (app/roadmap.py), computed afresh whenever
the roadmap is read, so they always match the material. The model only
writes each stage's title and one-sentence description, and never sees or
changes the order (decision record 13).

Titles are derived state like the graph: written in the background once the
graph is up to date, and remembered by stage. A stage whose concepts and
definitions are unchanged keeps its title, so adding a lecture asks the
model only about the stages it changed. Until a stage has a title, and
whenever the model cannot write one, it shows a plain one ("Deadlock and 6
more"): the roadmap never waits for the model.
"""

import hashlib
import logging
import re
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import prompting
from app import roadmap as rules
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
)
from app.schemas import (
    ConceptDocument,
    ConceptRef,
    RoadmapConcept,
    RoadmapCycle,
    RoadmapStage,
    RoadmapState,
)
from app.services import graph as graph_service
from app.services import sources, summaries

logger = logging.getLogger(__name__)

ARTIFACT_TYPE = "learning_roadmap"
PROMPT = ("roadmap_stages", "v1")
TITLE_WORDS = 8
DESCRIPTION_WORDS = 45
EVIDENCE_SHOWN = 4  # passages shown per concept

# Formatting a title or description must not carry: Markdown marks, list
# bullets, line breaks.
_MARKUP = re.compile(r"[*#`|\n]|^\s*(?:[-•]|\d+[.)])\s")


def _prompt_id() -> str:
    return "/".join(PROMPT)


def answer_schema(n: int) -> type[BaseModel]:
    """A title and a description for each of n stages. Every length is
    bounded (decision record 08)."""

    class StageText(BaseModel):
        stage: Annotated[int, Field(ge=1, le=n)]
        title: str = Field(min_length=1, max_length=60)
        description: str = Field(min_length=1, max_length=300)

    class Answer(BaseModel):
        stages: list[StageText] = Field(min_length=n, max_length=n)

    return Answer


# --- what the roadmap is built from -------------------------------------------


@dataclass
class Material:
    """The environment's concepts and relationships as the rules need them,
    the roadmap they give, and what is needed to show it."""

    nodes: dict[uuid.UUID, rules.Node]
    links: list[rules.Link]
    roadmap: rules.Roadmap
    documents: dict[uuid.UUID, Document]  # in the order they were added
    concept_documents: dict[uuid.UUID, list[uuid.UUID]]  # in that order
    evidence: dict[uuid.UUID, list[DocumentChunk]]  # in reading order

    @property
    def keys(self) -> list[str]:
        return [rules.stage_key(stage, self.nodes) for stage in self.roadmap.stages]

    @property
    def version(self) -> str:
        return hashlib.sha256("\n".join(self.keys).encode()).hexdigest()


def material(session: Session, environment_id: uuid.UUID) -> Material:
    documents = list(
        session.scalars(
            select(Document)
            .where(Document.environment_id == environment_id)
            .order_by(Document.created_at, Document.id)
        )
    )
    rank = {doc.id: n for n, doc in enumerate(documents)}
    evidence: dict[uuid.UUID, list[DocumentChunk]] = defaultdict(list)
    for concept_id, chunk in session.execute(
        select(ConceptEvidence.concept_id, DocumentChunk)
        .join(DocumentChunk, DocumentChunk.id == ConceptEvidence.chunk_id)
        .join(Concept, Concept.id == ConceptEvidence.concept_id)
        .where(Concept.environment_id == environment_id)
    ):
        evidence[concept_id].append(chunk)
    nodes = {}
    for concept in session.scalars(
        select(Concept).where(Concept.environment_id == environment_id)
    ):
        chunks = sorted(
            evidence[concept.id], key=lambda c: (rank.get(c.document_id, 0), c.ordinal)
        )
        evidence[concept.id] = chunks
        first = chunks[0] if chunks else None
        nodes[concept.id] = rules.Node(
            id=concept.id,
            name=concept.name,
            normalized_name=concept.normalized_name,
            definition=concept.definition,
            position=(rank[first.document_id], first.ordinal)
            if first
            else (len(rank), 0),
            home=first.document_id if first else uuid.UUID(int=0),
            evidence=len(chunks),
        )
    links = [
        rules.Link(r.source_concept_id, r.target_concept_id, r.relationship_type)
        for r in session.scalars(
            select(ConceptRelationship).where(
                ConceptRelationship.environment_id == environment_id
            )
        )
    ]
    concept_documents = {
        concept_id: sorted(
            {c.document_id for c in evidence[concept_id]}, key=rank.__getitem__
        )
        for concept_id in nodes
    }
    return Material(
        nodes=nodes,
        links=links,
        roadmap=rules.build(nodes.values(), links),
        documents={doc.id: doc for doc in documents},
        concept_documents=concept_documents,
        evidence=evidence,
    )


def _graph_busy(session: Session, environment: Environment, llm: LLMProvider) -> bool:
    """Whether the knowledge graph is still on its way: the roadmap waits
    for it, so its stages are not titled twice."""
    return graph_service.state(session, environment, llm).state in (
        "waiting",
        "updating",
        "stale",
    )


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


def remembered(
    session: Session, environment_id: uuid.UUID, llm: LLMProvider
) -> dict[str, tuple[str, str]]:
    """Every stage title written for this environment, model and prompt, by
    stage key, the newest first to be kept."""
    found: dict[str, tuple[str, str]] = {}
    for artifact in session.scalars(
        select(GeneratedArtifact)
        .where(
            GeneratedArtifact.environment_id == environment_id,
            GeneratedArtifact.artifact_type == ARTIFACT_TYPE,
            GeneratedArtifact.status == "ready",
            GeneratedArtifact.model_name == llm.model_name,
            GeneratedArtifact.prompt_version == _prompt_id(),
        )
        .order_by(GeneratedArtifact.updated_at.desc())
    ):
        for stage in (artifact.content or {}).get("stages", []):
            found.setdefault(stage["key"], (stage["title"], stage["description"]))
    return found


def request_roadmap(
    session: Session, environment: Environment, llm: LLMProvider
) -> tuple[GeneratedArtifact | None, bool]:
    """Make sure the titles of the environment's current stages are written
    or coming. None while the graph is still on its way, or when there are
    no concepts. The same stages, model and prompt find the same artifact, so
    asking again never rewrites; a failed or abandoned one is tried again."""
    if _graph_busy(session, environment, llm):
        return None, False
    found = material(session, environment.id)
    if not found.nodes:
        return None, False
    version = found.version
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
            metadata_json={"stages": len(found.roadmap.stages)},
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
    return artifact, False


# --- asking the model ---------------------------------------------------------


def _clean(text: str, words: int) -> str | None:
    """The text with its spacing tidied, or None if it carries formatting or
    is too long to be what was asked for."""
    text = re.sub(r"[ \t]+", " ", text).strip()
    if not text or _MARKUP.search(text) or len(text.split()) > words:
        return None
    return text


def _ask(
    stages: list[tuple[str, tuple[uuid.UUID, ...]]],
    nodes: dict[uuid.UUID, rules.Node],
    llm: LLMProvider,
) -> dict[str, tuple[str, str] | None]:
    """A title and description for each stage, by key: None for a stage
    whose answer was not usable. One request for all of them."""
    template = prompting.part(*PROMPT, "stage")
    blocks = [
        template.substitute(
            number=n,
            concepts="\n".join(
                f"- {nodes[i].name}: {nodes[i].definition}" for i in stage
            ),
        )
        for n, (_, stage) in enumerate(stages, start=1)
    ]
    prompt = prompting.render(*PROMPT, stages="\n\n".join(blocks))
    answer = llm.generate_structured(prompt, answer_schema(len(stages))).value
    written: dict[str, tuple[str, str] | None] = {key: None for key, _ in stages}
    seen = set()
    for text in answer.stages:
        if text.stage in seen:  # a stage answered twice keeps its first
            continue
        seen.add(text.stage)
        title = _clean(text.title, TITLE_WORDS)
        description = _clean(text.description, DESCRIPTION_WORDS)
        if title and description and not title.lower().startswith("stage"):
            written[stages[text.stage - 1][0]] = (title, description)
    return written


def write_roadmap(
    session_factory: SessionFactory, artifact_id: uuid.UUID, llm: LLMProvider
) -> None:
    """Write the titles of a pending roadmap. Runs as a background task, one
    model task at a time. Only stages without a remembered title go to the
    model, outside any transaction."""
    changed = "The material changed before the roadmap was written."
    with ONE_AT_A_TIME:
        with session_factory() as session:
            artifact = session.get(GeneratedArtifact, artifact_id, with_for_update=True)
            if artifact is None or artifact.status != "pending":
                return
            environment = session.get(Environment, artifact.environment_id)
            found = material(session, environment.id)
            if (
                _graph_busy(session, environment, llm)
                or found.version != artifact.source_version
                or llm.model_name != artifact.model_name
            ):
                artifact.status, artifact.error = "failed", changed
                session.commit()
                return
            known = remembered(session, environment.id, llm)
            stages = list(zip(found.keys, found.roadmap.stages, strict=True))
            unseen = list({k: (k, s) for k, s in stages if k not in known}.values())
            artifact.status = "generating"
            session.commit()

        problem, written = None, {}
        try:
            written = _ask(unseen, found.nodes, llm) if unseen else {}
        except LLMError as exc:
            problem = str(exc)
        except Exception:
            logger.exception("Writing the roadmap %s failed", artifact_id)
            problem = "An unexpected error occurred while writing the roadmap."

        with session_factory() as session:
            artifact = session.get(GeneratedArtifact, artifact_id, with_for_update=True)
            if artifact is None or artifact.status != "generating":
                return
            if problem is not None:
                artifact.status, artifact.error = "failed", problem
                session.commit()
                return
            if (
                material(session, artifact.environment_id).version
                != artifact.source_version
            ):
                artifact.status, artifact.error = "failed", changed
                session.commit()
                return
            texts = {**{k: v for k, v in written.items() if v}, **known}
            artifact.content = {
                "stages": [
                    {"key": key, "title": texts[key][0], "description": texts[key][1]}
                    for key, _ in stages
                    if key in texts
                ]
            }
            artifact.status = "ready"
            artifact.metadata_json = {
                **artifact.metadata_json,
                "asked": len(unseen),
                "remembered": len(stages) - len(unseen),
                "plain": sum(1 for key, _ in stages if key not in texts),
            }
            session.commit()


def refresh_roadmap(
    session_factory: SessionFactory, environment_id: uuid.UUID, llm: LLMProvider
) -> None:
    """Bring the roadmap's titles up to date, if its stages changed. Runs as
    a background task after the knowledge graph."""
    with session_factory() as session:
        environment = session.get(Environment, environment_id)
        if environment is None:
            return
        artifact, write_now = request_roadmap(session, environment, llm)
        artifact_id = artifact.id if artifact else None
    if write_now:
        write_roadmap(session_factory, artifact_id, llm)


# --- reading the roadmap -------------------------------------------------------


def state(session: Session, environment: Environment, llm: LLMProvider) -> RoadmapState:
    """The roadmap as the material stands, with every title written so far."""
    found = material(session, environment.id)
    busy = _graph_busy(session, environment, llm)
    current = (
        _find(session, environment.id, found.version, llm.model_name)
        if found.nodes
        else None
    )
    if busy:
        label = "waiting"
    elif not found.nodes:
        label = "none"
    elif current is None:
        label = "stale"
    elif current.status in ("pending", "generating"):
        label = "updating"
    elif current.status == "failed":
        label = "failed"
    else:
        label = "up_to_date"

    texts = remembered(session, environment.id, llm)
    in_cycle = {i for cycle in found.roadmap.cycles for i in cycle.concepts}
    builds_on = defaultdict(list)
    for link in found.links:
        if link.kind == "PREREQUISITE_OF" and link.source in found.nodes:
            builds_on[link.target].append(link.source)
    place = {i: n for n, i in enumerate(i for s in found.roadmap.stages for i in s)}
    shown = {i: chunks[:EVIDENCE_SHOWN] for i, chunks in found.evidence.items()}
    citations = iter(sources.cite_all(session, [c for i in place for c in shown[i]]))
    evidence = {i: [next(citations) for _ in shown[i]] for i in place}

    def document(doc_id):
        return ConceptDocument(
            document_id=doc_id, filename=found.documents[doc_id].filename
        )

    def ref(i):
        return ConceptRef(id=i, name=found.nodes[i].name)

    stages = []
    for number, (key, stage) in enumerate(
        zip(found.keys, found.roadmap.stages, strict=True), start=1
    ):
        names = [found.nodes[i].name for i in stage]
        written = texts.get(key)
        docs = {d for i in stage for d in found.concept_documents[i]}
        stages.append(
            RoadmapStage(
                number=number,
                title=written[0] if written else rules.plain_title(names),
                description=written[1] if written else None,
                written=written is not None,
                documents=[document(d) for d in found.documents if d in docs],
                concepts=[
                    RoadmapConcept(
                        id=i,
                        name=found.nodes[i].name,
                        definition=found.nodes[i].definition,
                        builds_on=[ref(p) for p in sorted(builds_on[i], key=place.get)],
                        in_cycle=i in in_cycle,
                        documents=[document(d) for d in found.concept_documents[i]],
                        evidence=evidence[i],
                    )
                    for i in stage
                ],
            )
        )
    return RoadmapState(
        state=label,
        error=current.error if label == "failed" else None,
        stages=stages,
        cycles=[
            RoadmapCycle(concepts=[ref(i) for i in cycle.concepts])
            for cycle in found.roadmap.cycles
        ],
        updated_at=current.updated_at if current else None,
    )
