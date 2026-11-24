"""Planted mistakes: how often the check catches each kind of misreading.

Purpose
-------
The model makes few mistakes on cleanly typeset pages, too few to say how
well the check (app/transcription.py) catches each kind. So mistakes are
planted: a page's perfect reading, its truth, gets exactly one change, of
one kind, in one place, and the check is asked whether the result agrees
with the page's text layer. A reading the check refuses is a mistake caught.

Each kind is a mistake a reader can make with one kind of notation: a sign
flipped, a prime or a hat dropped, a sum read as a product, the bounds of an
integral swapped, two entries of a matrix swapped. For every page whose
truth passes the check (a page whose truth is refused proves nothing about
mistakes), every place a kind can be planted is found, and up to PER_PAGE of
them are chosen at random, the same ones on every run. No model is needed,
and the whole set takes seconds.
"""

import random
import re
from collections.abc import Callable
from dataclasses import dataclass

PER_PAGE = 3

# Formulas in the source Markdown: displayed, then inline.
_FORMULA = re.compile(r"\$\$(.+?)\$\$|\$([^$]+)\$", re.DOTALL)

# One spelling of each letter: \epsilon for \varepsilon is the same letter.
_GREEK = [
    "alpha",
    "beta",
    "gamma",
    "delta",
    "varepsilon",
    "theta",
    "lambda",
    "mu",
    "nu",
    "xi",
    "pi",
    "rho",
    "sigma",
    "tau",
    "varphi",
    "chi",
    "psi",
    "omega",
]


@dataclass(frozen=True)
class Planted:
    kind: str
    page_markdown: str  # the page's truth with the mistake in it
    before: str  # the stretch of the page that was changed
    after: str


# --- edits within one formula ------------------------------------------------------
# Each takes a formula's LaTeX and returns every version of it with one
# mistake of its kind.


def _group_end(latex: str, i: int) -> int:
    """The index just past the braced group opening at latex[i]."""
    depth = 0
    for j in range(i, len(latex)):
        if latex[j] == "\\":
            continue
        if latex[j] == "{" and latex[j - 1 : j] != "\\":
            depth += 1
        elif latex[j] == "}" and latex[j - 1 : j] != "\\":
            depth -= 1
            if depth == 0:
                return j + 1
    return len(latex)


def _argument_end(latex: str, i: int) -> int:
    """The index just past the argument starting at latex[i]: a braced
    group, a command, or one character."""
    if i >= len(latex):
        return i
    if latex[i] == "{":
        return _group_end(latex, i)
    if latex[i] == "\\":
        m = re.match(r"\\[A-Za-z]+|\\.", latex[i:])
        return i + (m.end() if m else 1)
    return i + 1


def _replacements(
    latex: str, pattern: str, replace: Callable[[re.Match], str]
) -> list[str]:
    return [
        latex[: m.start()] + replace(m) + latex[m.end() :]
        for m in re.finditer(pattern, latex)
    ]


def _swap_words(table: dict[str, str]) -> Callable[[str], list[str]]:
    names = "|".join(sorted(table, key=len, reverse=True))

    def edit(latex: str) -> list[str]:
        return _replacements(
            latex, rf"\\({names})(?![A-Za-z])", lambda m: table[m.group(1)]
        )

    return edit


def sign(latex: str) -> list[str]:
    return _replacements(
        latex, r"(?<!\\)[+-]", lambda m: "-" if m.group() == "+" else "+"
    )


def digit(latex: str) -> list[str]:
    return _replacements(
        latex, r"(?<![\\{])\d", lambda m: str((int(m.group()) + 1) % 10)
    )


def _outside_words(latex: str) -> list[tuple[int, int]]:
    """Spans of \\text{...} and environment names, where letters are words."""
    spans = []
    for m in re.finditer(
        r"\\(text|textbf|mathrm|operatorname|begin|end|mathbb|mathcal)\{", latex
    ):
        spans.append((m.start(), _group_end(latex, m.end() - 1)))
    return spans


def letter(latex: str) -> list[str]:
    blocked = _outside_words(latex)
    found = []
    for m in re.finditer(r"(?<![\\A-Za-z])[a-zA-Z](?![A-Za-z])", latex):
        if any(a <= m.start() < b for a, b in blocked):
            continue
        c = m.group()
        new = (
            "y"
            if c == "x"
            else ("x" if c == "y" else chr((ord(c.lower()) - 97 + 1) % 26 + 97))
        )
        new = new.upper() if c.isupper() else new
        found.append(latex[: m.start()] + new + latex[m.end() :])
    return found


def greek(latex: str) -> list[str]:
    table = {g: "\\" + _GREEK[(i + 1) % len(_GREEK)] for i, g in enumerate(_GREEK)}
    table.update({"epsilon": r"\theta", "phi": r"\chi"})  # the other spellings
    return _swap_words(table)(latex)


def delta(latex: str) -> list[str]:
    return _swap_words({"Delta": r"\delta", "delta": r"\Delta"})(latex)


def _dropped_script(mark: str) -> Callable[[str], list[str]]:
    def edit(latex: str) -> list[str]:
        found = []
        for m in re.finditer(re.escape(mark), latex):
            end = _argument_end(latex, m.end())
            found.append(latex[: m.start()] + latex[end:])
        return found

    return edit


superscript = _dropped_script("^")
subscript = _dropped_script("_")


def prime(latex: str) -> list[str]:
    return _replacements(latex, r"'", lambda m: "")


def _unwrapped(commands: str) -> Callable[[str], list[str]]:
    """The command dropped, its argument kept: \\sqrt{2} becomes 2."""

    def edit(latex: str) -> list[str]:
        found = []
        for m in re.finditer(rf"\\({commands})(?![A-Za-z])\s*(\[[^\]]*\])?", latex):
            start = m.end()
            if start < len(latex) and latex[start] == "{":
                end = _group_end(latex, start)
                found.append(
                    latex[: m.start()] + latex[start + 1 : end - 1] + latex[end:]
                )
        return found

    return edit


root = _unwrapped("sqrt")
accent = _unwrapped("hat|widehat|bar|overline|tilde|widetilde|dot|ddot|vec")


def fraction(latex: str) -> list[str]:
    found = []
    for m in re.finditer(r"\\[dt]?frac(?![A-Za-z])\s*", latex):
        top = m.end()
        if top >= len(latex) or latex[top] != "{":
            continue
        bottom = _group_end(latex, top)
        if bottom >= len(latex) or latex[bottom] != "{":
            continue
        end = _group_end(latex, bottom)
        found.append(latex[:top] + latex[bottom:end] + latex[top:bottom] + latex[end:])
    return found


big_operator = _swap_words(
    {
        "sum": r"\prod",
        "prod": r"\sum",
        "int": r"\sum",
        "iint": r"\int",
        "oint": r"\int",
        "bigcup": r"\bigcap",
        "bigcap": r"\bigcup",
    }
)


def bounds(latex: str) -> list[str]:
    """A sum's, product's or integral's lower and upper bounds swapped."""
    found = []
    for m in re.finditer(r"\\(sum|prod|int|bigcup|bigcap)(?![A-Za-z])", latex):
        i = m.end()
        if latex[i : i + 1] != "_":
            continue
        low_end = _argument_end(latex, i + 1)
        if latex[low_end : low_end + 1] != "^":
            continue
        high_end = _argument_end(latex, low_end + 1)
        low, high = latex[i + 1 : low_end], latex[low_end + 1 : high_end]
        if low.strip("{} ") == high.strip("{} "):
            continue
        swapped = f"_{{{high.strip('{}')}}}^{{{low.strip('{}')}}}"
        found.append(latex[:i] + swapped + latex[high_end:])
    return found


def partial(latex: str) -> list[str]:
    return _replacements(latex, r"\\partial(?![A-Za-z])\s*", lambda m: "d")


set_relation = _swap_words(
    {
        "in": r"\notin",
        "notin": r"\in",
        "subseteq": r"\supseteq",
        "subset": r"\supset",
        "supseteq": r"\subseteq",
        "supset": r"\subset",
    }
)
set_operation = _swap_words({"cup": r"\cap", "cap": r"\cup", "setminus": r"\cap"})
logic = _swap_words(
    {
        "forall": r"\exists",
        "exists": r"\forall",
        "land": r"\lor",
        "lor": r"\land",
        "implies": r"\iff",
        "iff": r"\implies",
    }
)


def relation(latex: str) -> list[str]:
    swapped = _swap_words(
        {
            "leq": r"\geq",
            "geq": r"\leq",
            "le": r"\ge",
            "ge": r"\le",
            "neq": "=",
            "ne": "=",
            "approx": "=",
            "equiv": "=",
            "ll": r"\gg",
        }
    )(latex)
    return swapped + _replacements(
        latex, r"(?<!\\)[<>]", lambda m: ">" if m.group() == "<" else "<"
    )


_ENVIRONMENT = re.compile(
    r"(\\begin\{(?:[pbBvV]?matrix|array)\}(?:\{[^}]*\})?)(.*?)(\\end\{(?:[pbBvV]?matrix|array)\})",
    re.DOTALL,
)


def _cells(body: str) -> list[list[str]]:
    return [row.split("&") for row in re.split(r"\\\\", body)]


def _joined(rows: list[list[str]]) -> str:
    return r"\\".join("&".join(row) for row in rows)


def entry(latex: str) -> list[str]:
    """One cell of a matrix left empty."""
    found = []
    for m in _ENVIRONMENT.finditer(latex):
        rows = _cells(m.group(2))
        for r, row in enumerate(rows):
            for c, cell in enumerate(row):
                if cell.strip():
                    changed = [list(x) for x in rows]
                    changed[r][c] = " "
                    found.append(
                        latex[: m.start(2)] + _joined(changed) + latex[m.end(2) :]
                    )
    return found


def swapped_entries(latex: str) -> list[str]:
    """Two different cells of one row of a matrix swapped."""
    found = []
    for m in _ENVIRONMENT.finditer(latex):
        rows = _cells(m.group(2))
        for r, row in enumerate(rows):
            for c in range(len(row) - 1):
                if (
                    row[c].strip()
                    and row[c + 1].strip()
                    and row[c].strip() != row[c + 1].strip()
                ):
                    changed = [list(x) for x in rows]
                    changed[r][c], changed[r][c + 1] = row[c + 1], row[c]
                    found.append(
                        latex[: m.start(2)] + _joined(changed) + latex[m.end(2) :]
                    )
    return found


# --- the kinds ---------------------------------------------------------------------


@dataclass(frozen=True)
class Kind:
    name: str
    label: str
    edit: Callable[[str], list[str]] | None  # within a formula; None for page edits


KINDS: tuple[Kind, ...] = (
    Kind("sign", "A sign flipped (+ and −)", sign),
    Kind("digit", "A digit changed", digit),
    Kind("letter", "A variable's letter changed", letter),
    Kind("greek", "A Greek letter changed", greek),
    Kind("delta", "Δ read as δ, or δ as Δ", delta),
    Kind("superscript", "A superscript dropped", superscript),
    Kind("subscript", "A subscript dropped", subscript),
    Kind("prime", "A prime dropped (f′ read as f)", prime),
    Kind("root", "A square root dropped", root),
    Kind("accent", "An accent dropped (hat, bar, dot, arrow)", accent),
    Kind("fraction", "A fraction turned upside down", fraction),
    Kind("big_operator", "A big operator changed (Σ for ∫, Π for Σ)", big_operator),
    Kind("bounds", "A sum's or integral's bounds swapped", bounds),
    Kind("partial", "∂ read as d", partial),
    Kind("set_relation", "A set relation reversed (∈ and ∉, ⊆ and ⊇)", set_relation),
    Kind("set_operation", "A set operation changed (∪ and ∩)", set_operation),
    Kind("logic", "A quantifier or connective changed (∀ and ∃, ∧ and ∨)", logic),
    Kind("relation", "A relation changed (≤ and ≥, ≠ read as =)", relation),
    Kind("entry", "A matrix entry left out", entry),
    Kind("swapped_entries", "Two matrix entries swapped", swapped_entries),
    Kind("word", "A word of the prose left out", None),
    Kind("formula", "A displayed formula left out", None),
)
BY_NAME = {kind.name: kind for kind in KINDS}


def _candidates(markdown: str, kind: Kind) -> list[Planted]:
    found = []
    if kind.name == "word":
        prose = list(_prose_words(markdown))
        for start, end in prose:
            cut_end = end + 1 if markdown[end : end + 1] == " " else end
            found.append(
                Planted(
                    kind.name,
                    markdown[:start] + markdown[cut_end:],
                    markdown[start:end],
                    "",
                )
            )
        return found
    for m in _FORMULA.finditer(markdown):
        if kind.name == "formula":
            if m.group(1) is not None:
                found.append(
                    Planted(
                        kind.name,
                        markdown[: m.start()] + markdown[m.end() :],
                        m.group(),
                        "",
                    )
                )
            continue
        assert kind.edit is not None
        body_start, body_end = (
            (m.start(1), m.end(1)) if m.group(1) is not None else (m.start(2), m.end(2))
        )
        latex = markdown[body_start:body_end]
        for changed in kind.edit(latex):
            if changed != latex:
                found.append(
                    Planted(
                        kind.name,
                        markdown[:body_start] + changed + markdown[body_end:],
                        latex,
                        changed,
                    )
                )
    return found


def _prose_words(markdown: str):
    """Spans of the words of four letters or more outside any formula and
    any heading mark."""
    formulas = [(m.start(), m.end()) for m in _FORMULA.finditer(markdown)]
    for m in re.finditer(r"(?<![\\$\w])[A-Za-z]{4,}(?![\w$])", markdown):
        if not any(a <= m.start() < b for a, b in formulas):
            yield m.start(), m.end()


def plant(markdown: str, kind: Kind, seed: str) -> list[Planted]:
    """Up to PER_PAGE mistakes of the kind in the page, chosen the same way
    every run for the same seed."""
    found = _candidates(markdown, kind)
    rng = random.Random(seed)
    return rng.sample(found, min(PER_PAGE, len(found)))
