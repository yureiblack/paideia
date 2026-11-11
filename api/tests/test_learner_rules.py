"""Tests for learner state and scheduling in app/learner.py.

Purpose: the explainable schedule. Each recall moves a concept's gap one
step up the ladder, at most once a sitting; a miss brings it back the next
day and wins its sitting; the gap stops at 32 days; the same answers always
give the same state. The rules for "due", "needs attention" and "recently
strong", and sessions built from due concepts.
"""

import itertools
import uuid
from datetime import UTC, datetime, timedelta

from app.learner import (
    GAPS,
    Answer,
    Option,
    State,
    attention,
    replay,
    review,
    session,
    strong,
)

MONDAY = datetime(2026, 11, 16, 18, tzinfo=UTC)
DAY = timedelta(days=1)


def at(days=0, hours=0, correct=True):
    return Answer(MONDAY + timedelta(days=days, hours=hours), correct)


def test_a_new_concept_has_no_schedule_and_is_due_at_once():
    state = replay([])

    assert (state.exposures, state.gap_days, state.next_review_at) == (0, None, None)
    assert review(state, MONDAY) == "new"


def test_each_recall_moves_the_gap_one_step_up():
    # Right on Monday, Tuesday, Thursday: next on Tuesday, Thursday, Monday.
    state = replay([at(0), at(1), at(3)])

    assert state.gap_days == 4
    assert state.next_review_at == MONDAY + 7 * DAY
    assert (state.exposures, state.recalled, state.failed) == (3, 3, 0)
    assert state.last_recalled_at == MONDAY + 3 * DAY


def test_recalls_in_one_sitting_count_once():
    state = replay([at(0), at(0, hours=1), at(0, hours=11)])

    assert state.gap_days == 1
    assert state.next_review_at == MONDAY + timedelta(hours=11) + DAY
    assert state.recalled == 3  # every answer is still counted
    assert replay([at(0), at(0, hours=12)]).gap_days == 2  # a new sitting


def test_a_miss_brings_the_concept_back_the_next_day_and_wins_its_sitting():
    climbed = [at(0), at(1), at(3), at(7)]

    missed = replay([*climbed, at(15, correct=False)])
    recovered = replay([*climbed, at(15, correct=False), at(15, hours=2)])

    assert (missed.gap_days, missed.next_review_at) == (1, MONDAY + 16 * DAY)
    assert (missed.failed, missed.last_recalled_at) == (1, MONDAY + 7 * DAY)
    assert recovered.gap_days == 1  # the recall straight after does not undo it
    assert replay([*climbed, at(15, correct=False), at(16)]).gap_days == 2


def test_the_gap_stops_at_thirty_two_days():
    days = itertools.accumulate([0, 1, 2, 4, 8, 16, 32, 32, 32])

    state = replay([at(d) for d in days])

    assert GAPS == (1, 2, 4, 8, 16, 32)
    assert state.gap_days == 32


def test_the_same_answers_always_give_the_same_state():
    answers = [at(0), at(0, hours=2, correct=False), at(1), at(3), at(3, hours=13)]

    assert replay(answers) == replay(list(answers))
    assert replay(answers[:3]) != replay(answers)


def test_due_means_its_next_review_comes_by_the_given_time():
    state = replay([at(0)])

    assert review(state, MONDAY + timedelta(hours=23)) == "scheduled"
    assert review(state, MONDAY + DAY) == "due"


def test_needs_attention_after_a_miss_or_when_mostly_missed():
    assert (
        attention(replay([at(0), at(1, correct=False)])) == "Missed on its last answer."
    )
    mostly_missed = [
        at(0, correct=False),
        at(1, correct=False),
        at(2),
        at(3, correct=False),
        at(4),
    ]
    assert attention(replay(mostly_missed)) == "Recalled 2 of its last 5 answers."
    assert attention(replay([*mostly_missed, at(5)])) is None  # 3 of 6: half
    assert attention(replay([at(0), at(1)])) is None
    assert attention(replay([])) is None


def test_fewer_than_half_of_the_last_six_counts_only_the_last_six():
    old_misses = [at(d, correct=False) for d in range(4)]
    outcomes = [True, True, False, True, True, True]
    recent = [at(d, correct=c) for d, c in zip(range(4, 10), outcomes, strict=True)]
    state = replay([*old_misses, *recent])

    assert state.recent == tuple(outcomes)  # the four early misses are gone
    assert attention(state) is None


def test_recently_strong_needs_a_long_gap_and_a_recall_last():
    assert strong(replay([at(0), at(1), at(3)]))  # a 4-day gap
    assert not strong(replay([at(0), at(1)]))  # 2 days
    assert not strong(replay([at(0), at(1), at(3), at(7, correct=False)]))


def option(concept, kind, box=0, answered=None):
    return Option(uuid.uuid4(), concept, kind, box, answered)


def test_a_session_takes_overdue_concepts_first_then_new_ones_in_roadmap_order():
    overdue = replay([at(0)])  # due on Tuesday
    later = replay([at(0, hours=5)])
    future = replay([at(0), at(1), at(3)])
    now = MONDAY + 2 * DAY
    concepts = [
        ("new-late", State(), 5),
        ("new-early", State(), 1),
        ("later", later, 0),
        ("overdue", overdue, 9),
        ("future", future, 0),
    ]
    options = [option(c, "flashcard") for c, _, _ in concepts]

    picked = session(concepts, options, now, per_concept=1)

    assert [o.concept for o in picked] == ["overdue", "later", "new-early", "new-late"]


def test_each_concept_gives_two_items_of_different_kinds_lowest_box_first():
    options = [
        option("a", "flashcard", box=2),
        option("a", "flashcard", box=0),
        option("a", "flashcard", box=0, answered=MONDAY),
        option("a", "true_false", box=1),
        option("b", "short_answer", box=0),
        option("b", "short_answer", box=0, answered=MONDAY),
    ]

    picked = session([("a", State(), 0), ("b", State(), 1)], options, MONDAY)

    a = [o for o in picked if o.concept == "a"]
    b = [o for o in picked if o.concept == "b"]
    assert [(o.kind, o.box, o.last_answered_at) for o in a] == [
        ("flashcard", 0, None),
        ("true_false", 1, None),
    ]
    assert len(b) == 2  # only one kind: two of it
    assert all(x.concept != y.concept for x, y in itertools.pairwise(picked))


def test_a_session_is_bounded():
    concepts = [(n, State(), n) for n in range(8)]
    options = [option(n, k) for n in range(8) for k in ("flashcard", "true_false")]

    picked = session(concepts, options, MONDAY)

    assert len(picked) == 10
    assert {o.concept for o in picked} == {0, 1, 2, 3, 4}
