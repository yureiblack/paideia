"""Comparing a page's reading with what the page truly says, formula by
formula.

Purpose
-------
A reading is right when it says what the page says, not when it is written
the way the source was. A model may write \\dfrac for \\frac, \\quad for
\\qquad, a bracketed matrix where the page has round brackets, or leave out a
thin space; none of that changes the maths. It may also move a formula out of
a sentence onto a line of its own, split one formula in two, or write "det"
as a word next to the formula instead of inside it. And it may drop a minus
sign, which changes everything.

So both texts, as the app stores them, are turned into one stream each: the
words of the prose and the tokens of the maths, in reading order, with the
formulas' boundaries forgotten. Presentation is normalised away first (see
_PRESENTATION below). The two streams are aligned, and a formula of the page
is read right when every one of its tokens is matched, in order, in the
reading. A formula with any token changed, missing or added inside it is
wrong, and the changed tokens say how (_change()).

What is normalised away is a choice, listed here so that it can be argued
with: spacing commands, \\left and \\right and size commands, \\displaystyle;
the bracket style of a matrix (round, square or curly, never bars, which
mean a determinant); \\dfrac and \\tfrac for \\frac; font commands (bold,
upright, script and the like) and \\vec, counted apart as styling, since a
bold x and a plain x are the same variable to a reader; braces around a
single token; \\le for \\leq and the other spellings of one symbol; commas
and semicolons, which a reader may put inside a formula or between two;
and a full stop that ends a formula, which belongs to the sentence. Everything
else counts: signs, digits, letters, Greek letters, operators, relations,
accents such as hats and bars, primes, scripts, roots, fractions and the
cells of a matrix.
"""

import difflib
import re
from dataclasses import dataclass, field

from app import maths

# Commands that only space or size what they touch.
_SPACING = {
    r"\,", r"\;", r"\:", r"\!", r"\>", r"\ ", "~", r"\quad", r"\qquad", r"\left", r"\right",
    r"\middle", r"\big", r"\Big", r"\bigg", r"\Bigg", r"\bigl", r"\bigr", r"\Bigl", r"\Bigr",
    r"\biggl", r"\biggr", r"\displaystyle", r"\textstyle", r"\limits", r"\nolimits",
}  # fmt: skip
# Commands that set a letter's style, not which letter it is.
_STYLING = {
    r"\mathbf", r"\boldsymbol", r"\bm", r"\mathrm", r"\mathit", r"\mathsf", r"\mathtt",
    r"\vec",
}  # fmt: skip
# Commands that hold words.
_TEXT = {r"\text", r"\textbf", r"\textit", r"\textrm", r"\mbox"}
# Two spellings of one symbol.
_SAME = {
    r"\dfrac": r"\frac", r"\tfrac": r"\frac", r"\le": r"\leq", r"\ge": r"\geq",
    r"\ne": r"\neq", r"\ldots": r"\dots", r"\cdots": r"\dots", r"\dotsc": r"\dots",
    r"\dotsb": r"\dots", r"\lvert": "|", r"\rvert": "|", r"\vert": "|", r"\mid": "|",
    r"\lVert": r"\|", r"\rVert": r"\|", r"\Vert": r"\|", r"\to": r"\rightarrow",
    r"\gets": r"\leftarrow", r"\implies": r"\Rightarrow", r"\iff": r"\Leftrightarrow",
    r"\lbrace": r"\{", r"\rbrace": r"\}", r"\land": r"\wedge", r"\lor": r"\vee",
    r"\lnot": r"\neg", r"\varnothing": r"\emptyset", r"\epsilon": r"\varepsilon",
    r"\phi": r"\varphi", r"\colon": ":", "−": "-", "′": "'", r"\prime": "'",
    r"\top": "T", r"\intercal": "T", r"\cdotp": r"\cdot", r"\xrightarrow": r"\rightarrow",
    r"\longrightarrow": r"\rightarrow", r"\%": "%",
}  # fmt: skip
# Matrices whose brackets are only their look; an augmented matrix's array
# is one too, its bar a rule.
_MATRIX = {"matrix", "pmatrix", "bmatrix", "Bmatrix", "smallmatrix", "array"}
# Environments that only line a derivation up: their & and \\ are layout.
_ALIGNMENT = {
    "aligned",
    "align",
    "gathered",
    "gather",
    "split",
    "eqnarray",
    "alignat",
    "alignedat",
}
# Function names typeset upright: the same whether written inside a formula
# or as a word beside it.
_WORDS = {
    "det", "dim", "ker", "rank", "sin", "cos", "tan", "log", "ln", "exp", "lim", "max",
    "min", "sup", "inf", "gcd", "arg", "mod", "tr", "span", "nul", "col", "var", "cov",
    "re", "im", "fl", "bin",
}  # fmt: skip

_TOKEN = re.compile(r"\\[A-Za-z]+|\\.|[A-Za-z]+|\d|\S")
# Words and digits of prose, a decimal point, and the signs of maths a
# reader may write outside a formula: "a + sign", "0.34375".
_PROSE_WORD = re.compile(r"[^\W\d_]+|\d|(?<=\d)\.(?=\d)|[+=<>]")


@dataclass(frozen=True)
class Formula:
    latex: str  # as stored
    start: int  # its tokens are stream[start:end]
    end: int


@dataclass(frozen=True)
class Stream:
    items: tuple[str, ...]
    formulas: tuple[Formula, ...]
    styling: int  # styling commands met and set aside


def _group(tokens: list[str], i: int) -> int:
    """The index just past the braced group that opens at tokens[i]."""
    depth = 0
    for j in range(i, len(tokens)):
        if tokens[j] == "{":
            depth += 1
        elif tokens[j] == "}":
            depth -= 1
            if depth == 0:
                return j + 1
    return len(tokens)


def tokens(latex: str) -> tuple[list[str], int]:
    """A formula's tokens with its presentation normalised away, and how
    many styling commands were set aside."""
    raw = _TOKEN.findall(latex)
    out: list[str] = []
    aligned: list[str] = []  # the alignment environments open
    inside: list[str] = []  # the other environments open
    styled = 0
    i = 0
    while i < len(raw):
        t = raw[i]
        opens_group = raw[i + 1 : i + 2] == ["{"]
        if t in (r"\begin", r"\end") and opens_group:
            close = _group(raw, i + 1)
            name = "".join(raw[i + 2 : close - 1]).rstrip("*")
            if name == "array" and t == r"\begin" and raw[close : close + 1] == ["{"]:
                close = _group(raw, close)  # the column layout, such as cc|c
            if name in _MATRIX:
                name = "matrix"
            if name in _ALIGNMENT:
                (aligned.append if t == r"\begin" else _pop(aligned))(name)
            else:
                out.append(f"{t}{{{name}}}")
                (inside.append if t == r"\begin" else _pop(inside))(name)
            i = close
            continue
        if t in ("&", r"\\") and aligned and not inside:
            i += 1  # lining up a derivation
            continue
        if t == "|" and inside[-1:] == ["matrix"]:
            i += 1  # the bar of an augmented matrix, written as a cell
            continue
        if t in _TEXT and opens_group:
            # Words in a formula, \text{if }: the same words as in prose.
            close = _group(raw, i + 1)
            out.extend(w.lower() for w in raw[i + 2 : close - 1] if w.isalnum())
            styled += 1
            i = close
            continue
        if t == r"\operatorname" and opens_group:
            close = _group(raw, i + 1)
            out.append("".join(raw[i + 2 : close - 1]).lower())
            styled += 1
            i = close
            continue
        if t in _SPACING or t in (",", ";", r"\%", "%"):
            i += 1  # spacing, the commas between a formula's parts, a percent sign
            continue
        if t in _STYLING:
            styled += 1
            i += 1
            continue
        t = _SAME.get(t, t)
        if t.startswith("\\") and t[1:].lower() in _WORDS:
            out.append(t[1:].lower())
        elif re.fullmatch(r"[A-Za-z]{2,}", t):
            out.extend(t)  # the letters of a formula are variables, one by one
        else:
            out.append(t)
        i += 1
    # Braces around one token say nothing: x^{2} is x^2.
    changed = True
    while changed:
        changed = False
        for j in range(len(out) - 2):
            if out[j] == "{" and out[j + 2] == "}" and out[j + 1] not in "{}":
                del out[j + 2]
                del out[j]
                changed = True
                break
    out = _tidied(out)
    # A formula's last full stop belongs to its sentence.
    while out and out[-1] == ".":
        out.pop()
    return out, styled


def _pop(stack: list[str]):
    """A function that closes the innermost environment, if any is open."""
    return lambda name: stack.pop() if stack else None


def _tidied(out: list[str]) -> list[str]:
    """Layout left over once a matrix's bars and an alignment's marks are
    gone: two cell breaks in a row, the brackets drawn around a matrix, and
    the script mark of a labelled arrow (\\xrightarrow{...} is \\rightarrow
    with a label, however it is written)."""
    tidy: list[str] = []
    for n, t in enumerate(out):
        if t == "&" and tidy[-1:] == ["&"]:
            continue
        if t in ("[", "(") and out[n + 1 : n + 2] == [r"\begin{matrix}"]:
            continue
        if t in ("]", ")") and tidy[-1:] == [r"\end{matrix}"]:
            continue
        if (
            t in ("_", "^")
            and tidy[-1:] == [r"\rightarrow"]
            and out[n + 1 : n + 2] == ["{"]
        ):
            continue
        tidy.append(t)
    return tidy


def stream(text: str) -> Stream:
    """A page's stored text as one stream of prose words and maths tokens."""
    spans, _ = maths.spans(text)
    items: list[str] = []
    formulas: list[Formula] = []
    styled = 0
    for span in spans:
        body = text[span.body_start : span.body_end]
        if span.kind == "prose":
            items.extend(word.lower() for word in _PROSE_WORD.findall(body))
            continue
        found, n = tokens(body)
        styled += n
        formulas.append(Formula(body, len(items), len(items) + len(found)))
        items.extend(found)
    return Stream(tuple(items), tuple(formulas), styled)


@dataclass(frozen=True)
class Change:
    page: tuple[str, ...]  # the page's tokens
    reading: tuple[str, ...]  # what the reading has in their place

    @property
    def kind(self) -> str:
        """How the reading differs: left out, added, or what was changed."""
        return _change(self.page, self.reading)


@dataclass(frozen=True)
class FormulaResult:
    latex: str
    right: bool
    changes: tuple[Change, ...] = ()


@dataclass(frozen=True)
class Comparison:
    formulas: tuple[FormulaResult, ...]
    maths_tokens: int  # tokens in the page's formulas
    maths_errors: int  # of them, changed or missing, and tokens added among them
    prose_words: int
    prose_errors: int
    styling: int = 0
    other_changes: tuple[Change, ...] = field(default=())

    @property
    def right(self) -> bool:
        return all(f.right for f in self.formulas)


def _change(page: tuple[str, ...], reading: tuple[str, ...]) -> str:
    if not reading:
        return "left out"
    if not page:
        return "added"
    both = set(page) | set(reading)
    if both <= {"+", "-", r"\pm", r"\mp"}:
        return "sign"
    if all(t.isdigit() or t == "." for t in both):
        return "digit"
    if all(re.fullmatch(r"[A-Za-z]", t) for t in both):
        return "letter"
    if all(t.startswith("\\") and t[1:].lower() in _GREEK for t in both):
        return "Greek letter"
    return "structure"


_GREEK = {
    "alpha",
    "beta",
    "gamma",
    "delta",
    "varepsilon",
    "zeta",
    "eta",
    "theta",
    "vartheta",
    "iota",
    "kappa",
    "lambda",
    "mu",
    "nu",
    "xi",
    "pi",
    "varpi",
    "rho",
    "varrho",
    "sigma",
    "varsigma",
    "tau",
    "upsilon",
    "varphi",
    "chi",
    "psi",
    "omega",
}


def compare(page_text: str, reading_text: str) -> Comparison:
    """How a reading, as the app stores it, compares with the page's truth,
    stored the same way."""
    page, reading = stream(page_text), stream(reading_text)
    matcher = difflib.SequenceMatcher(None, page.items, reading.items, autojunk=False)
    matched = [False] * len(page.items)
    edits: list[tuple[int, int, int, int]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            matched[i1:i2] = [True] * (i2 - i1)
        else:
            edits.append((i1, i2, j1, j2))

    in_formula = [False] * (len(page.items) + 1)
    for f in page.formulas:
        in_formula[f.start : f.end] = [True] * (f.end - f.start)

    results = []
    claimed: set[int] = set()
    for f in page.formulas:
        right = all(matched[f.start : f.end])
        changes = []
        for n, (i1, i2, j1, j2) in enumerate(edits):
            # an edit touches the formula when it changes its tokens, or adds
            # tokens strictly inside it
            inside = (i1 < f.end and i2 > f.start) or (
                i1 == i2 and f.start < i1 < f.end
            )
            if inside:
                changes.append(Change(page.items[i1:i2], reading.items[j1:j2]))
                claimed.add(n)
                if i1 == i2:
                    right = False
        results.append(FormulaResult(f.latex, right, tuple(changes)))

    maths_tokens = sum(f.end - f.start for f in page.formulas)
    maths_errors = prose_errors = 0
    others = []
    for n, (i1, i2, j1, j2) in enumerate(edits):
        changed = range(i1, i2)
        maths_errors += sum(in_formula[k] for k in changed)
        prose_errors += sum(not in_formula[k] for k in changed)
        if i2 - i1 < j2 - j1:  # tokens added: to the maths when inside a formula
            extra = (j2 - j1) - (i2 - i1)
            if n in claimed:
                maths_errors += extra
            else:
                prose_errors += extra
        if n not in claimed:
            others.append(Change(page.items[i1:i2], reading.items[j1:j2]))
    prose_words = len(page.items) - maths_tokens
    return Comparison(
        tuple(results),
        maths_tokens,
        maths_errors,
        prose_words,
        prose_errors,
        reading.styling - page.styling,
        tuple(others),
    )
