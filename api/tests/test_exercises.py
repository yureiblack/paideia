"""Tests for app/exercises.py and app/exact.py: linear algebra exercises the
backend writes, solves and marks (decision record 27).

Purpose: prove the phase's acceptance criteria. Every type's answer agrees
with an independent computation (numpy, in floating point, which shares no
code with the exact module) over many seeds; the worked solution ends at
the stored answer; a review shows new numbers; and wrong, partial and
malformed answers are each handled and explained. Also: numbers stay small,
every prompt and step renders, and an answer with many right forms is
accepted in any of them.
"""

import re
from fractions import Fraction

import numpy as np
import pytest

from app import exact as X
from app import exercises as E
from app import maths

SEEDS = range(200)


def floats(m) -> np.ndarray:
    return np.array([[float(x) for x in row] for row in m])


def close(a, b) -> bool:
    return np.allclose(
        np.asarray(a, dtype=float), np.asarray(b, dtype=float), atol=1e-9
    )


def independently_right(ex: E.Exercise) -> bool:
    """The exercise's own answer, checked by numpy from the matrices it was
    built on."""
    s = [float(x) for x in ex.solution.numbers]
    g = {name: floats(m) for name, m in ex.given.items()}
    kind = ex.kind
    if kind == "determinant":
        return abs(np.linalg.det(g["A"]) - s[0]) < 1e-6
    if kind == "solve_system":
        return close(np.linalg.solve(g["A"], g["b"][:, 0]), s)
    if kind == "rank":
        return int(np.linalg.matrix_rank(g["A"])) == s[0]
    if kind == "inverse":
        return close(np.linalg.inv(g["A"]).ravel(), s)
    if kind == "product":
        return close((g["A"] @ g["B"]).ravel(), s)
    if kind == "reduced_form":
        r = np.array(s).reshape(g["A"].shape)
        ranks = {np.linalg.matrix_rank(m) for m in (g["A"], r, np.vstack([g["A"], r]))}
        return len(ranks) == 1  # the same row space
    if kind == "null_space":
        basis = np.array(s).reshape(-1, g["A"].shape[1])
        nullity = g["A"].shape[1] - np.linalg.matrix_rank(g["A"])
        return (
            close(g["A"] @ basis.T, 0)
            and np.linalg.matrix_rank(basis) == len(basis) == nullity
        )
    if kind == "independence":
        rank = np.linalg.matrix_rank(g["V"])
        if ex.solution.choice == 0:
            return rank == 3
        return rank < 3 and close(g["V"] @ np.array(s), 0) and any(s)
    if kind == "eigen":
        values, vectors = s[:2], np.array(s[2:]).reshape(2, 2)
        found = sorted(np.linalg.eigvals(g["A"]).real)
        return close(found, sorted(values)) and all(
            close(g["A"] @ v, value * v)
            for value, v in zip(values, vectors, strict=True)
        )
    raise AssertionError(kind)


@pytest.mark.parametrize("kind", sorted(E.KINDS))
def test_every_answer_agrees_with_an_independent_computation(kind):
    for seed in SEEDS:
        ex = E.exercise(kind, f"item:{seed}")
        assert independently_right(ex), (kind, seed, ex.prompt)
        assert E.mark(
            ex, [str(x) for x in ex.solution.numbers], ex.solution.choice
        ).correct


@pytest.mark.parametrize("kind", sorted(E.KINDS))
def test_every_prompt_and_step_renders_with_small_numbers(kind):
    for seed in SEEDS:
        ex = E.exercise(kind, f"item:{seed}")
        for text in (ex.prompt, ex.key, *ex.steps):
            assert maths.problem(text) is None, (kind, seed, text)
        shown = " ".join((ex.prompt, *ex.steps))
        assert max(int(n) for n in re.findall(r"\d+", shown)) <= 60
        denominators = [int(d) for d in re.findall(r"\\tfrac\{\d+\}\{(\d+)\}", shown)]
        assert max(denominators, default=1) <= 6


@pytest.mark.parametrize("kind", sorted(E.KINDS))
def test_the_worked_solution_ends_at_the_stored_answer(kind):
    for seed in SEEDS:
        ex = E.exercise(kind, f"item:{seed}")
        numbers = ex.solution.numbers
        last = ex.steps[-1]
        if kind in ("reduced_form",):
            reduced = tuple(tuple(numbers[i : i + 4]) for i in range(0, 12, 4))
            assert X.tex(reduced) in last
        elif kind == "inverse":
            n = int(len(numbers) ** 0.5)
            assert (
                X.tex(tuple(tuple(numbers[i : i + n]) for i in range(0, n * n, n)))
                in last
            )
        elif kind == "product":
            # Each entry's line ends at its value, in order.
            ends = [re.search(r"= (-?\d+)\\\)$", step) for step in ex.steps[1:]]
            assert [Fraction(m.group(1)) for m in ends] == list(numbers)
        elif kind == "null_space":
            basis = [numbers[i : i + 4] for i in range(0, len(numbers), 4)]
            assert all(X.column(v) in ex.steps[-2] for v in basis)
        elif kind == "independence":
            assert ("are dependent" in last) == (ex.solution.choice == 1)
            if ex.solution.choice == 1:
                assert X.column(numbers) in last
        elif kind == "eigen":
            assert (
                f"eigenvalues are \\({numbers[0]}\\) and \\({numbers[1]}\\)"
                in ex.steps[1]
            )
        else:
            assert all(X.number(x) in last for x in numbers), (kind, last)


@pytest.mark.parametrize("kind", sorted(E.KINDS))
def test_a_review_shows_new_numbers_and_a_seed_always_the_same(kind):
    prompts = [E.exercise(kind, f"item-7:{answers}").prompt for answers in range(6)]

    assert len(set(prompts)) >= 5
    assert E.exercise(kind, "item-7:3").prompt == prompts[3]


# --- marking -------------------------------------------------------------------------


def first(kind: str, wanted=lambda ex: True) -> E.Exercise:
    return next(
        e for e in (E.exercise(kind, f"pick:{s}") for s in range(500)) if wanted(e)
    )


def test_a_wrong_number_is_wrong():
    ex = first("determinant")
    wrong = str(ex.solution.numbers[0] + 1)

    marking = E.mark(ex, [wrong])

    assert (marking.correct, marking.right) == (False, (False,))


def test_a_partly_right_matrix_says_which_entries_were_right():
    ex = first("inverse", lambda e: len(e.solution.numbers) == 9)
    typed = [str(x) for x in ex.solution.numbers]
    typed[4] = str(ex.solution.numbers[4] + 1)

    marking = E.mark(ex, typed)

    assert not marking.correct
    assert marking.right == (True,) * 4 + (False,) + (True,) * 4
    assert marking.note == "8 of the 9 entries are right."


@pytest.mark.parametrize(
    "typed, reason",
    [
        ("", "Cell 1 is empty."),
        ("two", "Cell 1 is not a number"),
        ("2+3", "Cell 1 is not a number"),
        ("__import__('os')", "Cell 1 is not a number"),
        ("1/0", "Cell 1 divides by zero."),
        ("1" * 30, "Cell 1 is not a number"),
    ],
)
def test_what_is_not_a_number_is_refused_never_evaluated(typed, reason):
    with pytest.raises(E.Malformed, match=re.escape(reason)):
        E.mark(first("determinant"), [typed])


def test_the_wrong_number_of_cells_is_refused():
    with pytest.raises(E.Malformed, match="needs 9 numbers; 2 came"):
        E.mark(first("inverse", lambda e: len(e.solution.numbers) == 9), ["1", "2"])


@pytest.mark.parametrize(
    "typed, value",
    [
        ("3/4", Fraction(3, 4)),
        ("-0.5", Fraction(-1, 2)),
        ("−2", Fraction(-2)),
        (" 7 ", Fraction(7)),
        (".25", Fraction(1, 4)),
    ],
)
def test_integers_fractions_and_decimals_are_read_exactly(typed, value):
    assert E.read([typed], 1) == (value,)


def test_any_basis_of_the_null_space_is_right():
    ex = first("null_space")
    u, v = ex.solution.numbers[:4], ex.solution.numbers[4:]
    other = [*(a + b for a, b in zip(u, v, strict=True)), *(2 * b for b in v)]

    assert E.mark(ex, [str(x) for x in other]).correct
    same_twice = [str(x) for x in (*u, *u)]
    assert (
        E.mark(ex, same_twice).note
        == "The vectors are in the null space but not independent."
    )
    outside = [str(x) for x in (*u, *(b + 1 for b in v))]
    assert (
        E.mark(ex, outside).note
        == "Vector 2 is not a nonzero vector in the null space."
    )


def test_eigenvalues_in_any_order_with_any_nonzero_multiple_are_right():
    ex = first("eigen")
    (l1, l2), v1, v2 = (
        ex.solution.numbers[:2],
        ex.solution.numbers[2:4],
        ex.solution.numbers[4:],
    )
    swapped_and_scaled = [l2, l1, *(-3 * x for x in v2), *(2 * x for x in v1)]

    assert E.mark(ex, [str(x) for x in swapped_and_scaled]).correct
    mismatched = [l1, l2, *v2, *v1]
    assert E.mark(ex, [str(x) for x in mismatched]).note == (
        "Vector 1 is not an eigenvector for its eigenvalue."
    )
    assert E.mark(ex, [str(l1 + 10), str(l2), *map(str, v1), *map(str, v2)]).note == (
        "The eigenvalues are not right."
    )


def test_independence_is_a_choice_and_dependence_needs_weights():
    dependent = first("independence", lambda e: e.solution.choice == 1)
    independent = first("independence", lambda e: e.solution.choice == 0)
    weights = dependent.solution.numbers

    assert E.mark(dependent, [str(-2 * w) for w in weights], 1).correct
    assert E.mark(dependent, [], 0).note == "These vectors are dependent."
    assert (
        E.mark(dependent, ["0", "0", "0"], 1).note
        == "The weights must not all be zero."
    )
    assert E.mark(independent, [], 0).correct
    assert (
        E.mark(independent, ["1", "1", "1"], 1).note == "These vectors are independent."
    )
    with pytest.raises(E.Malformed, match="Choose whether"):
        E.mark(independent, [])


# --- the check on the model's choice -----------------------------------------------------


def test_a_type_fits_only_passages_that_use_its_words():
    assert E.fits("eigen", "Each eigenvalue of \\(A\\) is a root of ...")
    assert E.fits("determinant", "The \\(\\det(A)\\) of a matrix")
    assert not E.fits("eigen", "A deadlock needs four conditions.")
    # The operating system's kernel is no null space.
    assert not E.fits("null_space", "The kernel loads the page from disk.")


# --- the exact module ------------------------------------------------------------------


def test_determinants_and_reduction_agree_with_numpy():
    rng = np.random.default_rng(27)
    for _ in range(200):
        a = rng.integers(-5, 6, size=(3, 3))
        exact = X.matrix(a.tolist())
        assert abs(float(X.det(exact)) - np.linalg.det(a)) < 1e-6
        assert X.rank(exact) == np.linalg.matrix_rank(a)


def test_eigenvectors_are_whole_numbers_and_polynomials_read_cleanly():
    assert X.whole([Fraction(1, 2), Fraction(1)]) == (1, 2)
    assert X.whole([Fraction(-2), Fraction(4), Fraction(0)]) == (1, -2, 0)
    assert (
        X.polynomial([Fraction(1), Fraction(-6), Fraction(1)])
        == "\\lambda^{2} - 6\\lambda + 1"
    )
    assert (
        X.polynomial([Fraction(1), Fraction(4), Fraction(0)])
        == "\\lambda^{2} + 4\\lambda"
    )
    assert (X.factor(-4), X.factor(3), X.factor(0)) == (
        "(\\lambda + 4)",
        "(\\lambda - 3)",
        "\\lambda",
    )
    assert X.integer_roots([Fraction(1), Fraction(-1), Fraction(-6)]) == [-2, 3]
    # A null space read off the reduced form comes out in whole numbers.
    assert X.null_space(X.matrix([[2, -1]])) == [(1, 2)]
