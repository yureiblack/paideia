"""Tests for practice in app/services/practice.py, with mocked model answers.

Purpose: items are written from a concept's own passages and checked before
anything is stored; items failing a check, or not supported by their
passages, are dropped and counted; the same passages never write twice;
changed material retires items, kept with their attempts; answers are
graded by the key or by the learner and move items between boxes; sessions
hold due items, interleaved, or a stage's items.
"""

import itertools
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import practice as rules
from app.models import (
    Attempt,
    Concept,
    GeneratedArtifact,
    LearningItem,
    LearningItemSource,
    ReviewSchedule,
)
from app.schemas import AttemptCreate
from app.services import practice
from tests.fakes import FailingProvider, FakeReranker, practice_answer
from tests.test_concepts import add, chunks_of, concept, environment, extract
from tests.test_graph import (
    RULES,
    SCHEDULING,
    SCHEDULING_CONCEPTS,
    SYNCHRONIZATION,
    Deciding,
)

NOW = datetime(2026, 11, 11, 9, tzinfo=UTC)


class Practising(Deciding):
    """Deciding, whose practice answers come from items(prompt): by default
    the stand-in's, which pass every check."""

    def __init__(self, *args, items=practice_answer, **kwargs):
        super().__init__(*args, **kwargs)
        self.items = items

    def _answer(self, prompt, schema):
        if prompt.name == "practice_items":
            return self.items(prompt)
        return super()._answer(prompt, schema)

    def practice_calls(self):
        return [p for p, _ in self.calls if p.name == "practice_items"]


class LowScores(FakeReranker):
    def score(self, query, passages):
        return [0.2 for _ in passages]


def scheduling(session, session_factory, llm):
    env = environment(session)
    doc = add(session, session_factory, env, "scheduling.pdf", SCHEDULING)
    extract(session, session_factory, doc, llm)
    return env, doc


def named(session, env, name) -> Concept:
    return session.scalar(
        select(Concept).where(Concept.environment_id == env.id, Concept.name == name)
    )


def prepare(session, session_factory, env, names, llm, reranker=None):
    ids = [named(session, env, n).id for n in names]
    pending = practice.prepare(session, env, ids, llm)
    practice.write_all(session_factory, pending, llm, reranker or FakeReranker())
    session.expire_all()
    return pending


def items_of(session, concept_obj, retired=False) -> dict[str, LearningItem]:
    query = select(LearningItem).where(LearningItem.concept_id == concept_obj.id)
    query = query.where(
        LearningItem.retired_at.is_not(None)
        if retired
        else LearningItem.retired_at.is_(None)
    )
    return {i.kind: i for i in session.scalars(query)}


def test_preparing_a_concept_writes_four_checked_items_from_its_passages(
    session: Session, session_factory
):
    llm = Practising(RULES, [SCHEDULING_CONCEPTS])
    env, doc = scheduling(session, session_factory, llm)

    [generation_id] = prepare(session, session_factory, env, ["Thread"], llm)

    [prompt] = llm.practice_calls()
    assert "Concept: Thread: The meaning of Thread." in prompt.user
    assert (
        "[1] Threads\n\nA thread is a sequence of execution within a process."
        in prompt.user
    )
    thread = named(session, env, "Thread")
    items = items_of(session, thread)
    assert set(items) == set(rules.KINDS)
    assert {k: i.difficulty for k, i in items.items()} == rules.DIFFICULTY
    first_chunk = chunks_of(session, doc)[0]
    for item in items.values():
        [source] = session.scalars(
            select(LearningItemSource).where(LearningItemSource.item_id == item.id)
        )
        assert source.chunk_id == first_chunk.id
        assert item.metadata_json["generation_id"] == str(generation_id)
        assert item.metadata_json["support"] >= practice.MIN_SUPPORT
        assert (item.model_name, item.prompt_version) == (
            "mock-llm",
            "practice_items/v1",
        )
        assert session.get(ReviewSchedule, item.id).box == 0
    generation = session.get(GeneratedArtifact, generation_id)
    assert (generation.status, generation.metadata_json["kept"]) == ("ready", 4)
    mc = items["multiple_choice"].content
    assert mc["options"][mc["correct"]].startswith("Threads A thread is")
    truth = rules.wanted_truth(generation.source_version)
    assert items["true_false"].content["truth"] is truth
    assert f"that is {'true' if truth else 'false'} according to" in prompt.user


def test_preparing_again_writes_nothing(session: Session, session_factory):
    llm = Practising(RULES, [SCHEDULING_CONCEPTS])
    env, _ = scheduling(session, session_factory, llm)
    prepare(session, session_factory, env, ["Thread"], llm)

    assert prepare(session, session_factory, env, ["Thread"], llm) == []
    assert len(llm.practice_calls()) == 1


def test_items_failing_a_check_are_dropped_and_counted(
    session: Session, session_factory
):
    def flawed(prompt):
        answer = practice_answer(prompt)
        answer["short_answer"]["question"] = "What does passage 1 describe?"
        answer["multiple_choice"]["options"][1] = answer["multiple_choice"]["options"][
            0
        ]
        answer["true_false"]["true"] = not answer["true_false"]["true"]
        return answer

    llm = Practising(RULES, [SCHEDULING_CONCEPTS], items=flawed)
    env, _ = scheduling(session, session_factory, llm)

    [generation_id] = prepare(session, session_factory, env, ["Thread"], llm)

    assert set(items_of(session, named(session, env, "Thread"))) == {"flashcard"}
    assert session.get(GeneratedArtifact, generation_id).metadata_json["dropped"] == {
        "short_answer": "formatting, a mention of passages, or too long",
        "multiple_choice": "options repeat",
        "true_false": "not the truth asked for",
    }


def test_items_their_passages_do_not_support_are_never_stored(
    session: Session, session_factory
):
    llm = Practising(RULES, [SCHEDULING_CONCEPTS])
    env, _ = scheduling(session, session_factory, llm)

    [generation_id] = prepare(
        session, session_factory, env, ["Thread"], llm, LowScores()
    )

    generation = session.get(GeneratedArtifact, generation_id)
    assert generation.status == "failed"
    assert generation.error.startswith("No item passed the checks: short answer: not ")
    assert "(0.20)" in generation.error
    assert session.scalar(select(func.count()).select_from(LearningItem)) == 0


def test_a_failure_is_recorded_and_preparing_again_retries(
    session: Session, session_factory
):
    llm = Practising(RULES, [SCHEDULING_CONCEPTS])
    env, _ = scheduling(session, session_factory, llm)

    prepare(session, session_factory, env, ["Thread"], FailingProvider())
    failed = practice.overview(session, env, llm)
    retried = prepare(session, session_factory, env, ["Thread"], llm)

    thread_state = next(c for c in failed.concepts if c.name == "Thread")
    assert (thread_state.state, thread_state.error) == (
        "failed",
        "Could not reach Ollama. Is it running?",
    )
    assert len(retried) == 1
    assert len(items_of(session, named(session, env, "Thread"))) == 4


def test_changed_material_retires_items_and_keeps_their_attempts(
    session: Session, session_factory
):
    llm = Practising(RULES, [SCHEDULING_CONCEPTS, [concept("Thread", [1])]])
    env, _ = scheduling(session, session_factory, llm)
    prepare(session, session_factory, env, ["Thread"], llm)
    thread = named(session, env, "Thread")
    old = items_of(session, thread)["flashcard"]
    practice.answer(session, old, AttemptCreate(knew=True), NOW)

    # A second lecture explains threads too: Thread's passages change.
    sync = add(session, session_factory, env, "sync.pdf", SYNCHRONIZATION)
    extract(session, session_factory, sync, llm)
    session.expire_all()
    outdated = practice.overview(session, env, llm)

    state = next(c for c in outdated.concepts if c.name == "Thread")
    assert (state.state, state.items) == ("outdated", 0)
    assert practice.session_items(session, env) == []
    with pytest.raises(practice.NotPractised):
        practice.answer(session, old, AttemptCreate(knew=True), NOW)

    prepare(session, session_factory, env, ["Thread"], llm)

    assert len(items_of(session, thread)) == 4
    assert old.id in {i.id for i in items_of(session, thread, retired=True).values()}
    assert session.scalar(select(func.count()).where(Attempt.item_id == old.id)) == 1
    assert (
        next(
            c
            for c in practice.overview(session, env, llm).concepts
            if c.name == "Thread"
        ).state
        == "ready"
    )


def test_answers_are_graded_by_the_key_or_by_the_learner(
    session: Session, session_factory
):
    llm = Practising(RULES, [SCHEDULING_CONCEPTS])
    env, doc = scheduling(session, session_factory, llm)
    prepare(session, session_factory, env, ["Thread"], llm)
    items = items_of(session, named(session, env, "Thread"))
    mc, tf = items["multiple_choice"], items["true_false"]
    wrong = (mc.content["correct"] + 1) % 4

    missed = practice.answer(session, mc, AttemptCreate(choice=wrong, seconds=4.5), NOW)
    right = practice.answer(session, tf, AttemptCreate(truth=tf.content["truth"]), NOW)
    knew = practice.answer(session, items["flashcard"], AttemptCreate(knew=True), NOW)
    not_yet = practice.answer(
        session,
        items["short_answer"],
        AttemptCreate(knew=False, text="A process."),
        NOW,
    )

    assert (missed.correct, missed.graded_by) == (False, "key")
    assert missed.answer == mc.content["options"][mc.content["correct"]]
    assert missed.explanation == mc.content["explanation"]
    assert [c.chunk_id for c in missed.sources] == [chunks_of(session, doc)[0].id]
    assert (right.correct, right.graded_by, right.answer) == (
        True,
        "key",
        "True" if tf.content["truth"] else "False",
    )
    assert (knew.correct, knew.graded_by, knew.explanation) == (True, "learner", None)
    assert knew.answer == items["flashcard"].content["back"]
    assert (not_yet.correct, not_yet.box, not_yet.due_at) == (
        False,
        1,
        NOW + timedelta(days=1),
    )
    attempts = {
        a.item_id: a
        for a in session.scalars(select(Attempt).where(Attempt.answered_at == NOW))
    }
    assert attempts[mc.id].response == {"choice": wrong}
    assert attempts[mc.id].seconds == 4.5
    assert attempts[items["short_answer"].id].response == {
        "knew": False,
        "text": "A process.",
    }
    with pytest.raises(ValueError):
        practice.answer(session, mc, AttemptCreate(knew=True), NOW)


def test_review_moves_items_up_the_boxes(session: Session, session_factory):
    llm = Practising(RULES, [SCHEDULING_CONCEPTS])
    env, _ = scheduling(session, session_factory, llm)
    prepare(session, session_factory, env, ["Thread"], llm)
    card = items_of(session, named(session, env, "Thread"))["flashcard"]

    boxes = []
    for days in (0, 1, 3):
        result = practice.answer(
            session, card, AttemptCreate(knew=True), NOW + timedelta(days=days)
        )
        boxes.append((result.box, result.due_at))

    assert boxes == [
        (1, NOW + timedelta(days=1)),
        (2, NOW + timedelta(days=3)),
        (3, NOW + timedelta(days=7)),
    ]


def test_a_session_holds_due_items_interleaved_and_a_stage_holds_all(
    session: Session, session_factory
):
    llm = Practising(RULES, [SCHEDULING_CONCEPTS])
    env, _ = scheduling(session, session_factory, llm)
    names = ["Thread", "Round Robin", "Time Quantum"]
    prepare(session, session_factory, env, names, llm)
    later = datetime.now(UTC) + timedelta(minutes=1)

    due = practice.session_items(session, env, now=later)

    assert len(due) == rules.SESSION_SIZE
    assert all(a.concept.id != b.concept.id for a, b in itertools.pairwise(due))
    assert all(
        i.answer is None for i in due if i.kind in ("multiple_choice", "true_false")
    )
    for item in due[:3]:
        practice.answer(
            session,
            session.get(LearningItem, item.id),
            AttemptCreate(knew=True, choice=0, truth=True),
            later,
        )
    answered = {i.id for i in due[:3]}
    assert answered.isdisjoint(
        i.id for i in practice.session_items(session, env, now=later)
    )
    thread = named(session, env, "Thread")
    stage = practice.session_items(session, env, [thread.id], now=later)
    assert {i.concept.name for i in stage} == {"Thread"}
    assert len(stage) == 4  # due or not


def test_the_overview_counts_what_is_due(session: Session, session_factory):
    llm = Practising(RULES, [SCHEDULING_CONCEPTS])
    env, _ = scheduling(session, session_factory, llm)
    prepare(session, session_factory, env, ["Thread"], llm)
    card = items_of(session, named(session, env, "Thread"))["flashcard"]
    later = datetime.now(UTC) + timedelta(minutes=1)  # new items are due at once
    practice.answer(session, card, AttemptCreate(knew=True), later)

    view = practice.overview(session, env, llm, now=later + timedelta(hours=1))

    assert (view.items, view.due, view.next_due_at) == (4, 3, later + timedelta(days=1))
    states = {c.name: (c.state, c.items, c.due) for c in view.concepts}
    assert states == {
        "Round Robin": ("none", 0, 0),
        "Thread": ("ready", 4, 3),
        "Time Quantum": ("none", 0, 0),
    }
