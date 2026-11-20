"""Maths in text: LaTeX between \\( \\) and \\[ \\] (decision record 24).

Purpose
-------
Any text Paideia shows may hold maths: passages, summaries, concept
definitions, practice items. Maths is stored as LaTeX, inline between \\( and
\\), displayed on its own line between \\[ and \\]. Never between dollar signs:
the page renders only these two pairs, so a price in an economics text never
turns into maths.

This module is the backend's half of that convention; the page's half is
web/src/lib/maths.ts, which splits text the same way.

- spans() splits a text into prose and formulas.
- for_model() shows the model text in the notation it is asked to write:
  formulas between dollar signs.
- from_model() turns what the language model writes into the stored form.
  In its JSON answers the model writes LaTeX between dollar signs, whatever
  it is asked (prototyped in record 24), and JSON's escaping damages it in
  two ways, both repaired here, inside formulas only:
  - JSON reads \\b, \\f, \\n, \\r and \\t as control characters, so "\\begin"
    arrives as a backspace and "egin". The backslash is put back when that
    makes a command KaTeX knows; a backspace or form feed always means one.
  - A matrix's row break "\\\\" arrives as a single backslash. Inside an
    environment made of rows, a single backslash before a space is put back
    to two.
- problem() says why a text's formulas would not render, or would render
  something no formula should: unclosed or nested delimiters, unbalanced
  braces or \\left and \\right, unknown or mismatched environments, commands
  KaTeX does not know, and commands refused here (see REFUSED).
- prose() hides each formula behind a placeholder, so rules about prose
  (practice's plain-text rules, length limits) never look inside maths.

KaTeX's commands and environments come from katex.json, generated from the
KaTeX the page renders with (web/scripts/katex-commands.ts); a test in web/
fails when the two disagree.
"""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

_KATEX = json.loads((Path(__file__).parent / "katex.json").read_text("utf-8"))
KATEX_VERSION: str = _KATEX["katex"]
COMMANDS: frozenset[str] = frozenset(_KATEX["commands"])
SYMBOLS: frozenset[str] = frozenset(_KATEX["symbols"])
ENVIRONMENTS: frozenset[str] = frozenset(_KATEX["environments"])

# Commands KaTeX knows that no formula here may use.
REFUSED = {
    # They define or redefine commands, so one formula could change what
    # later ones mean. A formula never needs them.
    **dict.fromkeys(
        (
            "def",
            "edef",
            "gdef",
            "xdef",
            "let",
            "futurelet",
            "global",
            "long",
            "newcommand",
            "renewcommand",
            "providecommand",
            "expandafter",
            "noexpand",
        ),
        "defines commands",
    ),
    # They write to the browser's console.
    **dict.fromkeys(("show", "message", "errmessage"), "writes to the console"),
    # They need KaTeX's trust option, which the page leaves off, so they
    # would show as errors.
    **dict.fromkeys(
        (
            "href",
            "url",
            "includegraphics",
            "htmlClass",
            "htmlId",
            "htmlStyle",
            "htmlData",
        ),
        "links, images or HTML",
    ),
    # Its text runs to a delimiter of its own choosing, which can be the
    # closing \) of the formula.
    "verb": "verbatim text",
}

# Environments whose rows are separated by \\.
ROW_ENVIRONMENTS = frozenset(
    name
    for name in ENVIRONMENTS
    if re.match(
        r"(.*matrix|array|darray|subarray|.*cases|aligned|alignedat|align|alignat"
        r"|gathered|gather|split|CD|equation)\*?$",
        name,
    )
)

# How long the LaTeX of one field's formulas may be, altogether, wherever a
# field has a length limit. The limit itself then applies to the prose, each
# formula counting as one character (see sizes()): LaTeX is long for what it
# shows, and a 3 by 3 matrix of fractions is about 90 characters.
FORMULA_CHARS = 300

_OPEN = {"(": ")", "[": "]"}
_DISPLAY = {"(": False, "[": True}


@dataclass(frozen=True)
class Span:
    """text[start:end] is the span, delimiters included for a formula;
    text[body_start:body_end] is a formula's LaTeX, or the prose itself."""

    start: int
    end: int
    body_start: int
    body_end: int
    kind: str  # "prose", "inline" or "display"


def spans(text: str) -> tuple[list[Span], str | None]:
    """The text split into prose and formulas, and the first problem with
    its delimiters, if any. An unclosed formula is returned as prose, so a
    caller that shows text can still show it.

    In prose, \\( and \\[ open a formula. Inside one, a backslash always
    takes the next character with it, so "\\\\" (a row break) is never read
    as the start of a delimiter; \\) or \\] closes the formula when it
    matches the opening, and any other delimiter is a problem.
    """
    result: list[Span] = []
    problem = None
    i, prose_start, n = 0, 0, len(text)
    while i < n:
        if text[i] != "\\" or i + 1 >= n:
            i += 1
            continue
        c = text[i + 1]
        if c in ")]":
            problem = problem or "a formula is closed but never opened"
            i += 2
            continue
        if c not in _OPEN:
            i += 2
            continue
        close = _OPEN[c]
        j = i + 2
        end = None
        while j < n:
            if text[j] == "\\" and j + 1 < n:
                d = text[j + 1]
                if d == close:
                    end = j
                    break
                if d in "()[]":
                    problem = problem or "a formula opens or closes inside another"
                j += 2
                continue
            j += 1
        if end is None:
            problem = problem or "a formula is not closed"
            i += 2
            continue
        if prose_start < i:
            result.append(Span(prose_start, i, prose_start, i, "prose"))
        kind = "display" if _DISPLAY[c] else "inline"
        result.append(Span(i, end + 2, i + 2, end, kind))
        i = prose_start = end + 2
    if prose_start < n:
        result.append(Span(prose_start, n, prose_start, n, "prose"))
    return result, problem


def formulas(text: str) -> list[str]:
    """The LaTeX of every formula in the text, in order."""
    return [
        text[s.body_start : s.body_end] for s in spans(text)[0] if s.kind != "prose"
    ]


# --- what the model reads and writes ----------------------------------------------


def for_model(text: str) -> str:
    """Text as the model is shown it: formulas between dollar signs, the
    notation it is asked to write, so that it copies what it reads. Shown
    \\( \\) while asked for dollar signs, it sometimes wrote Unicode maths
    instead of LaTeX (record 24)."""
    found, _ = spans(text)
    pieces = []
    for span in found:
        body = text[span.body_start : span.body_end]
        if span.kind == "prose":
            pieces.append(body)
        elif span.kind == "inline":
            pieces.append(f"${body}$")
        else:
            pieces.append(f"$${body}$$")
    return "".join(pieces)


# What JSON makes of a backslash followed by these letters.
_JSON_ESCAPES = {"\b": "b", "\f": "f", "\n": "n", "\r": "r", "\t": "t"}
_LETTERS = re.compile(r"[A-Za-z]*")
_LONE_BACKSLASH = re.compile(r"(?<!\\)\\(?=\s)")
_ENVIRONMENT = re.compile(r"\\begin\{([A-Za-z]+\*?)\}(.*?)\\end\{\1\}", re.DOTALL)


def _damaged_command(text: str, i: int) -> str | None:
    """The command JSON turned into the control character at text[i], if it
    did: a backspace or form feed always, a newline, carriage return or tab
    only when putting the backslash back makes a command KaTeX knows."""
    letter = _JSON_ESCAPES.get(text[i])
    if letter is None:
        return None
    found = _LETTERS.match(text, i + 1)
    name = letter + (found.group(0) if found else "")
    return name if text[i] in "\b\f" or name in COMMANDS else None


def _repair(latex: str) -> str:
    """A formula with the damage JSON's escaping does put right."""
    out, i = [], 0
    while i < len(latex):
        name = _damaged_command(latex, i)
        if name is not None:
            out.append("\\" + name)
            i += len(name)
            continue
        out.append(latex[i])
        i += 1
    latex = "".join(out)

    def rows(match: re.Match) -> str:
        whole, name, body = match.group(0), match.group(1), match.group(2)
        if name not in ROW_ENVIRONMENTS:
            return whole
        return whole.replace(body, _LONE_BACKSLASH.sub(r"\\\\", body))

    return _ENVIRONMENT.sub(rows, latex)


def _dollar_closer(text: str, start: int) -> int | None:
    """Where the $ that closes an inline formula opened at start is: the
    next unescaped $ with no space before it and no digit after it, as
    Pandoc reads TeX maths. None if there is none, and the $ was money."""
    j = start + 1
    while j < len(text):
        if text[j] == "\\":
            j += 2
            continue
        if text[j] == "$":
            after = text[j + 1 : j + 2]
            if not text[j - 1].isspace() and not after.isdigit():
                return j
            return None
        j += 1
    return None


def _opens(text: str, i: int) -> bool:
    """Whether text[i], just after a $, lets the $ open a formula: anything
    but a space does, and so does a command JSON turned into a tab or a
    newline, as in "$\\times$"."""
    return not text[i].isspace() or _damaged_command(text, i) is not None


def from_model(text: str) -> str:
    """What the model wrote, in the stored form: formulas between dollar
    signs moved to \\( \\) and \\[ \\], and every formula repaired.

    $$...$$ is displayed maths. $...$ is a formula only when, as Pandoc
    reads TeX maths, the opening $ has no space after it and the closing $
    no space before it and no digit after it: "$5 and $10" stays money.
    Formulas the model already wrote between \\( \\) or \\[ \\] are kept.
    """
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c == "\\" and i + 1 < n and text[i + 1] in _OPEN:
            close = _OPEN[text[i + 1]]
            j = i + 2
            while j < n and not (text[j] == "\\" and text[j + 1 : j + 2] == close):
                j += 2 if text[j] == "\\" else 1
            if j < n:
                out.append(text[i : i + 2] + _repair(text[i + 2 : j]) + text[j : j + 2])
                i = j + 2
                continue
        if c == "\\" and i + 1 < n:
            out.append(text[i : i + 2])
            i += 2
            continue
        if text.startswith("$$", i):
            j = text.find("$$", i + 2)
            if j > i + 2:
                out.append("\\[" + _repair(text[i + 2 : j]).strip() + "\\]")
                i = j + 2
                continue
        elif c == "$" and i + 1 < n and _opens(text, i + 1):
            closer = _dollar_closer(text, i)
            if closer is not None:
                out.append("\\(" + _repair(text[i + 1 : closer]) + "\\)")
                i = closer + 1
                continue
        out.append(c)
        i += 1
    return "".join(out)


def from_model_checked(text: str) -> str:
    """from_model(), for text that cannot be dropped on its own: a formula
    that would not render raises ValueError, which makes the whole answer
    malformed, so the model is asked again (decision record 08)."""
    text = from_model(text)
    reason = problem(text)
    if reason:
        raise ValueError(f"A formula would not render: {reason}.")
    return text


# --- whether a formula renders ------------------------------------------------

_TOKEN = re.compile(r"\\([A-Za-z]+)|\\(.)|([{}$%])", re.DOTALL)
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _formula_problem(latex: str) -> str | None:
    if not latex.strip():
        return "an empty formula"
    depth = 0
    environments: list[str] = []
    lefts = 0
    for token in _TOKEN.finditer(latex):
        command, symbol, plain = token.groups()
        if plain == "{":
            depth += 1
        elif plain == "}":
            depth -= 1
            if depth < 0:
                return "a } with no {"
        elif plain == "$":
            return "a $ inside a formula"
        elif plain == "%":
            return "a % inside a formula, which hides the rest of it"
        elif symbol is not None:
            if symbol not in SYMBOLS:
                return f"an unknown command \\{symbol}"
        elif command is None:
            continue
        elif command in REFUSED:
            return f"\\{command}, which {REFUSED[command]}"
        elif command not in COMMANDS:
            return f"an unknown command \\{command}"
        elif command in ("begin", "end"):
            name = re.match(r"\s*\{([A-Za-z]+\*?)\}", latex[token.end() :])
            if name is None:
                return f"\\{command} without an environment"
            if command == "begin":
                if name.group(1) not in ENVIRONMENTS:
                    return f"an unknown environment {name.group(1)}"
                environments.append(name.group(1))
            elif not environments or environments.pop() != name.group(1):
                return f"\\end{{{name.group(1)}}} does not match its \\begin"
        elif command == "left":
            lefts += 1
        elif command == "right":
            lefts -= 1
            if lefts < 0:
                return "a \\right with no \\left"
    if depth:
        return "a { with no }"
    if environments:
        return f"\\begin{{{environments[-1]}}} with no \\end"
    if lefts:
        return "a \\left with no \\right"
    return None


def problem(text: str) -> str | None:
    """Why the text's maths would not render, or None if it would. Every
    formula must parse; nothing outside a formula may be a control
    character, which is what JSON makes of LaTeX written outside one."""
    if _CONTROL.search(text):
        return "a control character, the remains of LaTeX outside a formula"
    found, delimiter_problem = spans(text)
    if delimiter_problem:
        return delimiter_problem
    for span in found:
        if span.kind == "prose":
            continue
        reason = _formula_problem(text[span.body_start : span.body_end])
        if reason:
            return reason
    return None


# --- prose rules that must not look inside maths --------------------------------

# Private-use characters: no text Paideia stores contains them.
_HOLE = "\ue000{}\ue001"
_HOLE_PATTERN = re.compile("\ue000(\\d+)\ue001")


def prose(text: str) -> tuple[str, Callable[[str], str]]:
    """The text with each formula replaced by a placeholder, and a function
    putting the formulas back into prose derived from it. Placeholders
    contain no spaces, letters or punctuation that prose rules act on."""
    found, _ = spans(text)
    pieces: list[str] = []
    kept: list[str] = []
    for span in found:
        if span.kind == "prose":
            pieces.append(text[span.start : span.end])
        else:
            pieces.append(_HOLE.format(len(kept)))
            kept.append(text[span.start : span.end])

    def restore(derived: str) -> str:
        return _HOLE_PATTERN.sub(lambda m: kept[int(m.group(1))], derived)

    return "".join(pieces), restore


def sizes(text: str) -> tuple[int, int]:
    """How long the text's prose is, each formula counting as one
    character, and how long its formulas' LaTeX is altogether."""
    found, _ = spans(text)
    prose_chars = formula_chars = 0
    for span in found:
        if span.kind == "prose":
            prose_chars += span.end - span.start
        else:
            prose_chars += 1
            formula_chars += span.body_end - span.body_start
    return prose_chars, formula_chars
