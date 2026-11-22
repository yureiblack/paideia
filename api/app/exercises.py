"""Linear algebra exercises the backend writes, solves and marks (decision
record 27).

Purpose
-------
The model never computes an exercise. It only chooses which types of
exercise fit a concept, from this catalogue. Everything else is here, pure
and exact (app/exact.py):

- An exercise is generated from a seed: the item and how many times it has
  been answered, so every review shows new numbers, and the same seed always
  gives the same exercise, which is how an answer is marked.
- Numbers are small with clean answers, because each exercise is built
  backward from its answer: an invertible integer matrix times a chosen
  reduced form, a chosen solution, chosen eigenvalues.
- The worked solution is written step by step, in the stored maths form.
- Answers are typed in cells, as integers, fractions or decimals, read
  exactly and never evaluated. An answer with many right forms (a basis, an
  eigenvector, weights) is checked by what it must satisfy, so any right
  one is accepted.
"""

import random
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from fractions import Fraction

from app import exact as X
from app.exact import Matrix, Vector

F = Fraction

# --- the catalogue -------------------------------------------------------------


@dataclass(frozen=True)
class Kind:
    """A type of exercise: what it asks, shown to the model when it chooses;
    the words a concept's passages must use for it to fit."""

    describes: str
    words: str  # a regular expression, matched without regard to case


KINDS: dict[str, Kind] = {
    "determinant": Kind(
        "the determinant of a 2 by 2 or 3 by 3 matrix", r"determinant|\\det\b"
    ),
    "solve_system": Kind(
        "solving a system of three linear equations with exactly one solution",
        r"system of (linear )?equations|linear system|augmented matrix",
    ),
    "reduced_form": Kind(
        "the reduced row echelon form of a matrix",
        r"row echelon|row reduc|reduced form",
    ),
    "rank": Kind("the rank of a matrix", r"\brank\b"),
    "inverse": Kind(
        "the inverse of a 2 by 2 or 3 by 3 matrix", r"\binverse\b|invertible"
    ),
    "product": Kind(
        "the product of two matrices",
        r"matrix product|product of (two )?matri|matrix multiplication|multiply(ing)? (two )?matri",
    ),
    # Not "kernel": an operating system has one too.
    "null_space": Kind("a basis of the null space of a matrix", r"null ?space"),
    "independence": Kind(
        "whether three vectors are linearly independent",
        r"linearly (in)?dependent|linear (in)?dependence",
    ),
    "eigen": Kind(
        "the eigenvalues of a 2 by 2 matrix and an eigenvector for each",
        r"eigenvalue|eigenvector",
    ),
}


def fits(kind: str, passages: str) -> bool:
    """Whether a concept's passages use the words of this type of exercise:
    the check on the model's choice (decision record 27)."""
    return re.search(KINDS[kind].words, passages, re.IGNORECASE) is not None


# --- an exercise -------------------------------------------------------------------


@dataclass(frozen=True)
class Answer:
    """What was typed, read: the numbers in the cells, and for an exercise
    with a choice, the option chosen (0 or 1)."""

    numbers: tuple[Fraction, ...]
    choice: int | None = None


@dataclass(frozen=True)
class Exercise:
    """One exercise, generated from a seed. form says what the learner fills
    in; key is the answer to show, solution a right answer as it would be
    typed; steps the worked solution, each in the stored maths form; given
    the matrices it was built on, by name; marking checks an answer."""

    kind: str
    prompt: str
    form: dict
    key: str
    solution: Answer
    steps: tuple[str, ...]
    given: dict[str, Matrix]
    marking: Callable[[Answer], "Marking"] = field(repr=False, compare=False)


@dataclass(frozen=True)
class Marking:
    """How an answer went: right or not, which cells were right, and a
    sentence saying what was wrong, if anything."""

    correct: bool
    right: tuple[bool, ...]
    note: str


class Malformed(ValueError):
    """An answer that cannot be read. The message says which cell, and why;
    nothing is recorded."""


# --- reading what was typed ----------------------------------------------------------

_NUMBER = re.compile(r"[+-]?(\d+/\d+|\d+\.\d*|\.\d+|\d+)")
CELL_CHARS = 24


def read(cells: Sequence[str], count: int) -> tuple[Fraction, ...]:
    """The cells as exact numbers: integers, fractions such as 3/4, and
    decimals such as -0.25. Nothing typed is evaluated; anything else is
    Malformed."""
    if len(cells) != count:
        raise Malformed(f"The answer needs {count} numbers; {len(cells)} came.")
    numbers = []
    for i, cell in enumerate(cells, start=1):
        text = cell.replace("−", "-").replace(" ", "")
        if not text:
            raise Malformed(f"Cell {i} is empty.")
        if len(text) > CELL_CHARS or not _NUMBER.fullmatch(text):
            raise Malformed(
                f"Cell {i} is not a number: write an integer, a fraction like 3/4, "
                "or a decimal like 0.5."
            )
        try:
            numbers.append(Fraction(text))
        except ZeroDivisionError:
            raise Malformed(f"Cell {i} divides by zero.") from None
    return tuple(numbers)


def count(form: dict) -> int:
    """How many cells a form has."""
    kind = form["type"]
    if kind == "number":
        return 1
    if kind == "vector":
        return int(form["size"])
    if kind == "matrix":
        return int(form["rows"]) * int(form["columns"])
    if kind == "vectors":
        return int(form["count"]) * int(form["size"])
    if kind == "eigen":
        return int(form["size"]) + int(form["size"]) ** 2
    if kind == "independence":
        return int(form["size"])
    raise ValueError(f"unknown form {kind!r}")


# --- marking ----------------------------------------------------------------------------


def _same(numbers: Sequence[Fraction], key: Sequence[Fraction], what: str) -> Marking:
    right = tuple(x == y for x, y in zip(numbers, key, strict=True))
    if all(right):
        return Marking(True, right, "")
    wrong = right.count(False)
    if len(right) == 1:
        return Marking(False, right, "")
    return Marking(
        False, right, f"{len(right) - wrong} of the {len(right)} {what} are right."
    )


def _flat(a: Matrix) -> tuple[Fraction, ...]:
    return tuple(x for row in a for x in row)


def _chunks(numbers: Sequence[Fraction], size: int) -> list[Vector]:
    return [tuple(numbers[i : i + size]) for i in range(0, len(numbers), size)]


# --- building blocks ------------------------------------------------------------------


def _small(rng: random.Random, low: int = -4, high: int = 4, zero: bool = True) -> int:
    while True:
        x = rng.randint(low, high)
        if zero or x:
            return x


def _unimodular(rng: random.Random, n: int, ops: int = 4, limit: int = 4) -> Matrix:
    """An integer matrix whose determinant is 1 or -1, with small entries:
    the identity changed by a few row additions and perhaps a swap. Its
    inverse is an integer matrix too."""
    while True:
        rows = [list(r) for r in X.identity(n)]
        for _ in range(ops):
            i, j = rng.sample(range(n), 2)
            c = rng.choice([-2, -1, 1, 2])
            rows[i] = [x + c * y for x, y in zip(rows[i], rows[j], strict=True)]
        if rng.random() < 0.5:
            i, j = rng.sample(range(n), 2)
            rows[i], rows[j] = rows[j], rows[i]
        m = X.matrix(rows)
        if X.largest(m) <= limit:
            return m


def _reduced(rng: random.Random, m: int, n: int, r: int) -> Matrix:
    """A matrix already in reduced row echelon form, m by n, of rank r, with
    a pivot in the first column and small entries."""
    while True:
        pivots = sorted(rng.sample(range(n), r))
        if pivots[0] == 0:
            break
    rows = [[F(0)] * n for _ in range(m)]
    for i, p in enumerate(pivots):
        rows[i][p] = F(1)
        for j in range(p + 1, n):
            if j not in pivots:
                rows[i][j] = F(_small(rng, -3, 3))
    return X.matrix(rows)


def _hidden(rng: random.Random, target: Matrix, limit: int = 9) -> Matrix:
    """A matrix whose reduced form is target: target changed by row
    operations that can be undone, so its numbers stay whole and small, and
    reducing it takes a few steps."""
    while True:
        a = X.mul(_unimodular(rng, len(target), ops=3, limit=3), target)
        if X.largest(a) <= limit and len(X.rref(a)[1]) >= 3:
            return a


def _reduction(a: Matrix, steps: list[X.Step], bar: int | None = None) -> list[str]:
    return [f"\\[{X.tex(a, bar)}\\]"] + [
        f"\\(\\xrightarrow{{{op}}}\\) \\[{X.tex(m, bar)}\\]" for op, m in steps
    ]


# --- the exercises ----------------------------------------------------------------------


def _determinant(rng: random.Random) -> Exercise:
    n = rng.choice([2, 3])
    while True:
        a = X.matrix([[_small(rng) for _ in range(n)] for _ in range(n)])
        d = X.det(a)
        if d != 0 and abs(d) <= 60:
            break
    num = X.number
    if n == 2:
        steps = [
            f"\\[\\det A = ({num(a[0][0])})({num(a[1][1])}) - ({num(a[0][1])})({num(a[1][0])}) = {num(d)}\\]"
        ]
    else:
        terms = []
        for j in range(3):
            m = X.minor(a, 0, j)
            sign = "" if j == 0 else (" - " if j == 1 else " + ")
            rows = r" \\ ".join(" & ".join(num(x) for x in row) for row in m)
            terms.append(
                (sign, a[0][j], f"\\begin{{vmatrix}} {rows} \\end{{vmatrix}}", X.det(m))
            )
        steps = [
            "Expand along the first row:",
            "\\[\\det A = "
            + "".join(f"{s}({num(c)}){v}" for s, c, v, _ in terms)
            + "\\]",
            "\\[= "
            + "".join(f"{s}({num(c)})({num(dm)})" for s, c, _, dm in terms)
            + f" = {num(d)}\\]",
        ]
    return Exercise(
        "determinant",
        f"Find the determinant of \\[A = {X.tex(a)}.\\]",
        {"type": "number", "label": "\\det A"},
        f"\\(\\det A = {num(d)}\\)",
        Answer((d,)),
        tuple(steps),
        {"A": a},
        lambda answer: _same(answer.numbers, (d,), "numbers"),
    )


def _solve_system(rng: random.Random) -> Exercise:
    a = _unimodular(rng, 3)
    x = tuple(F(_small(rng, -3, 3)) for _ in range(3))
    b = X.apply(a, x)
    names = ("x", "y", "z")
    equations = []
    for row, value in zip(a, b, strict=True):
        terms = ""
        for c, name in zip(row, names, strict=True):
            if c == 0:
                continue
            sign = "-" if c < 0 else ("+" if terms else "")
            size = "" if abs(c) == 1 else X.number(abs(c))
            terms += f" {sign} {size}{name}"
        equations.append(f"{terms.strip()} &= {X.number(value)}")
    system = r"\[\begin{aligned} " + r" \\ ".join(equations) + r" \end{aligned}\]"
    augmented = X.beside(a, tuple((v,) for v in b))
    _, steps, _ = X.rref(augmented, columns=3)
    solution = ", ".join(f"{n} = {X.number(v)}" for n, v in zip(names, x, strict=True))
    return Exercise(
        "solve_system",
        "Solve the system " + system,
        {"type": "vector", "size": 3, "labels": list(names)},
        f"\\({solution}\\)",
        Answer(x),
        (
            "Row reduce the augmented matrix:",
            *_reduction(augmented, steps, 3),
            f"So \\({solution}\\).",
        ),
        {"A": a, "b": tuple((v,) for v in b)},
        lambda answer: _same(answer.numbers, x, "values"),
    )


def _reduced_form(rng: random.Random) -> Exercise:
    target = _reduced(rng, 3, 4, rng.choice([2, 3]))
    a = _hidden(rng, target)
    reduced, steps, _ = X.rref(a)
    return Exercise(
        "reduced_form",
        f"Find the reduced row echelon form of \\[A = {X.tex(a)}.\\]",
        {"type": "matrix", "rows": 3, "columns": 4},
        f"\\[{X.tex(reduced)}\\]",
        Answer(_flat(reduced)),
        tuple(_reduction(a, steps)),
        {"A": a},
        lambda answer: _same(answer.numbers, _flat(reduced), "entries"),
    )


def _rank(rng: random.Random) -> Exercise:
    a = _hidden(rng, _reduced(rng, 3, 4, rng.choice([2, 3])))
    _, steps, pivots = X.rref(a)
    r = len(pivots)
    return Exercise(
        "rank",
        f"Find the rank of \\[A = {X.tex(a)}.\\]",
        {"type": "number", "label": "\\operatorname{rank} A"},
        f"\\(\\operatorname{{rank}} A = {r}\\)",
        Answer((F(r),)),
        (
            *_reduction(a, steps),
            f"The reduced form has {r} pivots, so the rank is \\({r}\\).",
        ),
        {"A": a},
        lambda answer: _same(answer.numbers, (F(r),), "numbers"),
    )


def _inverse(rng: random.Random) -> Exercise:
    n = rng.choice([2, 3])
    if n == 2:
        while True:
            a = X.matrix([[_small(rng, -5, 5) for _ in range(2)] for _ in range(2)])
            if X.det(a) in (1, -1, 2, -2, 3, -3):
                break
    else:
        a = _unimodular(rng, 3)
    inverse, steps = X.inverse(a)
    assert inverse is not None
    return Exercise(
        "inverse",
        f"Find the inverse of \\[A = {X.tex(a)}.\\]",
        {"type": "matrix", "rows": n, "columns": n},
        f"\\[A^{{-1}} = {X.tex(inverse)}\\]",
        Answer(_flat(inverse)),
        (
            "Row reduce \\([A \\mid I]\\) until the left half is \\(I\\):",
            *_reduction(X.beside(a, X.identity(n)), steps, n),
            f"So \\[A^{{-1}} = {X.tex(inverse)}.\\]",
        ),
        {"A": a},
        lambda answer: _same(answer.numbers, _flat(inverse), "entries"),
    )


def _product(rng: random.Random) -> Exercise:
    m, k, n = rng.choice([(2, 3, 2), (2, 2, 2), (3, 2, 2), (2, 3, 3)])
    a = X.matrix([[_small(rng, -3, 3) for _ in range(k)] for _ in range(m)])
    b = X.matrix([[_small(rng, -3, 3) for _ in range(n)] for _ in range(k)])
    c = X.mul(a, b)
    steps = [
        "Each entry is a row of \\(A\\) times a column of \\(B\\):",
        *(
            f"\\(c_{{{i + 1}{j + 1}}} = "
            + " + ".join(
                f"({X.number(a[i][t])})({X.number(b[t][j])})" for t in range(k)
            )
            + f" = {X.number(c[i][j])}\\)"
            for i in range(m)
            for j in range(n)
        ),
    ]
    return Exercise(
        "product",
        f"Find \\(AB\\) for \\[A = {X.tex(a)}, \\quad B = {X.tex(b)}.\\]",
        {"type": "matrix", "rows": m, "columns": n},
        f"\\[AB = {X.tex(c)}\\]",
        Answer(_flat(c)),
        tuple(steps),
        {"A": a, "B": b},
        lambda answer: _same(answer.numbers, _flat(c), "entries"),
    )


def _null_space(rng: random.Random) -> Exercise:
    a = _hidden(rng, _reduced(rng, 3, 4, 2))
    _, steps, pivots = X.rref(a)
    basis = X.null_space(a)
    free = [j for j in range(4) if j not in pivots]

    def marking(answer: Answer) -> Marking:
        vectors = _chunks(answer.numbers, 4)
        valid = [any(v) and not any(X.apply(a, v)) for v in vectors]
        right = tuple(ok for ok in valid for _ in range(4))
        if not all(valid):
            first = valid.index(False) + 1
            return Marking(
                False,
                right,
                f"Vector {first} is not a nonzero vector in the null space.",
            )
        if X.rank(X.transpose(tuple(vectors))) < len(vectors):
            return Marking(
                False, right, "The vectors are in the null space but not independent."
            )
        return Marking(True, right, "")

    return Exercise(
        "null_space",
        f"Find a basis of the null space of \\[A = {X.tex(a)}.\\]",
        {"type": "vectors", "count": len(basis), "size": 4},
        "For example \\[" + ", \\quad ".join(X.column(v) for v in basis) + "\\]",
        Answer(tuple(x for v in basis for x in v)),
        (
            *_reduction(a, steps),
            "The free variables are "
            + " and ".join(f"\\(x_{{{f + 1}}}\\)" for f in free)
            + ". Setting each to 1 in turn and the other to 0 gives a basis:",
            "\\[" + ", \\quad ".join(X.column(v) for v in basis) + "\\]",
            "Any other basis of the same null space is right too.",
        ),
        {"A": a},
        marking,
    )


def _independence(rng: random.Random) -> Exercise:
    dependent = rng.random() < 0.5
    s, t = _small(rng, -2, 2, zero=False), _small(rng, -2, 2, zero=False)
    target = X.matrix([[1, 0, s], [0, 1, t], [0, 0, 0]]) if dependent else X.identity(3)
    columns = _hidden(rng, target)
    vectors = X.transpose(columns)
    _, steps, _ = X.rref(columns)
    shown = ", \\quad ".join(
        f"v_{i + 1} = {X.column(v)}" for i, v in enumerate(vectors)
    )
    weights: Vector = ()
    if dependent:
        weights = X.null_space(columns)[0]
        key = "Dependent, for example with weights \\[" + X.column(weights) + "\\]"
        last = (
            "The third column has no pivot, so the vectors are dependent. The null "
            f"space gives the weights \\[{X.column(weights)}.\\]"
        )
    else:
        key = "Independent."
        last = "Every column has a pivot, so the vectors are linearly independent."

    def marking(answer: Answer) -> Marking:
        said_dependent = answer.choice == 1
        if said_dependent != dependent:
            return Marking(
                False,
                (False,) * 3,
                "These vectors are dependent."
                if dependent
                else "These vectors are independent.",
            )
        if not dependent:
            return Marking(True, (True,) * 3, "")
        w = answer.numbers
        if not any(w):
            return Marking(False, (False,) * 3, "The weights must not all be zero.")
        if any(X.apply(columns, w)):
            return Marking(
                False, (False,) * 3, "These weights do not give the zero vector."
            )
        return Marking(True, (True,) * 3, "")

    return Exercise(
        "independence",
        f"Are the vectors \\[{shown}\\] linearly independent? If not, give weights "
        "\\(c_1, c_2, c_3\\), not all zero, with \\(c_1v_1 + c_2v_2 + c_3v_3 = 0\\).",
        {"type": "independence", "size": 3, "options": ["Independent", "Dependent"]},
        key,
        Answer(tuple(weights), 1) if dependent else Answer((), 0),
        (
            "Put the vectors in the columns of a matrix and row reduce:",
            *_reduction(columns, steps),
            last,
        ),
        {"V": columns},
        marking,
    )


def _eigen(rng: random.Random) -> Exercise:
    while True:
        values = rng.sample(range(-4, 6), 2)
        p = _unimodular(rng, 2, ops=2, limit=3)
        p_inverse, _ = X.inverse(p)
        assert p_inverse is not None
        a = X.mul(X.mul(p, X.matrix([[values[0], 0], [0, values[1]]])), p_inverse)
        if X.largest(a) <= 9:
            break
    poly = X.characteristic(a)
    roots = X.integer_roots(poly)
    vectors = []
    steps = [
        f"\\[\\det(A - \\lambda I) = {X.polynomial(poly)} = {X.factor(roots[0])}{X.factor(roots[1])}\\]",
        f"So the eigenvalues are \\({roots[0]}\\) and \\({roots[1]}\\).",
    ]
    for value in roots:
        shifted = X.sub(a, X.scaled(X.identity(2), F(value)))
        v = X.null_space(shifted)[0]
        vectors.append(v)
        size = "" if abs(value) == 1 else str(abs(value))  # A - I, not A - 1I
        shift = "A" if value == 0 else (f"A - {size}I" if value > 0 else f"A + {size}I")
        steps.append(
            f"For \\(\\lambda = {value}\\): \\[{shift} = {X.tex(shifted)}\\] "
            f"Its null space is spanned by \\[{X.column(v)}.\\]"
        )
    steps.append("Any nonzero multiple of an eigenvector is right too.")

    def marking(answer: Answer) -> Marking:
        given, rest = answer.numbers[:2], answer.numbers[2:]
        value_right = tuple(sorted(given) == sorted(F(r) for r in roots) for _ in given)
        right_values = sorted(given) == sorted(F(r) for r in roots)
        checks = []
        for value, v in zip(given, _chunks(rest, 2), strict=True):
            shifted = X.sub(a, X.scaled(X.identity(2), value))
            checks.append(any(v) and not any(X.apply(shifted, v)))
        right = value_right + tuple(ok for ok in checks for _ in range(2))
        if not right_values:
            return Marking(False, right, "The eigenvalues are not right.")
        if not all(checks):
            first = checks.index(False) + 1
            return Marking(
                False,
                right,
                f"Vector {first} is not an eigenvector for its eigenvalue.",
            )
        return Marking(True, right, "")

    return Exercise(
        "eigen",
        f"Find the eigenvalues of \\[A = {X.tex(a)}\\] and an eigenvector for each.",
        {"type": "eigen", "size": 2},
        f"Eigenvalues \\({roots[0]}\\) and \\({roots[1]}\\), with eigenvectors \\["
        + ", \\quad ".join(X.column(v) for v in vectors)
        + "\\]",
        Answer((*(F(r) for r in roots), *(x for v in vectors for x in v))),
        tuple(steps),
        {"A": a},
        marking,
    )


_MAKERS: dict[str, Callable[[random.Random], Exercise]] = {
    "determinant": _determinant,
    "solve_system": _solve_system,
    "reduced_form": _reduced_form,
    "rank": _rank,
    "inverse": _inverse,
    "product": _product,
    "null_space": _null_space,
    "independence": _independence,
    "eigen": _eigen,
}
assert set(_MAKERS) == set(KINDS)


def exercise(kind: str, seed: str) -> Exercise:
    """The exercise of this kind for this seed: always the same one."""
    return _MAKERS[kind](random.Random(seed))


def mark(item: Exercise, cells: Sequence[str], choice: int | None = None) -> Marking:
    """Mark what was typed. Malformed if a cell is not a number, or a choice
    is missing where the exercise asks for one."""
    if item.form["type"] == "independence":
        if choice not in (0, 1):
            raise Malformed("Choose whether the vectors are independent.")
        if choice == 0:
            return item.marking(Answer((), choice))
    return item.marking(Answer(read(cells, count(item.form)), choice))
