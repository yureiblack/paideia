"""Tests for the study planner in app/planner.py.

Purpose: today's plan by fixed rules. Weak concepts are strengthened first,
then due ones reviewed, then the next roadmap stage learned, then recent
material skimmed; no concept twice; big groups split; effort from reading
and answering, at the learner's own pace once known; a budget takes sessions
in order while they fit; the same inputs always give the same plan.
"""

import random
from datetime import UTC, datetime, timedelta

from app.planner import (
    DEFAULT_SECONDS,
    GROUP,
    Concept,
    Document,
    Stage,
    build,
    pace,
)

NOW = datetime(2026, 11, 12, 18, tzinfo=UTC)
PACE = pace({})


def concept(
    name,
    place,
    review=None,
    attention=None,
    exposures=0,
    gap=None,
    kinds=("flashcard", "true_false"),
    words=200,
    passage=None,
):
    return Concept(
        id=name,
        name=name,
        place=place,
        review=review,
        attention=attention,
        exposures=exposures,
        gap_days=gap,
        kinds=kinds,
        passages=((passage or f"p-{name}", words),),
    )


def trial():
    """Today in the trial environment: three missed, two due, stage 3 next."""
    concepts = [
        concept("Thread", 0, "due", exposures=4, gap=1, passage="p1"),
        concept("Context Switch", 1, "due", exposures=4, gap=1, passage="p1"),
        concept("Dispatcher", 2, "due", "Missed on its last answer.", 2, 1),
        concept("Round Robin", 3, "due", "Missed on its last answer.", 2, 1),
        concept("Time Quantum", 4, "due", "Missed on its last answer.", 2, 1),
        concept("Aging", 5, kinds=(), words=400, passage="p3"),  # one passage
        concept("SJF", 6, kinds=(), words=400, passage="p3"),
        concept("Mutex", 7, kinds=()),
    ]
    stages = [
        Stage(1, "Threads", ("Thread", "Context Switch")),
        Stage(2, "Scheduling", ("Dispatcher", "Round Robin", "Time Quantum")),
        Stage(3, "Advanced scheduling", ("Aging", "SJF")),
        Stage(4, "Locks", ("Mutex",)),
    ]
    documents = [
        Document("d1", "Scheduling.pdf", NOW - timedelta(days=2), 300, ("Thread",)),
        Document("d2", "Synchronization.pdf", NOW - timedelta(days=2), 400, ("Mutex",)),
    ]
    return concepts, stages, documents


def test_weak_then_due_then_the_next_stage_then_recent_material():
    plan = build(*trial(), PACE, NOW)

    assert [(s.kind, s.concepts) for s in plan.sessions] == [
        ("strengthen", ("Dispatcher", "Round Robin", "Time Quantum")),
        ("review", ("Thread", "Context Switch")),
        ("learn", ("Aging", "SJF")),
        ("skim", ("Mutex",)),
    ]
    strengthen, review, learn, skim = plan.sessions
    assert strengthen.title == "Strengthen: Dispatcher, Round Robin and Time Quantum"
    assert strengthen.rationale.startswith("3 concepts missed on the last answer")
    assert review.rationale == (
        "2 concepts due for review today. Reviewing on time lets each gap keep "
        "growing; it is now 1 day."
    )
    assert (learn.title, learn.stage, learn.needs_preparing) == (
        "Learn: stage 3, Advanced scheduling",
        3,
        True,
    )
    assert "need preparing first" in learn.rationale
    assert (skim.title, skim.document) == ("Skim: Synchronization.pdf", "d2")
    assert skim.rationale.startswith("Added 2 days ago, and none of its 1 concept")


def test_effort_counts_reading_once_per_passage_and_two_answers_per_concept():
    plan = build(*trial(), PACE, NOW)
    strengthen, review, learn, skim = plan.sessions

    # 3 passages of 200 words at 200 a minute, then 6 answers at 30 s.
    assert strengthen.minutes == 3 + 3
    # Thread and Context Switch share their passage; review only answers:
    # 4 answers at 30 s.
    assert review.minutes == 2
    # Aging and SJF share one 400-word passage, read once: 2 minutes; not
    # prepared, so 4 answers at the mean of all kinds (52.5 s): 3.5 more.
    assert learn.minutes == 6
    assert skim.minutes == 2  # 400 words
    assert plan.minutes == 6 + 2 + 6 + 2


def test_the_learners_own_pace_replaces_the_defaults_once_known():
    assert (
        pace({"flashcard": [10, 12, 14, 16]})["flashcard"]
        == DEFAULT_SECONDS["flashcard"]
    )
    own = pace({"flashcard": [10, 12, 14, 16, 90], "true_false": [8] * 5})
    assert (own["flashcard"], own["true_false"]) == (14, 8)
    assert own["short_answer"] == DEFAULT_SECONDS["short_answer"]

    fast = build(*trial(), own, NOW)
    assert fast.sessions[1].minutes == 1  # 4 answers at about 11 s


def test_no_concept_appears_twice():
    plan = build(*trial(), PACE, NOW)

    placed = [c for s in plan.sessions if s.kind != "skim" for c in s.concepts]
    assert len(placed) == len(set(placed))


def test_big_groups_become_several_sessions_in_roadmap_order():
    due = [concept(f"C{n:02}", n, "due", exposures=1, gap=2) for n in range(GROUP + 2)]

    plan = build(due, [], [], PACE, NOW)

    assert [len(s.concepts) for s in plan.sessions] == [GROUP, 2]
    assert plan.sessions[1].concepts == ("C05", "C06")


def test_the_next_stage_is_the_first_with_concepts_not_yet_practised():
    concepts = [
        concept("A", 0, "scheduled", exposures=3, gap=4),
        concept("B", 1, "new", exposures=0),  # prepared, never answered
        concept("C", 2, kinds=()),
    ]
    stages = [
        Stage(1, "One", ("A",)),
        Stage(2, "Two", ("B",)),
        Stage(3, "Three", ("C",)),
    ]

    [learn] = build(concepts, stages, [], PACE, NOW).sessions

    assert (learn.stage, learn.concepts, learn.needs_preparing) == (2, ("B",), False)
    assert "need preparing" not in learn.rationale


def test_only_recent_untouched_documents_with_a_summary_are_skimmed():
    concepts = [concept("A", 0, kinds=()), concept("B", 1, "scheduled", exposures=1)]
    documents = [
        Document("old", "Old.pdf", NOW - timedelta(days=8), 300, ("A",)),
        Document("plain", "Plain.pdf", NOW, None, ("A",)),
        Document("started", "Started.pdf", NOW, 300, ("A", "B")),
        Document("new1", "New1.pdf", NOW - timedelta(hours=2), 300, ("A",)),
        Document("new2", "New2.pdf", NOW - timedelta(days=1), 300, ("A",)),
        Document("new3", "New3.pdf", NOW - timedelta(days=3), 300, ("A",)),
    ]

    plan = build(concepts, [], documents, PACE, NOW)

    assert [s.document for s in plan.sessions] == ["new1", "new2"]  # newest two
    only_old = build(concepts, [], [documents[0], documents[-1]], PACE, NOW)
    assert [s.document for s in only_old.sessions] == ["new3"]  # 8 days is too old
    assert plan.sessions[0].rationale.startswith("Added today")
    assert plan.sessions[1].rationale.startswith("Added yesterday")


def test_a_budget_takes_sessions_in_order_while_they_fit():
    plan = build(*trial(), PACE, NOW, budget=10)

    # Strengthen (6) and review (2) fit; learn (6) does not; skim (2) does.
    assert [s.kind for s in plan.sessions] == ["strengthen", "review", "skim"]
    assert [s.kind for s in plan.later] == ["learn"]
    assert plan.minutes == 10
    assert build(*trial(), PACE, NOW, budget=1).sessions == ()


def test_the_same_inputs_always_give_the_same_plan():
    concepts, stages, documents = trial()
    first = build(concepts, stages, documents, PACE, NOW)

    for seed in range(5):
        shuffled = concepts[:]
        random.Random(seed).shuffle(shuffled)
        assert build(shuffled, stages, list(reversed(documents)), PACE, NOW) == first


def test_nothing_to_do_is_an_empty_plan():
    plan = build([concept("A", 0, "scheduled", exposures=2, gap=4)], [], [], PACE, NOW)
    assert (plan.sessions, plan.minutes) == ((), 0)


def test_a_weak_concept_without_items_to_answer_is_not_strengthened():
    # Its items were retired when its material changed: nothing to answer
    # until it is prepared again.
    outdated = concept(
        "A", 0, "scheduled", "Missed on its last answer.", 2, 1, kinds=()
    )

    assert build([outdated], [], [], PACE, NOW).sessions == ()
