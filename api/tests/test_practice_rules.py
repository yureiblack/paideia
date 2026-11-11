"""Tests for the practice rules in app/practice.py.

Purpose: which items a learner ever sees, and what happens after. Text is
plain and never talks about passages; options differ, lose the model's
numbering and are shuffled the same way every time; true/false statements
are true or false as asked; difficulty follows the kind of item; review
follows Leitner boxes; sessions mix concepts.
"""

import hashlib
import itertools
from datetime import UTC, datetime, timedelta

import pytest

from app.practice import (
    DIFFICULTY,
    INTERVALS,
    Candidate,
    flashcard,
    interleave,
    multiple_choice,
    pick,
    schedule,
    short_answer,
    tidy,
    true_false,
    wanted_truth,
)

NOW = datetime(2026, 11, 11, 9, tzinfo=UTC)


@pytest.mark.parametrize(
    ("text", "tidied"),
    [
        ("A thread has its own stack (passage [1]).", "A thread has its own stack."),
        ("It caches translations [2].", "It caches translations."),
        ("FIFO suffers from it (passages 1 and 3).", "FIFO suffers from it."),
        ("Wait blocks (see passage 2) when negative.", "Wait blocks when negative."),
        ("  Quantum   of 10 to 100 ms. ", "Quantum of 10 to 100 ms."),
        (
            "Which is not a condition for deadlock according to the passages?",
            "Which is not a condition for deadlock?",
        ),
        (
            "It is false because passage 1 explicitly states that LRU never shows it.",
            "It is false because LRU never shows it.",
        ),
        (
            "The passages state that ordering locks prevents it.",
            "Ordering locks prevents it.",
        ),
        (
            "Optimal evicts the latest-used page, as mentioned in passage 1.",
            "Optimal evicts the latest-used page.",
        ),
    ],
)
def test_citation_marks_and_attributions_are_removed(text, tidied):
    assert tidy(text, 300) == tidied


@pytest.mark.parametrize(
    "text",
    [
        "What does passage 2 say about deadlock?",
        "The passages describe four conditions as necessary.",
        "**Deadlock** is a state.",
        "A state where:\nprocesses wait.",
        "",
        "x" * 301,
    ],
)
def test_mentions_of_passages_formatting_and_overlong_text_are_refused(text):
    assert tidy(text, 300) is None


def test_options_lose_their_numbering_and_are_shuffled_the_same_way_each_time():
    options = [
        "1. Mutual exclusion",
        "2) No preemption",
        "C: Priority scheduling",
        "Hold and wait",
    ]

    draft = multiple_choice(
        "Which is not a condition for deadlock?",
        options,
        3,
        "It is not one of the four.",
        [1],
        "seed",
    )
    again = multiple_choice(
        "Which is not a condition for deadlock?",
        options,
        3,
        "It is not one of the four.",
        [1],
        "seed",
    )

    assert draft == again
    assert sorted(draft.content["options"]) == [
        "Hold and wait",
        "Mutual exclusion",
        "No preemption",
        "Priority scheduling",
    ]
    assert draft.content["options"][draft.content["correct"]] == "Priority scheduling"
    assert draft.claim == "Which is not a condition for deadlock? Priority scheduling"


def test_the_right_option_lands_in_different_places_for_different_items():
    places = {
        multiple_choice(
            "Q?", ["A one", "B two", "C three", "D four"], 2, "Why.", [1], seed
        ).content["correct"]
        for seed in ("a", "b", "c", "d", "e", "f", "g", "h")
    }
    assert len(places) > 1


@pytest.mark.parametrize(
    ("options", "correct", "reason"),
    [
        (["Paging", "paging", "TLB", "Frames"], 1, "options repeat"),
        (["Paging", "TLB", "Frames"], 1, "not four options with one correct"),
        (["Paging", "TLB", "Frames", "Swap"], 5, "not four options with one correct"),
        (["Paging", "TLB (passage 1)", "Frames", "**Swap**"], 1, None),
    ],
)
def test_options_must_be_four_distinct_and_plain(options, correct, reason):
    result = multiple_choice("Q?", options, correct, "Why.", [1], "seed")
    if reason:
        assert result == reason
    else:
        assert isinstance(result, str)  # the formatted option refuses the item


def test_a_true_false_statement_must_be_as_asked():
    asked_false = true_false(
        "LRU shows the anomaly.", False, "It never does.", [1], False
    )
    came_true = true_false("FIFO shows the anomaly.", True, "It does.", [1], False)

    assert asked_false.content == {
        "statement": "LRU shows the anomaly.",
        "truth": False,
        "explanation": "It never does.",
    }
    assert came_true == "not the truth asked for"


def test_about_half_of_the_statements_are_asked_to_be_false():
    keys = [hashlib.sha256(str(n).encode()).hexdigest() for n in range(200)]
    share = sum(wanted_truth(k) for k in keys) / len(keys)
    assert 0.35 < share < 0.65
    assert wanted_truth(keys[0]) == wanted_truth(keys[0])


def test_difficulty_follows_the_kind_of_item():
    assert short_answer("What is a TLB?", "A cache.", [1]).difficulty == 3
    assert flashcard("TLB", "A cache of translations.", [1]).difficulty == 1
    assert DIFFICULTY == {
        "true_false": 1,
        "flashcard": 1,
        "multiple_choice": 2,
        "short_answer": 3,
    }


def test_review_follows_leitner_boxes():
    assert INTERVALS == (1, 2, 4, 8, 16)
    box, due = schedule(0, True, NOW)  # a new item answered right
    assert (box, due) == (1, NOW + timedelta(days=1))
    box, due = schedule(box, True, NOW)
    assert (box, due) == (2, NOW + timedelta(days=2))
    for _ in range(5):
        box, due = schedule(box, True, NOW)
    assert (box, due) == (5, NOW + timedelta(days=16))  # the last box stays
    assert schedule(4, False, NOW) == (1, NOW + timedelta(days=1))
    assert schedule(0, False, NOW) == (1, NOW + timedelta(days=1))


def test_interleaving_never_repeats_a_concept_when_it_can_be_avoided():
    items = ["a1", "a2", "a3", "b1", "b2", "c1"]

    mixed = interleave(items, lambda item: item[0])

    assert sorted(mixed) == sorted(items)
    assert all(x[0] != y[0] for x, y in itertools.pairwise(mixed))
    assert [x for x in mixed if x[0] == "a"] == ["a1", "a2", "a3"]  # order kept
    assert interleave(["a1", "a2"], lambda item: item[0]) == ["a1", "a2"]


def candidate(item, concept, due_in_hours, place, difficulty=1):
    return Candidate(
        item, concept, NOW + timedelta(hours=due_in_hours), place, difficulty
    )


def test_a_session_takes_due_items_longest_due_first_then_roadmap_order():
    items = [
        candidate("late", "a", -48, 2),
        candidate("early-b", "b", -1, 0),
        candidate("early-a", "a", -1, 1),
        candidate("tomorrow", "c", 24, 0),
    ]

    session = pick(items, NOW)

    assert [c.id for c in session] == ["late", "early-b", "early-a"]
    stage = pick(items, NOW, due_only=False)
    assert [c.id for c in stage][-1] == "tomorrow"


def test_a_session_is_bounded_and_interleaved():
    items = [
        candidate(f"{c}{n}", c, -1, place)
        for place, c in enumerate("ab")
        for n in range(8)
    ]

    session = pick(items, NOW, limit=10)

    # Eight items each: concepts take turns, so five of each, alternating.
    assert len(session) == 10
    assert sorted(c.concept for c in session) == ["a"] * 5 + ["b"] * 5
    assert all(x.concept != y.concept for x, y in itertools.pairwise(session))
