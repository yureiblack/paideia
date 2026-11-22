"""Exact linear algebra on fractions, for exercises and their worked
solutions (decision record 27).

Purpose
-------
The model is weak at arithmetic, so exercises are never computed by it. This
module computes them exactly, with Python's own Fraction: no rounding, and
no dependency (record 24 chose against sympy, since a worked solution needs
every step, and sympy gives results, not steps).

Matrices are tuples of rows of Fraction, small enough for exercises: at most
a few rows and columns. Row reduction records each operation and the matrix
after it, which is what a worked solution shows. Everything is pure.
"""

from collections.abc import Iterable, Sequence
from fractions import Fraction
from math import gcd, lcm

Matrix = tuple[tuple[Fraction, ...], ...]
Vector = tuple[Fraction, ...]
# One step of a row reduction: the operation, in LaTeX, and the matrix after.
Step = tuple[str, Matrix]


def matrix(rows: Iterable[Iterable[int | Fraction]]) -> Matrix:
    return tuple(tuple(Fraction(x) for x in row) for row in rows)


def identity(n: int) -> Matrix:
    return tuple(tuple(Fraction(int(i == j)) for j in range(n)) for i in range(n))


def mul(a: Matrix, b: Matrix) -> Matrix:
    return tuple(
        tuple(
            sum((a[i][k] * b[k][j] for k in range(len(b))), Fraction(0))
            for j in range(len(b[0]))
        )
        for i in range(len(a))
    )


def apply(a: Matrix, v: Sequence[Fraction]) -> Vector:
    """The matrix times a vector."""
    return tuple(
        sum((x * y for x, y in zip(row, v, strict=True)), Fraction(0)) for row in a
    )


def sub(a: Matrix, b: Matrix) -> Matrix:
    return tuple(
        tuple(x - y for x, y in zip(r, s, strict=True))
        for r, s in zip(a, b, strict=True)
    )


def scaled(a: Matrix, c: Fraction) -> Matrix:
    return tuple(tuple(c * x for x in row) for row in a)


def transpose(a: Matrix) -> Matrix:
    return tuple(tuple(col) for col in zip(*a, strict=True))


def beside(a: Matrix, b: Matrix) -> Matrix:
    """[A | B]: b's columns after a's."""
    return tuple(r + s for r, s in zip(a, b, strict=True))


def largest(a: Matrix) -> Fraction:
    """The largest absolute entry: how big an exercise's numbers are."""
    return max((abs(x) for row in a for x in row), default=Fraction(0))


# --- row reduction -----------------------------------------------------------------


def _row(i: int) -> str:
    return f"R_{{{i + 1}}}"


def rref(a: Matrix, columns: int | None = None) -> tuple[Matrix, list[Step], list[int]]:
    """Gauss-Jordan elimination on the first `columns` columns (all of them
    by default): the reduced row echelon form, each step, and the pivot
    columns. The pivot row is one whose entry is 1 or -1 if there is one,
    otherwise the smallest, to keep the numbers small."""
    rows = [list(r) for r in a]
    m = len(rows)
    columns = len(rows[0]) if columns is None else columns
    steps: list[Step] = []
    pivots: list[int] = []

    def now() -> Matrix:
        return tuple(tuple(r) for r in rows)

    r = 0
    for c in range(columns):
        if r == m:
            break
        found = [i for i in range(r, m) if rows[i][c] != 0]
        if not found:
            continue
        best = min(found, key=lambda i: (abs(rows[i][c]) != 1, abs(rows[i][c]), i))
        if best != r:
            rows[r], rows[best] = rows[best], rows[r]
            steps.append((f"{_row(r)} \\leftrightarrow {_row(best)}", now()))
        p = rows[r][c]
        if p != 1:
            rows[r] = [x / p for x in rows[r]]
            factor = "-" if p == -1 else number(1 / p)
            steps.append((f"{_row(r)} \\to {factor}{_row(r)}", now()))
        for i in range(m):
            f = rows[i][c]
            if i != r and f != 0:
                rows[i] = [x - f * y for x, y in zip(rows[i], rows[r], strict=True)]
                sign = "-" if f > 0 else "+"
                size = "" if abs(f) == 1 else number(abs(f))
                steps.append(
                    (f"{_row(i)} \\to {_row(i)} {sign} {size}{_row(r)}", now())
                )
        pivots.append(c)
        r += 1
    return now(), steps, pivots


def rank(a: Matrix) -> int:
    return len(rref(a)[2])


def minor(a: Matrix, i: int, j: int) -> Matrix:
    """The matrix without row i and column j."""
    return tuple(
        tuple(x for k, x in enumerate(row) if k != j)
        for r, row in enumerate(a)
        if r != i
    )


def det(a: Matrix) -> Fraction:
    """The determinant, by cofactor expansion along the first row: exact,
    and quick for the small matrices of exercises."""
    n = len(a)
    if n == 1:
        return a[0][0]
    if n == 2:
        return a[0][0] * a[1][1] - a[0][1] * a[1][0]
    return sum(
        ((-1) ** j * a[0][j] * det(minor(a, 0, j)) for j in range(n)), Fraction(0)
    )


def inverse(a: Matrix) -> tuple[Matrix | None, list[Step]]:
    """The inverse, by row reducing [A | I], with its steps; None if the
    matrix is not invertible."""
    n = len(a)
    reduced, steps, pivots = rref(beside(a, identity(n)), columns=n)
    if pivots != list(range(n)):
        return None, steps
    return tuple(row[n:] for row in reduced), steps


def whole(v: Sequence[Fraction]) -> Vector:
    """The vector scaled to the smallest whole numbers in the same direction,
    its first nonzero entry positive: (1/2, 1) becomes (1, 2)."""
    ints = [int(x * lcm(*(y.denominator for y in v))) for x in v]
    common = gcd(*ints) or 1
    sign = -1 if next((x for x in ints if x), 1) < 0 else 1
    return tuple(Fraction(sign * x // common) for x in ints)


def null_space(a: Matrix) -> list[Vector]:
    """A basis of the null space, read off the reduced form: each free
    variable set to 1 in turn and the others to 0, scaled to whole numbers."""
    reduced, _, pivots = rref(a)
    n = len(a[0])
    basis = []
    for free in (j for j in range(n) if j not in pivots):
        v = [Fraction(0)] * n
        v[free] = Fraction(1)
        for row, p in zip(reduced, pivots, strict=False):
            v[p] = -row[free]
        basis.append(whole(v))
    return basis


def characteristic(a: Matrix) -> list[Fraction]:
    """The coefficients of λ² - (trace)λ + det, for a 2 by 2 matrix: its
    characteristic polynomial, highest power first."""
    if len(a) != 2:
        raise ValueError("Only 2 by 2 matrices are supported.")
    return [Fraction(1), -(a[0][0] + a[1][1]), det(a)]


def integer_roots(coefficients: Sequence[Fraction]) -> list[int]:
    """The integer roots of a polynomial with integer coefficients, with
    multiplicity, smallest first, found among the divisors of its constant
    term. Exercises are built to have them."""
    coefficients = list(coefficients)
    roots: list[int] = []
    while len(coefficients) > 1:
        if coefficients[-1] == 0:
            roots.append(0)
            coefficients = coefficients[:-1]
            continue
        constant = abs(int(coefficients[-1]))
        root = next(
            (
                r
                for d in range(1, constant + 1)
                if constant % d == 0
                for r in (d, -d)
                if _value(coefficients, Fraction(r)) == 0
            ),
            None,
        )
        if root is None:
            break
        roots.append(root)
        quotient = [coefficients[0]]
        for k in coefficients[1:-1]:
            quotient.append(k + quotient[-1] * root)
        coefficients = quotient
    return sorted(roots)


def _value(coefficients: Sequence[Fraction], x: Fraction) -> Fraction:
    total = Fraction(0)
    for k in coefficients:
        total = total * x + k
    return total


# --- LaTeX --------------------------------------------------------------------------


def number(x: Fraction | int) -> str:
    """A number in LaTeX: 3, -2, \\tfrac{3}{4}, -\\tfrac{1}{2}."""
    x = Fraction(x)
    if x.denominator == 1:
        return str(x.numerator)
    sign = "-" if x < 0 else ""
    return f"{sign}\\tfrac{{{abs(x.numerator)}}}{{{x.denominator}}}"


def tex(a: Matrix, bar: int | None = None) -> str:
    """A matrix in LaTeX. bar draws a line before that column, as in an
    augmented matrix."""
    rows = r" \\ ".join(" & ".join(number(x) for x in row) for row in a)
    if bar is None:
        return f"\\begin{{pmatrix}} {rows} \\end{{pmatrix}}"
    columns = "c" * bar + "|" + "c" * (len(a[0]) - bar)
    return f"\\left(\\begin{{array}}{{{columns}}} {rows} \\end{{array}}\\right)"


def column(v: Sequence[Fraction]) -> str:
    """A vector, written as a column."""
    return tex(tuple((x,) for x in v))


def polynomial(coefficients: Sequence[Fraction], variable: str = "\\lambda") -> str:
    """A polynomial in LaTeX with its signs tidied: λ^2 - 6λ + 1."""
    n = len(coefficients) - 1
    out = ""
    for i, k in enumerate(coefficients):
        power = n - i
        if k == 0:
            continue
        size = abs(k)
        body = (
            number(size)
            if power == 0
            else ("" if size == 1 else number(size))
            + variable
            + (f"^{{{power}}}" if power > 1 else "")
        )
        if not out:
            out = ("-" if k < 0 else "") + body
        else:
            out += (" - " if k < 0 else " + ") + body
    return out or "0"


def factor(root: int, variable: str = "\\lambda") -> str:
    """(λ - 3), (λ + 2), or λ for a root of 0."""
    if root == 0:
        return variable
    return f"({variable} - {root})" if root > 0 else f"({variable} + {-root})"
