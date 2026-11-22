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
import unicodedata
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


# --- what maths shows (decision record 26) ----------------------------------------
#
# A formula's LaTeX and a PDF's text layer write the same maths differently: a
# matrix in the layer is a list of numbers, a fraction two lines, "≠" an
# equals sign under a separate stroke. What both keep is which characters are
# shown, in order: digits, letters and operators. shown() reduces any text to
# them; a transcription is checked with it (app/transcription.py), and the
# maths the model writes is looked up in its passages with it (unquoted).


# The character each command draws, where the text layer has that character:
# Greek letters, operators, relations, arrows and named functions. Commands
# not listed draw no character the layer has (\frac, \hat, spacing...).
_DRAWS = {
    **{
        name: chr(code)
        for name, code in {
            "alpha": 0x3B1,
            "beta": 0x3B2,
            "gamma": 0x3B3,
            "delta": 0x3B4,
            "epsilon": 0x3B5,
            "varepsilon": 0x3B5,
            "zeta": 0x3B6,
            "eta": 0x3B7,
            "theta": 0x3B8,
            "vartheta": 0x3B8,
            "iota": 0x3B9,
            "kappa": 0x3BA,
            "lambda": 0x3BB,
            "mu": 0x3BC,
            "nu": 0x3BD,
            "xi": 0x3BE,
            "pi": 0x3C0,
            "varpi": 0x3C0,
            "rho": 0x3C1,
            "varrho": 0x3C1,
            "sigma": 0x3C3,
            "varsigma": 0x3C2,
            "tau": 0x3C4,
            "upsilon": 0x3C5,
            "phi": 0x3C6,
            "varphi": 0x3C6,
            "chi": 0x3C7,
            "psi": 0x3C8,
            "omega": 0x3C9,
            "Gamma": 0x393,
            "Delta": 0x394,
            "Theta": 0x398,
            "Lambda": 0x39B,
            "Xi": 0x39E,
            "Pi": 0x3A0,
            "Sigma": 0x3A3,
            "Upsilon": 0x3A5,
            "Phi": 0x3A6,
            "Psi": 0x3A8,
            "Omega": 0x3A9,
        }.items()
    },
    "cdot": "·",
    "cdots": "···",
    "times": "×",
    "pm": "±",
    "mp": "∓",
    "div": "÷",
    "le": "≤",
    "leq": "≤",
    "ge": "≥",
    "geq": "≥",
    "ne": "≠",
    "neq": "≠",
    "to": "→",
    "rightarrow": "→",
    "longrightarrow": "→",
    "xrightarrow": "→",
    "mapsto": "↦",
    "leftarrow": "←",
    "longleftarrow": "←",
    "xleftarrow": "←",
    "Rightarrow": "⇒",
    "xRightarrow": "⇒",
    "Longrightarrow": "⇒",
    "implies": "⇒",
    "Leftrightarrow": "⇔",
    "Longleftrightarrow": "⇔",
    "iff": "⇔",
    "in": "∈",
    "notin": "∉",
    "subset": "⊂",
    "subseteq": "⊆",
    "supset": "⊃",
    "supseteq": "⊇",
    "cup": "∪",
    "cap": "∩",
    "infty": "∞",
    "perp": "⊥",
    "approx": "≈",
    "equiv": "≡",
    "cong": "≅",
    "sim": "∼",
    "ast": "*",
    "star": "*",
    "lt": "<",
    "gt": ">",
    **{
        name: name
        for name in (
            "det",
            "dim",
            "rank",
            "ker",
            "sin",
            "cos",
            "tan",
            "cot",
            "sec",
            "csc",
            "log",
            "ln",
            "exp",
            "min",
            "max",
            "lim",
            "sup",
            "inf",
            "gcd",
            "deg",
            "arg",
            "Pr",
        )
    },
}
# Commands whose braced argument names a layout, not text: \begin{array}{cc|c}.
_LAYOUT = re.compile(r"\\(begin|end)\{[a-zA-Z*]+\}(\{[^{}]*\})?")
_SIZE = re.compile(r"\\(left|right|middle|[Bb]igg?[lrm]?)\b\.?")
_RULE_CELL = re.compile(r"^\s*(-+|—+|\||\\vert|\\mid|\\rule\{[^}]*\}\{[^}]*\})?\s*$")
_MATRIX = re.compile(
    r"(\\begin\{[a-zA-Z]*matrix\*?\})(.*?)(\\end\{[a-zA-Z]*matrix\*?\})", re.DOTALL
)


def _without_rules(latex: str) -> str:
    """A matrix's cells that only draw a rule, a dash or a bar standing for
    a row or column vector, are decoration: the text layer has no such
    character, or has it as a bar the check does not count."""

    def rows(m: re.Match) -> str:
        kept = []
        for row in re.split(r"\\\\", m.group(2)):
            cells = [cell for cell in row.split("&") if not _RULE_CELL.match(cell)]
            kept.append(" & ".join(cells))
        return m.group(1) + r" \\ ".join(kept) + m.group(3)

    return _MATRIX.sub(rows, latex)


def _drawn(latex: str) -> str:
    """The characters a formula draws that a text layer would have."""
    # Row breaks first: a row break followed by v is a break and a letter,
    # not a backslash and a command named v.
    text = _LAYOUT.sub(" ", _without_rules(latex)).replace("\\\\", " ")
    text = _SIZE.sub(" ", text)
    text = re.sub(r"\\([A-Za-z]+)", lambda m: f" {_DRAWS.get(m.group(1), '')} ", text)
    text = re.sub(r"\\.", " ", text)  # \{ \} \, and the like
    # Every minus in a formula is a minus, never a hyphen.
    return re.sub(r"[{}^_&]", " ", text).replace("-", "−")


def _plain(text: str) -> str:
    """Page text with each formula replaced by the characters it draws."""
    found, _ = spans(text)
    return "".join(
        text[s.body_start : s.body_end]
        if s.kind == "prose"
        else " " + _drawn(text[s.body_start : s.body_end]) + " "
        for s in found
    )


_OPERATORS = set("+−=<>≤≥≠·×÷±∓→←↦⇒⇔∈∉⊂⊆⊃⊇∪∩∞⊥≈≡≅∼*")
# A text layer's way of writing characters it has no single code for.
_LAYER_FORMS = [
    (re.compile("\u0338\\s*="), "≠"),  # an equals sign struck through
    (re.compile("\u0338\\s*∈"), "∉"),
    (re.compile("(−\\s*)+→"), "→"),  # a long arrow: minus signs and an arrow
    (re.compile("(=\\s*)+⇒"), "⇒"),  # a long implication
    (re.compile("⇐\\s*⇒"), "⇔"),
    (re.compile("[⋅∙]"), "·"),
    (re.compile("[∗⋆]"), "*"),
]
# A hyphen between two letters, or ending a line after one, joins words; it
# is not a minus. Any other hyphen-minus is.
_WORD_HYPHEN = re.compile(r"(?<=[^\W\d_])-(?=[^\W\d_]|\s*$)", re.MULTILINE)


def shown(text: str) -> str:
    """The digits, letters and operators the text shows, in order, each
    formula as the characters it draws: "\\(\\lambda^2 - 6\\lambda\\)" and the
    text layer's "λ2 −6λ" both show "λ2−6λ"."""
    text = unicodedata.normalize("NFKC", _plain(text))
    for pattern, replacement in _LAYER_FORMS:
        text = pattern.sub(replacement, text)
    text = _WORD_HYPHEN.sub(" ", text).replace("-", "−")
    return "".join(c for c in text if c.isalnum() or c in _OPERATORS)


def _states(found: str) -> bool:
    """Whether maths showing these characters states something: a digit or
    an operator. Letters and symbols alone only name something."""
    return any(c.isdigit() or c in _OPERATORS for c in found)


def unquoted(text: str, sources: str) -> list[str]:
    """The formulas in text whose maths its sources do not show (decision
    record 26): the model may quote maths, never work it out. A formula
    with a digit or an operator must show exactly what some stretch of the
    sources shows, spacing and layout aside; one of symbols alone, only
    symbols the sources show."""
    seen = shown(sources)
    symbols = set(seen)
    missing = []
    for latex in formulas(text):
        found = shown(f"\\({latex}\\)")
        if _states(found):
            if found not in seen:
                missing.append(latex)
        elif not set(found) <= symbols:
            missing.append(latex)
    return missing
