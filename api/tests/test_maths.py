"""Tests for maths in text, app/maths.py.

Purpose: formulas are found between \\( \\) and \\[ \\] and nowhere else;
what the model writes between dollar signs is moved there, money is not, and
the damage JSON's escaping does to LaTeX is repaired; a formula that would
not render, or uses a refused command, is named with its reason; prose rules
never see inside formulas. The model's answers quoted here are real ones,
from the prototype in decision record 24.
"""

import json

import pytest

from app import maths
from app.maths import (
    for_model,
    formulas,
    from_model,
    problem,
    prose,
    sizes,
    spans,
)


def test_the_model_is_shown_formulas_in_the_notation_it_writes() -> None:
    stored = r"Let \(A\) be \[\det A = 1\], at $5."
    shown = for_model(stored)
    assert shown == r"Let $A$ be $$\det A = 1$$, at $5."
    # What it copies back is stored as it was.
    assert from_model(shown) == stored


def test_spans_split_prose_and_formulas() -> None:
    text = r"Let \(A\) be \[\det A = 1\] here."
    found, trouble = spans(text)
    assert trouble is None
    assert [(s.kind, text[s.start : s.end]) for s in found] == [
        ("prose", "Let "),
        ("inline", r"\(A\)"),
        ("prose", " be "),
        ("display", r"\[\det A = 1\]"),
        ("prose", " here."),
    ]
    assert formulas(text) == ["A", r"\det A = 1"]


def test_a_row_break_inside_a_formula_is_not_a_delimiter() -> None:
    text = r"\(\begin{pmatrix} 1 \\ 2 \end{pmatrix}\)"
    assert formulas(text) == [r"\begin{pmatrix} 1 \\ 2 \end{pmatrix}"]
    assert problem(text) is None


def test_dollars_are_never_formulas_once_stored() -> None:
    assert formulas("It costs $5 and $x$ means nothing here.") == []


@pytest.mark.parametrize(
    ("raw_json", "stored"),
    [
        # Real answers: JSON read "\b" as a backspace, and "\\" (a row break)
        # as one backslash.
        (
            r'{"x": "the matrix $A = \begin{pmatrix} 5 & 2 \\ 2 & 1 \\end{pmatrix}$?"}',
            r"the matrix \(A = \begin{pmatrix} 5 & 2 \\ 2 & 1 \end{pmatrix}\)?",
        ),
        (
            r'{"x": "$\\det \\begin{pmatrix} 5 - \\lambda & 2 \\ 2 & 1 - \\lambda \\end{pmatrix}$"}',
            r"\(\det \begin{pmatrix} 5 - \lambda & 2 \\ 2 & 1 - \lambda \end{pmatrix}\)",
        ),
        (
            r'{"x": "$f(\\lambda) = \\lambda^2 - 6\\lambda + 1$"}',
            r"\(f(\lambda) = \lambda^2 - 6\lambda + 1\)",
        ),
        # \f, \t, \r and \n read as control characters, even first in a
        # formula, where they look like a space after the $.
        (r'{"x": "$$\frac{1}{2}$$"}', r"\[\frac{1}{2}\]"),
        (
            r'{"x": "$\times$, $\rho$, $\tau$, $\nabla f$"}',
            r"\(\times\), \(\rho\), \(\tau\), \(\nabla f\)",
        ),
        # Formulas the model already wrote in the stored form are kept.
        (r'{"x": "\\(\\lambda\\) and \\[x^2\\]"}', r"\(\lambda\) and \[x^2\]"),
    ],
)
def test_from_model_moves_and_repairs_formulas(raw_json: str, stored: str) -> None:
    text = from_model(json.loads(raw_json)["x"])
    assert text == stored
    assert problem(text) is None


@pytest.mark.parametrize(
    "money",
    [
        "It costs $5 and $10.",
        "Between $5-$10 a month.",
        "A $ sign alone, and $ spaced $ out.",
        r"An escaped \$5 and \$6.",
    ],
)
def test_money_stays_money(money: str) -> None:
    assert from_model(money) == money


def test_a_newline_is_only_repaired_when_it_makes_a_command() -> None:
    # A real line break inside a formula stays one; "\n" before "eq" was
    # "\neq".
    assert from_model("$a\nx$") == "\\(a\nx\\)"
    assert from_model("$a \neq b$") == r"\(a \neq b\)"


def test_a_lone_backslash_is_only_a_row_break_inside_rows() -> None:
    # Inside a matrix it was "\\"; outside, "\ " is LaTeX's own spacing.
    assert from_model(r"$\begin{matrix} a \ b \end{matrix}$") == (
        r"\(\begin{matrix} a \\ b \end{matrix}\)"
    )
    assert from_model(r"$a \ b$") == r"\(a \ b\)"


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        (r"\(\frac{1}{2\)", "a { with no }"),
        (r"\(x}\)", "a } with no {"),
        (r"\(x\) and \(y", "a formula is not closed"),
        (r"a \) b", "a formula is closed but never opened"),
        (r"\(\[x\]\)", "a formula opens or closes inside another"),
        (r"\(\foo\)", r"an unknown command \foo"),
        (r"\(\begin{foo}x\end{foo}\)", "an unknown environment foo"),
        (
            r"\(\begin{pmatrix}1\end{bmatrix}\)",
            r"\end{bmatrix} does not match its \begin",
        ),
        (r"\(\begin{pmatrix}1\)", r"\begin{pmatrix} with no \end"),
        (r"\(\begin x\)", r"\begin without an environment"),
        (r"\(\left( x\)", r"a \left with no \right"),
        (r"\(x \right)\)", r"a \right with no \left"),
        (r"\(50%\)", "a % inside a formula, which hides the rest of it"),
        (r"\(a $ b\)", "a $ inside a formula"),
        (r"\( \)", "an empty formula"),
        (
            "\x0crac{1}{2}",
            "a control character, the remains of LaTeX outside a formula",
        ),
        (r"\(\def\x{1}\)", r"\def, which defines commands"),
        (r"\(\newcommand{\R}{x}\)", r"\newcommand, which defines commands"),
        (r"\(\href{javascript:alert(1)}{x}\)", r"\href, which links, images or HTML"),
        (r"\(\htmlClass{x}{y}\)", r"\htmlClass, which links, images or HTML"),
        (r"\(\show\x\)", r"\show, which writes to the console"),
        (r"\(\verb|x|\)", r"\verb, which verbatim text"),
    ],
)
def test_problem_names_what_would_not_render(text: str, reason: str) -> None:
    assert problem(text) == reason


@pytest.mark.parametrize(
    "fine",
    [
        "No maths at all, at $5.",
        r"\(\{x \mid x > 0\}\) and \(\|v\|\) and \(|A|\)",
        r"\(50\%\) and \(\$5\)",
        r"\[\left( \frac{1}{2} \right) \begin{cases} 1 & x > 0 \\ 0 & \text{else} \end{cases}\]",
        r"\(\mathbb{R}^n\), \(\operatorname{rank} A\), \(A^\top\), \(\lambda_0\)",
        "Two lines\nof prose.",
    ],
)
def test_problem_accepts_what_renders(fine: str) -> None:
    assert problem(fine) is None


def test_refused_commands_are_ones_katex_knows() -> None:
    # Refusing a command KaTeX does not know would be a typo here.
    assert set(maths.REFUSED) <= maths.COMMANDS


def test_prose_hides_formulas_from_prose_rules() -> None:
    text = r"Is |x| equal to \(|A| = 2*3\)?"
    hidden, restore = prose(text)
    assert "|A|" not in hidden and "*" not in hidden
    assert "|x|" in hidden
    assert restore(hidden.upper()) == r"IS |X| EQUAL TO \(|A| = 2*3\)?"


def test_sizes_count_prose_and_latex_apart() -> None:
    text = r"Find \(\det\begin{pmatrix}1&2\\3&4\end{pmatrix}\) now."
    # "Find " + one for the formula + " now." is 11; the LaTeX is 40.
    assert sizes(text) == (11, 40)
