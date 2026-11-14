"""Tests for the offline evaluation in evaluation/ (decision record 20).

Purpose: the benchmark's numbers are only as good as its labels and its
arithmetic. These check that every question's evidence still resolves to the
passages the app cuts from the corpus, with the right counts of each kind,
that the key facts can be found in their documents, and that each score is
computed as defined, on rankings made by hand. The benchmark itself, with
the real models, runs locally: python scripts/evaluate_retrieval.py.
"""

import pytest

from evaluation import dataset, metrics


@pytest.fixture(scope="module")
def passages():
    return dataset.passages()


def test_every_label_resolves_to_the_passages_the_app_cuts(passages):
    questions = dataset.load_questions()

    assert len(questions) == 80
    assert dataset.problems(questions, passages) == []


def test_a_broken_label_is_reported(passages):
    good = dataset.load_questions()
    nowhere = dataset.Question(
        id="z1",
        kind="term",
        question="What is a zombie process?",
        term="zombie",
        evidence=(dataset.Evidence("01-processes-and-threads.pdf", "not in it"),),
    )
    # Two quotes from one passage: not a question needing two passages.
    one_passage = dataset.Question(
        id="z3",
        kind="multi",
        question="What is a zombie process, and what does wait do?",
        evidence=(
            dataset.Evidence(
                "01-processes-and-threads.pdf",
                "the child's entry in the process table stays behind as a zombie process",
            ),
            dataset.Evidence(
                "01-processes-and-threads.pdf",
                "A parent collects a finished child's exit status by calling wait",
            ),
        ),
    )
    # An alternative quote must resolve too.
    bad_alternative = dataset.Question(
        id="z4",
        kind="term",
        question="What is a zombie process?",
        term="zombie",
        evidence=(
            dataset.Evidence(
                "01-processes-and-threads.pdf",
                "the child's entry in the process table stays behind as a zombie process",
                also=(dataset.Evidence("01-processes-and-threads.pdf", "not in it"),),
            ),
        ),
    )
    copying = dataset.Question(
        id="z2",
        kind="meaning",
        question="What is a race condition?",
        avoid=("race condition",),
        evidence=good[0].evidence,
    )

    found = dataset.problems(
        [*good, nowhere, one_passage, bad_alternative, copying], passages
    )

    assert "z1: quote found 0 times in the corpus" in found
    assert "z2: the question uses 'race condition'" in found
    assert "z3: needs two different passages" in found
    assert "z4: quote found 0 times in the corpus" in found
    assert any(p.startswith("kinds are") for p in found)


def test_every_key_fact_can_be_found_in_its_document():
    facts = dataset.load_key_facts()

    assert len(facts) == 50
    assert dataset.fact_problems(facts) == []


def test_a_fact_is_covered_only_when_every_word_group_is_matched():
    fact = dataset.KeyFact("f", "d", "fact", (("fork",), ("exec", "execve")))

    assert dataset.covers("Unix uses fork, then execve.", fact)
    assert not dataset.covers("Unix uses fork.", fact)
    # Words match where a word begins, never inside another word.
    optimal = dataset.KeyFact("f", "d", "fact", (("opt",),))
    assert dataset.covers("The optimal policy", optimal)
    assert not dataset.covers("Processes adopt it", optimal)


def test_recall_counts_the_share_of_parts_answered_in_the_first_k():
    ranked = ["a", "b", "c", "d", "e", "f"]

    assert metrics.recall_at(ranked, [{"c"}], 5) == 1.0
    assert metrics.recall_at(ranked, [{"f"}], 5) == 0.0
    # Two parts, one answered in the first five.
    assert metrics.recall_at(ranked, [{"b"}, {"f"}], 5) == 0.5
    assert metrics.recall_at(ranked, [{"b"}, {"f"}], 10) == 1.0
    # A part answered by either of two passages counts once.
    assert metrics.recall_at(ranked, [{"a", "b"}], 5) == 1.0
    assert metrics.recall_at(ranked, [{"z", "e"}, {"y"}], 5) == 0.5
    with pytest.raises(ValueError):
        metrics.recall_at(ranked, [], 5)
    with pytest.raises(ValueError):
        metrics.recall_at(ranked, [{"a"}, set()], 5)


def test_reciprocal_rank_is_one_over_the_first_relevant_position():
    ranked = ["a", "b", "c"]

    assert metrics.reciprocal_rank(ranked, {"a"}) == 1.0
    assert metrics.reciprocal_rank(ranked, {"c", "b"}) == 0.5
    assert metrics.reciprocal_rank(ranked, {"z"}) == 0.0
    assert metrics.reciprocal_rank(ranked, {"c"}, k=2) == 0.0
    assert metrics.hit_at_1(ranked, {"a"}) == 1.0
    assert metrics.hit_at_1(ranked, {"b"}) == 0.0
    assert metrics.hit_at_1([], {"b"}) == 0.0


def test_percentiles_interpolate_between_measurements():
    times = [1.0, 2.0, 3.0, 4.0]

    assert metrics.percentile(times, 50) == 2.5
    assert metrics.percentile(times, 0) == 1.0
    assert metrics.percentile(times, 100) == 4.0
    assert metrics.percentile([5.0], 95) == 5.0
    assert metrics.percentile(times, 95) == pytest.approx(3.85)


def test_scores_are_averaged_overall_and_by_kind():
    rows = [
        {"kind": "term", "rr": 1.0},
        {"kind": "term", "rr": 0.5},
        {"kind": "multi", "rr": 0.0},
    ]

    assert metrics.by_kind(rows, "rr") == {"all": 0.5, "term": 0.75, "multi": 0.0}


def test_generation_scores():
    # Two key points: the first cites two passages, one supporting it; the
    # second cites one passage that does not.
    points = [[True, False], [False]]

    assert metrics.citation_correctness(points) == pytest.approx(1 / 3)
    assert metrics.groundedness(points) == 0.5
    assert metrics.completeness([True, True, False, True]) == 0.75
