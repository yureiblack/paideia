"""Practice: items written from a concept's passages, answers, and review.

Purpose
-------
Preparing practice for a concept asks the model for four items, one of each
kind, from the concept's own passages. The backend checks every item before
keeping it (app/practice.py), and keeps an item only if the search reranker
finds its answer in the passages it cites. Items are written on request, in
the background, one concept at a time; the same passages, model and prompt
never write twice. When a concept's passages change, its items stop being
practised, and preparing it again writes new ones and retires the old, kept
with their attempts (decision record 14).

Multiple choice and true/false answers are checked against the stored key;
short answers and flashcards are marked by the learner after seeing the
answer. Every answer is recorded. A concept's learner state, and when it
comes back for review, are worked out from those answers (app/learner.py);
each item's own Leitner box only decides which of a concept's items come
first.
"""

import hashlib
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import learner, prompting
from app import practice as rules
from app.db import SessionFactory
from app.llm import ONE_AT_A_TIME, LLMError, LLMProvider
from app.models import (
    Attempt,
    Concept,
    ConceptEvidence,
    Document,
    DocumentChunk,
    Environment,
    GeneratedArtifact,
    LearningItem,
    LearningItemSource,
    ReviewSchedule,
)
from app.reranking import Reranker
from app.schemas import (
    AttemptCreate,
    AttemptResult,
    ConceptNote,
    ConceptRef,
    PracticeConcept,
    PracticeItem,
    PracticeOverview,
)
from app.services import roadmap as roadmap_service
from app.services import sources, summaries

logger = logging.getLogger(__name__)

ARTIFACT_TYPE = "practice_set"
PROMPT = ("practice_items", "v1")
MIN_SUPPORT = 0.5  # the reranker's score of an answer against its passages
CHANGED = "The material changed before the practice items were written."


class NotPractised(Exception):
    """The item was replaced, or its material changed: it is no longer
    practised."""


def _prompt_id() -> str:
    return "/".join(PROMPT)


def answer_schema(n: int) -> type[BaseModel]:
    """One item of each kind, each citing 1 to 3 of the n passages. The
    limits here are looser than the checks after, so an overlong answer is
    refused whole rather than cut off mid-sentence (decision record 08)."""
    sources_ = Annotated[
        list[Annotated[int, Field(ge=1, le=n)]], Field(min_length=1, max_length=3)
    ]

    def text(limit: int):
        return Field(min_length=1, max_length=limit * 3 // 2)

    class ShortAnswer(BaseModel):
        question: str = text(rules.QUESTION_CHARS)
        answer: str = text(rules.ANSWER_CHARS)
        sources: sources_

    class MultipleChoice(BaseModel):
        question: str = text(rules.QUESTION_CHARS)
        options: list[
            Annotated[str, Field(min_length=1, max_length=rules.OPTION_CHARS * 3 // 2)]
        ] = Field(min_length=rules.OPTIONS, max_length=rules.OPTIONS)
        correct: int = Field(ge=1, le=rules.OPTIONS)
        explanation: str = text(rules.ANSWER_CHARS)
        sources: sources_

    class TrueFalse(BaseModel):
        statement: str = text(rules.QUESTION_CHARS)
        true: bool
        explanation: str = text(rules.ANSWER_CHARS)
        sources: sources_

    class Flashcard(BaseModel):
        front: str = text(rules.FRONT_CHARS)
        back: str = text(rules.ANSWER_CHARS)
        sources: sources_

    class Answer(BaseModel):
        short_answer: ShortAnswer
        multiple_choice: MultipleChoice
        true_false: TrueFalse
        flashcard: Flashcard

    return Answer


# --- what an item is written from ------------------------------------------


def evidence(session: Session, concept_ids) -> dict[uuid.UUID, list[DocumentChunk]]:
    """Each concept's passages, in reading order: the order the documents
    were added, then their place in the document."""
    found: dict[uuid.UUID, list[DocumentChunk]] = defaultdict(list)
    for concept_id, chunk in session.execute(
        select(ConceptEvidence.concept_id, DocumentChunk)
        .join(DocumentChunk, DocumentChunk.id == ConceptEvidence.chunk_id)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(ConceptEvidence.concept_id.in_(list(concept_ids)))
        .order_by(Document.created_at, Document.id, DocumentChunk.ordinal)
    ):
        found[concept_id].append(chunk)
    return found


def evidence_key(concept: Concept, chunks: list[DocumentChunk]) -> str:
    """The concept as the model sees it: its name, definition and passages.
    Items whose key is not the concept's current one are not practised."""
    text = "\n".join(
        [concept.normalized_name, concept.definition, *(c.content_hash for c in chunks)]
    )
    return hashlib.sha256(text.encode()).hexdigest()


def _find(session: Session, environment_id: uuid.UUID, key: str, model: str):
    return session.scalar(
        select(GeneratedArtifact).where(
            GeneratedArtifact.environment_id == environment_id,
            GeneratedArtifact.document_id.is_(None),
            GeneratedArtifact.artifact_type == ARTIFACT_TYPE,
            GeneratedArtifact.source_version == key,
            GeneratedArtifact.model_name == model,
            GeneratedArtifact.prompt_version == _prompt_id(),
        )
    )


def request_practice(
    session: Session, concept: Concept, llm: LLMProvider
) -> tuple[GeneratedArtifact | None, bool]:
    """Make sure the concept's items for its current passages are written or
    coming. None for a concept without passages. A failed or abandoned
    generation is tried again; a finished one is never repeated."""
    chunks = evidence(session, [concept.id])[concept.id]
    if not chunks:
        return None, False
    key = evidence_key(concept, chunks)
    artifact = _find(session, concept.environment_id, key, llm.model_name)
    if artifact is None:
        artifact = GeneratedArtifact(
            environment_id=concept.environment_id,
            document_id=None,
            artifact_type=ARTIFACT_TYPE,
            source_version=key,
            model_name=llm.model_name,
            prompt_version=_prompt_id(),
            status="pending",
            metadata_json={"concept_id": str(concept.id)},
        )
        session.add(artifact)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            return _find(session, concept.environment_id, key, llm.model_name), False
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


def prepare(
    session: Session, environment: Environment, concept_ids, llm: LLMProvider
) -> list[uuid.UUID]:
    """Ask for the items of these concepts of the environment. The ids of
    the generations to write now, in the order asked."""
    wanted = list(dict.fromkeys(concept_ids))
    concepts = {
        c.id: c
        for c in session.scalars(
            select(Concept).where(
                Concept.environment_id == environment.id, Concept.id.in_(wanted)
            )
        )
    }
    pending = []
    for concept_id in wanted:
        if concept_id in concepts:
            artifact, write_now = request_practice(session, concepts[concept_id], llm)
            if write_now:
                pending.append(artifact.id)
    return pending


# --- writing the items --------------------------------------------------------


@dataclass(frozen=True)
class _Passage:
    number: int
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    text: str


def _write(
    name: str,
    definition: str,
    passages: list[_Passage],
    key: str,
    llm: LLMProvider,
    reranker: Reranker,
) -> tuple[list[tuple[rules.Draft, float]], dict[str, str]]:
    """The items the model wrote that pass every check, with their support,
    and why each other one was dropped, by kind."""
    truth = rules.wanted_truth(key)
    prompt = prompting.render(
        *PROMPT,
        concept=name,
        definition=definition,
        passages="\n\n".join(f"[{p.number}] {p.text}" for p in passages),
        truth="true" if truth else "false",
    )
    answer = llm.generate_structured(prompt, answer_schema(len(passages))).value
    sa, mc, tf, fc = (
        answer.short_answer,
        answer.multiple_choice,
        answer.true_false,
        answer.flashcard,
    )
    candidates = {
        "short_answer": rules.short_answer(sa.question, sa.answer, sa.sources),
        "multiple_choice": rules.multiple_choice(
            mc.question, mc.options, mc.correct, mc.explanation, mc.sources, key
        ),
        "true_false": rules.true_false(
            tf.statement, tf.true, tf.explanation, tf.sources, truth
        ),
        "flashcard": rules.flashcard(fc.front, fc.back, fc.sources),
    }
    texts = {p.number: p.text for p in passages}
    kept, dropped = [], {}
    for kind, draft in candidates.items():
        if isinstance(draft, str):
            dropped[kind] = draft
            continue
        support = max(
            reranker.score(
                draft.claim, [texts[n] for n in dict.fromkeys(draft.sources)]
            )
        )
        if support < MIN_SUPPORT:
            dropped[kind] = f"not supported by its passages ({support:.2f})"
            continue
        kept.append((draft, support))
    return kept, dropped


def write_practice(
    session_factory: SessionFactory,
    artifact_id: uuid.UUID,
    llm: LLMProvider,
    reranker: Reranker,
) -> None:
    """Write a pending generation's items. Runs as a background task, one
    model task at a time; the model is asked outside any transaction, and
    the new items replace the concept's old ones in one."""
    with ONE_AT_A_TIME:
        with session_factory() as session:
            artifact = session.get(GeneratedArtifact, artifact_id, with_for_update=True)
            if artifact is None or artifact.status != "pending":
                return
            concept = session.get(
                Concept, uuid.UUID(artifact.metadata_json["concept_id"])
            )
            chunks = evidence(session, [concept.id])[concept.id] if concept else []
            if (
                concept is None
                or not chunks
                or evidence_key(concept, chunks) != artifact.source_version
                or llm.model_name != artifact.model_name
            ):
                artifact.status, artifact.error = "failed", CHANGED
                session.commit()
                return
            name, definition = concept.name, concept.definition
            passages = [
                _Passage(n, c.id, c.document_id, sources.with_heading(c))
                for n, c in enumerate(chunks, start=1)
            ]
            artifact.status = "generating"
            session.commit()

        problem, kept, dropped = None, [], {}
        try:
            kept, dropped = _write(
                name, definition, passages, artifact.source_version, llm, reranker
            )
        except LLMError as exc:
            problem = str(exc)
        except Exception:
            logger.exception("Writing practice items %s failed", artifact_id)
            problem = "An unexpected error occurred while writing practice items."
        if problem is None and not kept:
            problem = "No item passed the checks: " + "; ".join(
                f"{kind.replace('_', ' ')}: {why}" for kind, why in dropped.items()
            )

        with session_factory() as session:
            artifact = session.get(GeneratedArtifact, artifact_id, with_for_update=True)
            if artifact is None or artifact.status != "generating":
                return
            concept = session.get(
                Concept, uuid.UUID(artifact.metadata_json["concept_id"])
            )
            chunks = evidence(session, [concept.id])[concept.id] if concept else []
            if problem is None and (
                concept is None
                or evidence_key(concept, chunks) != artifact.source_version
            ):
                problem = CHANGED
            if problem is not None:
                artifact.status, artifact.error = "failed", problem
                session.commit()
                return
            now = datetime.now(UTC)
            session.execute(
                update(LearningItem)
                .where(
                    LearningItem.concept_id == concept.id,
                    LearningItem.retired_at.is_(None),
                )
                .values(retired_at=now)
            )
            by_number = {p.number: p for p in passages}
            for draft, support in kept:
                item = LearningItem(
                    environment_id=concept.environment_id,
                    concept_id=concept.id,
                    kind=draft.kind,
                    content=draft.content,
                    difficulty=draft.difficulty,
                    evidence_key=artifact.source_version,
                    model_name=llm.model_name,
                    prompt_version=_prompt_id(),
                    metadata_json={
                        "support": round(support, 3),
                        "generation_id": str(artifact.id),
                    },
                )
                session.add(item)
                session.flush()
                for number in dict.fromkeys(draft.sources):
                    passage = by_number[number]
                    session.add(
                        LearningItemSource(
                            item_id=item.id,
                            chunk_id=passage.chunk_id,
                            document_id=passage.document_id,
                        )
                    )
                session.add(ReviewSchedule(item_id=item.id, box=0, due_at=now))
            artifact.status = "ready"
            artifact.metadata_json = {
                **artifact.metadata_json,
                "kept": len(kept),
                "dropped": dropped,
            }
            session.commit()


def write_all(
    session_factory: SessionFactory,
    artifact_ids: list[uuid.UUID],
    llm: LLMProvider,
    reranker: Reranker,
) -> None:
    """Write several generations, one after another. A background task."""
    for artifact_id in artifact_ids:
        write_practice(session_factory, artifact_id, llm, reranker)


# --- practising -----------------------------------------------------------------


def _current_keys(session: Session, concepts: list[Concept]) -> dict[uuid.UUID, str]:
    chunks = evidence(session, [c.id for c in concepts])
    return {c.id: evidence_key(c, chunks[c.id]) for c in concepts if chunks[c.id]}


def _practised(session: Session, environment_id: uuid.UUID, concept_ids=None):
    """The items practised now, with their schedules: not retired, and
    written from their concept's current passages."""
    query = select(Concept).where(Concept.environment_id == environment_id)
    if concept_ids is not None:
        query = query.where(Concept.id.in_(list(concept_ids)))
    concepts = {c.id: c for c in session.scalars(query)}
    keys = _current_keys(session, list(concepts.values()))
    rows = session.execute(
        select(LearningItem, ReviewSchedule)
        .join(ReviewSchedule, ReviewSchedule.item_id == LearningItem.id)
        .where(
            LearningItem.environment_id == environment_id,
            LearningItem.concept_id.in_(list(concepts)),
            LearningItem.retired_at.is_(None),
        )
    ).all()
    current = [(i, s) for i, s in rows if keys.get(i.concept_id) == i.evidence_key]
    stale = {i.concept_id for i, _ in rows if keys.get(i.concept_id) != i.evidence_key}
    return concepts, keys, current, stale


def answers(
    session: Session, environment_id: uuid.UUID
) -> dict[uuid.UUID, list[learner.Answer]]:
    """Every answer given in the environment, by concept, in the order they
    were made: the answers to all of a concept's items, retired ones too."""
    found: dict[uuid.UUID, list[learner.Answer]] = defaultdict(list)
    for concept_id, answered_at, correct in session.execute(
        select(LearningItem.concept_id, Attempt.answered_at, Attempt.correct)
        .join(LearningItem, LearningItem.id == Attempt.item_id)
        .where(LearningItem.environment_id == environment_id)
        .order_by(Attempt.answered_at, Attempt.id)
    ):
        found[concept_id].append(learner.Answer(answered_at, correct))
    return found


def learner_states(
    session: Session, environment_id: uuid.UUID
) -> dict[uuid.UUID, learner.State]:
    """Each concept's learner state, from its answers (decision record 15)."""
    return {
        concept_id: learner.replay(given)
        for concept_id, given in answers(session, environment_id).items()
    }


def overview(
    session: Session,
    environment: Environment,
    llm: LLMProvider,
    now: datetime | None = None,
    until: datetime | None = None,
) -> PracticeOverview:
    """Practice at a glance. until is the end of the learner's day: concepts
    due by then count as due today."""
    now = now or datetime.now(UTC)
    until = max(until or now, now)
    concepts, keys, current, stale = _practised(session, environment.id)
    generations = {
        a.source_version: a
        for a in session.scalars(
            select(GeneratedArtifact).where(
                GeneratedArtifact.environment_id == environment.id,
                GeneratedArtifact.artifact_type == ARTIFACT_TYPE,
                GeneratedArtifact.source_version.in_(list(keys.values())),
                GeneratedArtifact.model_name == llm.model_name,
                GeneratedArtifact.prompt_version == _prompt_id(),
            )
        )
    }
    states = learner_states(session, environment.id)
    items = defaultdict(int)
    for item, _ in current:
        items[item.concept_id] += 1
    rows = []
    for concept in sorted(concepts.values(), key=lambda c: c.normalized_name):
        generation = generations.get(keys.get(concept.id))
        if generation is not None:
            state = generation.status
        else:
            state = "outdated" if concept.id in stale else "none"
        known = states.get(concept.id, learner.State())
        rows.append(
            PracticeConcept(
                concept_id=concept.id,
                name=concept.name,
                state=state,
                error=generation.error if state == "failed" else None,
                items=items[concept.id],
                review=learner.review(known, until) if items[concept.id] else None,
                exposures=known.exposures,
                recalled=known.recalled,
                failed=known.failed,
                last_attempted_at=known.last_attempted_at,
                last_recalled_at=known.last_recalled_at,
                gap_days=known.gap_days,
                next_review_at=known.next_review_at,
                attention=learner.attention(known),
            )
        )
    practised = [r for r in rows if r.review is not None]
    needing = sorted(
        (r for r in practised if r.attention),
        key=lambda r: r.last_attempted_at,
        reverse=True,
    )
    strong = sorted(
        (
            r
            for r in practised
            if learner.strong(states.get(r.concept_id, learner.State()))
        ),
        key=lambda r: (-r.gap_days, -r.last_recalled_at.timestamp()),
    )
    later = [r.next_review_at for r in practised if r.review == "scheduled"]
    return PracticeOverview(
        items=len(current),
        due_concepts=sum(r.review == "due" for r in practised),
        new_concepts=sum(r.review == "new" for r in practised),
        next_review_at=min(later) if later else None,
        concepts=rows,
        needs_attention=[
            ConceptNote(concept_id=r.concept_id, name=r.name, note=r.attention)
            for r in needing
        ],
        recently_strong=[
            ConceptNote(
                concept_id=r.concept_id,
                name=r.name,
                note=f"Recalled; next review in {r.gap_days} days.",
            )
            for r in strong[:5]
        ],
    )


def _shown(
    item: LearningItem, schedule: ReviewSchedule, concept: Concept
) -> PracticeItem:
    content = item.content
    prompt = content.get("question") or content.get("statement") or content["front"]
    self_marked = item.kind in ("short_answer", "flashcard")
    return PracticeItem(
        id=item.id,
        concept=ConceptRef(id=concept.id, name=concept.name),
        kind=item.kind,
        difficulty=item.difficulty,
        prompt=prompt,
        options=content.get("options"),
        answer=(content.get("answer") or content.get("back")) if self_marked else None,
        box=schedule.box,
        due_at=schedule.due_at,
    )


def session_items(
    session: Session,
    environment: Environment,
    concept_ids=None,
    now: datetime | None = None,
    until: datetime | None = None,
) -> list[PracticeItem]:
    """A practice session of at most ten items, interleaved. Without
    concept_ids: the concepts due by until (the end of the learner's day),
    overdue first, then new ones, two items each (decision record 15). With
    concept_ids (a stage): those concepts' items, due ones first."""
    now = now or datetime.now(UTC)
    until = max(until or now, now)
    concepts, _, current, _ = _practised(session, environment.id, concept_ids)
    found = roadmap_service.material(session, environment.id)
    place = {i: n for n, i in enumerate(i for s in found.roadmap.stages for i in s)}
    by_id = {item.id: (item, schedule) for item, schedule in current}
    if concept_ids is None:
        states = learner_states(session, environment.id)
        practised = {item.concept_id for item, _ in current}
        chosen_ids = [
            option.id
            for option in learner.session(
                [
                    (c, states.get(c, learner.State()), place.get(c, len(place)))
                    for c in practised
                ],
                [
                    learner.Option(
                        item.id,
                        item.concept_id,
                        item.kind,
                        schedule.box,
                        schedule.last_answered_at,
                    )
                    for item, schedule in current
                ],
                until,
            )
        ]
    else:
        chosen_ids = [
            c.id
            for c in rules.pick(
                [
                    rules.Candidate(
                        item.id,
                        item.concept_id,
                        schedule.due_at,
                        place.get(item.concept_id, len(place)),
                        item.difficulty,
                    )
                    for item, schedule in current
                ],
                now,
                due_only=False,
            )
        ]
    return [_shown(*by_id[i], concepts[by_id[i][0].concept_id]) for i in chosen_ids]


def answer(
    session: Session,
    item: LearningItem,
    data: AttemptCreate,
    now: datetime | None = None,
) -> AttemptResult:
    """Record an answer, grade it, and move the item between boxes. Raises
    NotPractised for an item no longer practised, ValueError for an answer
    of the wrong kind."""
    now = now or datetime.now(UTC)
    concept = session.get(Concept, item.concept_id)
    key = _current_keys(session, [concept]).get(concept.id)
    if item.retired_at is not None or item.evidence_key != key:
        raise NotPractised("This item was replaced and is no longer practised.")
    content, kind = item.content, item.kind
    if kind == "multiple_choice":
        if data.choice is None:
            raise ValueError("A multiple-choice answer needs a choice.")
        correct, graded_by = data.choice == content["correct"], "key"
        right, explanation = (
            content["options"][content["correct"]],
            content["explanation"],
        )
        response = {"choice": data.choice}
    elif kind == "true_false":
        if data.truth is None:
            raise ValueError("A true/false answer needs true or false.")
        correct, graded_by = data.truth == content["truth"], "key"
        right, explanation = (
            ("True" if content["truth"] else "False"),
            content["explanation"],
        )
        response = {"truth": data.truth}
    else:
        if data.knew is None:
            raise ValueError("Mark whether you knew it, once the answer is shown.")
        correct, graded_by = data.knew, "learner"
        right, explanation = content.get("answer") or content["back"], None
        response = {"knew": data.knew, **({"text": data.text} if data.text else {})}
    session.add(
        Attempt(
            item_id=item.id,
            answered_at=now,
            response=response,
            correct=correct,
            graded_by=graded_by,
            seconds=data.seconds,
        )
    )
    schedule = session.get(ReviewSchedule, item.id)
    if schedule is None:
        schedule = ReviewSchedule(item_id=item.id, box=0, due_at=now)
        session.add(schedule)
    schedule.box, schedule.due_at = rules.schedule(schedule.box, correct, now)
    schedule.last_answered_at = now
    chunks = list(
        session.scalars(
            select(DocumentChunk)
            .join(LearningItemSource, LearningItemSource.chunk_id == DocumentChunk.id)
            .where(LearningItemSource.item_id == item.id)
            .order_by(DocumentChunk.document_id, DocumentChunk.ordinal)
        )
    )
    session.flush()
    state = learner_states(session, item.environment_id)[item.concept_id]
    result = AttemptResult(
        correct=correct,
        graded_by=graded_by,
        answer=right,
        explanation=explanation,
        sources=sources.cite_all(session, chunks),
        box=schedule.box,
        due_at=state.next_review_at,
        gap_days=state.gap_days,
    )
    session.commit()
    return result
