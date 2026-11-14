"""Tests for practice in app/services/practice.py, with mocked model answers.

Purpose: items are written from a concept's own passages and checked before
anything is stored; items failing a check, or not supported by their
passages, are dropped and counted; the same passages never write twice;
new passages keep a concept's items, a changed cited passage retires them,
kept with their attempts; answers are
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
    Document,
    GeneratedArtifact,
    LearningItem,
    LearningItemSource,
    ReviewSchedule,
)
from app.schemas import AttemptCreate
from app.services import documents as document_service
from app.services import practice
from tests.fakes import FailingProvider, FakeEmbedder, FakeReranker, practice_answer
from tests.parsed import H, P, Returns, document
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


def test_new_passages_keep_items_and_changed_ones_retire_them(
    session: Session, session_factory
):
    llm = Practising(
        RULES, [SCHEDULING_CONCEPTS, [concept("Thread", [1])], SCHEDULING_CONCEPTS]
    )
    env, doc = scheduling(session, session_factory, llm)
    prepare(session, session_factory, env, ["Thread"], llm)
    thread = named(session, env, "Thread")
    old = items_of(session, thread)["flashcard"]
    practice.answer(session, old, AttemptCreate(knew=True), NOW)

    # A second lecture explains threads too: new passages for Thread, but the
    # ones its items cite are unchanged, so they are still practised.
    sync = add(session, session_factory, env, "sync.pdf", SYNCHRONIZATION)
    extract(session, session_factory, sync, llm)
    session.expire_all()
    still = next(
        c for c in practice.overview(session, env, llm).concepts if c.name == "Thread"
    )
    assert (still.state, still.items) == ("ready", 4)
    assert practice.answer(session, old, AttemptCreate(knew=True), NOW).correct

    # Its own passage is rewritten: the cited passage is gone, so its items
    # are no longer practised until prepared again.
    edited = document(
        [H("Threads"), P("A thread is the smallest unit the scheduler runs.")],
        [H("Round robin"), P("Round robin gives every thread a time quantum in turn.")],
    )
    document_service.request_reprocess(session, doc)
    document_service.process_document(
        session_factory, doc.id, Returns(edited), FakeEmbedder()
    )
    session.expire_all()  # read again by another session
    extract(session, session_factory, session.get(Document, doc.id), llm)
    session.expire_all()
    outdated = next(
        c for c in practice.overview(session, env, llm).concepts if c.name == "Thread"
    )
    assert (outdated.state, outdated.items) == ("outdated", 0)
    with pytest.raises(practice.NotPractised):
        practice.answer(session, old, AttemptCreate(knew=True), NOW)

    prepare(session, session_factory, env, ["Thread"], llm)

    assert len(items_of(session, thread)) == 4
    assert old.id in {i.id for i in items_of(session, thread, retired=True).values()}
    assert session.scalar(select(func.count()).where(Attempt.item_id == old.id)) == 2


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


def test_each_item_still_moves_up_its_own_box(session: Session, session_factory):
    llm = Practising(RULES, [SCHEDULING_CONCEPTS])
    env, _ = scheduling(session, session_factory, llm)
    prepare(session, session_factory, env, ["Thread"], llm)
    card = items_of(session, named(session, env, "Thread"))["flashcard"]

    boxes = [
        practice.answer(
            session, card, AttemptCreate(knew=True), NOW + timedelta(days=d)
        ).box
        for d in (0, 1, 3)
    ]

    assert boxes == [1, 2, 3]
    assert session.get(ReviewSchedule, card.id).due_at == NOW + timedelta(days=7)


def test_a_session_holds_due_concepts_items_and_a_stage_holds_all(
    session: Session, session_factory
):
    llm = Practising(RULES, [SCHEDULING_CONCEPTS])
    env, _ = scheduling(session, session_factory, llm)
    names = ["Thread", "Round Robin", "Time Quantum"]
    prepare(session, session_factory, env, names, llm)
    later = datetime.now(UTC) + timedelta(minutes=1)

    due = practice.session_items(session, env, now=later)

    # Three new concepts, two items each, of different kinds, interleaved.
    assert len(due) == 6
    assert sorted(i.concept.name for i in due) == sorted(names * 2)
    assert all(a.concept.id != b.concept.id for a, b in itertools.pairwise(due))
    assert all(len({i.kind for i in due if i.concept.name == n}) == 2 for n in names)
    assert all(
        i.answer is None for i in due if i.kind in ("multiple_choice", "true_false")
    )
    for item in (i for i in due if i.concept.name == "Thread"):
        practice.answer(
            session,
            session.get(LearningItem, item.id),
            AttemptCreate(knew=True, choice=0, truth=True),
            later,
        )
    # Thread was reviewed: it comes back tomorrow, not in this day's session.
    again = practice.session_items(session, env, now=later)
    assert {i.concept.name for i in again} == {"Round Robin", "Time Quantum"}
    tomorrow = practice.session_items(
        session, env, now=later, until=later + timedelta(days=1)
    )
    assert "Thread" in {i.concept.name for i in tomorrow}
    thread = named(session, env, "Thread")
    stage = practice.session_items(session, env, [thread.id], now=later)
    assert {i.concept.name for i in stage} == {"Thread"}
    assert len(stage) == 4  # due or not


def test_the_overview_gives_each_concepts_learner_state(
    session: Session, session_factory
):
    llm = Practising(RULES, [SCHEDULING_CONCEPTS])
    env, _ = scheduling(session, session_factory, llm)
    prepare(session, session_factory, env, ["Thread", "Round Robin"], llm)
    thread = items_of(session, named(session, env, "Thread"))
    later = datetime.now(UTC) + timedelta(minutes=1)  # new items are due at once
    missed_at = later + timedelta(minutes=1)
    practice.answer(session, thread["flashcard"], AttemptCreate(knew=True), later)
    practice.answer(
        session, thread["short_answer"], AttemptCreate(knew=False), missed_at
    )

    view = practice.overview(session, env, llm, now=later + timedelta(hours=1))
    concepts = {c.name: c for c in view.concepts}

    assert (view.items, view.due_concepts, view.new_concepts) == (8, 0, 1)
    assert view.next_review_at == missed_at + timedelta(days=1)
    t = concepts["Thread"]
    assert (t.review, t.exposures, t.recalled, t.failed, t.gap_days) == (
        "scheduled",
        2,
        1,
        1,
        1,
    )
    assert (t.last_attempted_at, t.last_recalled_at) == (missed_at, later)
    assert t.attention == "Missed on its last answer."
    assert concepts["Round Robin"].review == "new"
    assert concepts["Time Quantum"].review is None  # no items
    assert [n.name for n in view.needs_attention] == ["Thread"]
    assert view.recently_strong == []
    tomorrow = practice.overview(
        session, env, llm, now=later, until=later + timedelta(days=1, hours=1)
    )
    assert tomorrow.due_concepts == 1


def test_a_concept_recalled_over_days_becomes_recently_strong(
    session: Session, session_factory
):
    llm = Practising(RULES, [SCHEDULING_CONCEPTS])
    env, _ = scheduling(session, session_factory, llm)
    prepare(session, session_factory, env, ["Thread"], llm)
    card = items_of(session, named(session, env, "Thread"))["flashcard"]
    start = datetime.now(UTC) + timedelta(minutes=1)

    results = [
        practice.answer(
            session, card, AttemptCreate(knew=True), start + timedelta(days=d)
        )
        for d in (0, 1, 3)
    ]

    assert [(r.gap_days, r.due_at) for r in results] == [
        (1, start + timedelta(days=1)),
        (2, start + timedelta(days=3)),
        (4, start + timedelta(days=7)),
    ]
    view = practice.overview(session, env, llm, now=start + timedelta(days=3))
    assert [(n.name, n.note) for n in view.recently_strong] == [
        ("Thread", "Recalled; next review in 4 days.")
    ]


def test_an_item_is_retired_when_any_passage_it_cites_changes(
    session: Session, session_factory
):
    def two_sources(prompt):
        answer = practice_answer(prompt)
        for item in answer.values():
            item["sources"] = [1, 2]
        return answer

    both = [concept("Thread", [1, 2]), *SCHEDULING_CONCEPTS[1:]]
    llm = Practising(RULES, [both, both], items=two_sources)
    env, doc = scheduling(session, session_factory, llm)
    prepare(session, session_factory, env, ["Thread"], llm)
    thread = named(session, env, "Thread")
    assert len(items_of(session, thread)) == 4

    # Only the round robin passage changes; every item cites it too.
    edited = document(
        [H("Threads"), P("A thread is a sequence of execution within a process.")],
        [H("Round robin"), P("Round robin hands out the processor in equal turns.")],
    )
    document_service.request_reprocess(session, doc)
    document_service.process_document(
        session_factory, doc.id, Returns(edited), FakeEmbedder()
    )
    session.expire_all()

    state = next(
        c for c in practice.overview(session, env, llm).concepts if c.name == "Thread"
    )
    assert (state.state, state.items) == ("outdated", 0)
