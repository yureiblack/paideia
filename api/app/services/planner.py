"""Today's study plan for an environment.

Purpose
-------
Gathers what the planner needs (app/planner.py) and turns its plan into the
API's shape. Everything comes from what is already stored: each concept's
learner state and practice items (Phase 15 and 14), the roadmap (Phase 13),
the documents with their dates and summaries, and the learner's own answer
times. Nothing is stored, and no model is asked: the plan is worked out
afresh whenever it is read (decision record 16).
"""

import uuid
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import planner
from app.llm import LLMProvider
from app.models import (
    Attempt,
    Document,
    DocumentConcept,
    Environment,
    LearningItem,
)
from app.schemas import ConceptDocument, ConceptRef, PlanSession, StudyPlan
from app.services import practice, summaries
from app.services import roadmap as roadmap_service


def _summary_words(
    session: Session, document: Document, llm: LLMProvider
) -> int | None:
    summary = summaries.current_summary(session, document, llm)
    if summary is None or summary.status != "ready" or not summary.content:
        return None
    text = [summary.content.get("overview") or ""]
    text += [point["text"] for point in summary.content.get("key_points", [])]
    return sum(len(t.split()) for t in text) or None


def _timed(session: Session, environment_id: uuid.UUID) -> dict[str, list[float]]:
    timed: dict[str, list[float]] = defaultdict(list)
    for kind, seconds in session.execute(
        select(LearningItem.kind, Attempt.seconds)
        .join(LearningItem, LearningItem.id == Attempt.item_id)
        .where(
            LearningItem.environment_id == environment_id,
            Attempt.seconds.is_not(None),
        )
    ):
        timed[kind].append(seconds)
    return timed


def plan(
    session: Session,
    environment: Environment,
    llm: LLMProvider,
    now: datetime | None = None,
    until: datetime | None = None,
    budget: int | None = None,
) -> StudyPlan:
    """Today's plan. until is the end of the learner's day; budget, in
    minutes, is optional."""
    now = now or datetime.now(UTC)
    until = max(until or now, now)
    view = practice.overview(session, environment, llm, now=now, until=until)
    road = roadmap_service.state(session, environment, llm)
    place = {
        c.id: n
        for n, c in enumerate(c for stage in road.stages for c in stage.concepts)
    }
    _, _, current, _ = practice._practised(session, environment.id)
    kinds: dict[uuid.UUID, set[str]] = defaultdict(set)
    for item, _ in current:
        kinds[item.concept_id].add(item.kind)
    chunks = practice.evidence(session, [c.concept_id for c in view.concepts])
    concepts = [
        planner.Concept(
            id=c.concept_id,
            name=c.name,
            place=place.get(c.concept_id, len(place)),
            review=c.review,
            attention=c.attention,
            exposures=c.exposures,
            gap_days=c.gap_days,
            kinds=tuple(sorted(kinds[c.concept_id])),
            passages=tuple(
                (chunk.id, len(chunk.content.split())) for chunk in chunks[c.concept_id]
            ),
        )
        for c in view.concepts
    ]
    stages = [
        planner.Stage(s.number, s.title, tuple(c.id for c in s.concepts))
        for s in road.stages
    ]
    links: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    for document_id, concept_id in session.execute(
        select(DocumentConcept.document_id, DocumentConcept.concept_id)
        .join(Document, Document.id == DocumentConcept.document_id)
        .where(Document.environment_id == environment.id)
    ):
        links[document_id].append(concept_id)
    documents = {
        d.id: d
        for d in session.scalars(
            select(Document).where(
                Document.environment_id == environment.id, Document.status == "ready"
            )
        )
    }
    built = planner.build(
        concepts,
        stages,
        [
            planner.Document(
                id=d.id,
                filename=d.filename,
                added_at=d.created_at,
                summary_words=_summary_words(session, d, llm),
                concepts=tuple(
                    sorted(links[d.id], key=lambda i: place.get(i, len(place)))
                ),
            )
            for d in documents.values()
        ],
        planner.pace(_timed(session, environment.id)),
        now,
        budget,
    )
    names = {c.concept_id: c.name for c in view.concepts}

    def shown(s: planner.Session) -> PlanSession:
        document = documents.get(s.document) if s.document else None
        return PlanSession(
            kind=s.kind,
            title=s.title,
            minutes=s.minutes,
            rationale=s.rationale,
            concepts=[ConceptRef(id=i, name=names[i]) for i in s.concepts],
            stage=s.stage,
            document=ConceptDocument(
                document_id=document.id, filename=document.filename
            )
            if document
            else None,
            needs_preparing=s.needs_preparing,
        )

    return StudyPlan(
        sessions=[shown(s) for s in built.sessions],
        later=[shown(s) for s in built.later],
        minutes=built.minutes,
        budget=budget,
    )
