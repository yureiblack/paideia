"""A page's transcription by the vision model: turning it into page text, and
checking it against the PDF's own text layer.

Purpose
-------
The model reads a page's image and writes it out as Markdown with its maths
in LaTeX (decision record 26). This module is pure: it takes that Markdown
and the page's text layer (app/parsing.page_layer) and returns either the
page's new text, in the form pages are stored in, or the reason it cannot
be used. Nothing here calls the model or opens the PDF.

The model makes real mistakes: on a linear algebra textbook it replaced a
worked example with "The answer is", dropped a plus sign from a matrix row,
wrote a wrong matrix, left out zeros and stars, changed a digit and began a
page with a sentence of its own. Its LaTeX cannot be compared with the text
layer as text: a matrix in the layer is a list of numbers, a fraction two
lines, "≠" an equals sign under a separate stroke. What survives every
layout is which characters are there. So both are reduced to their digits,
letters and operators, counted, and compared:

- Digits and operators must match exactly. A changed sign or a lost entry
  changes the maths.
- Letters may differ by 1%, at least 3: the model drops a word now and then,
  or corrects a typo of the book's, and that changes no maths.
- Figure labels may be left out, and the running header and footer are
  left out of both.

Counting cannot see order: a matrix whose columns the model put back in
order has the same characters. That is a known limit of the check.
"""

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

from app import maths
from app.parsing import PARAGRAPH_BREAK, PageLayer, ParsedBlock

LETTER_SLACK = 0.01
LETTER_SLACK_MIN = 3

# --- from Markdown to page text --------------------------------------------------


class Unusable(Exception):
    """The transcription cannot become page text. The message says why."""


@dataclass(frozen=True)
class PageText:
    """A page's text in the stored form, with its paragraphs: text[start:end]
    of each block is a paragraph or heading."""

    text: str
    blocks: tuple[ParsedBlock, ...]


# "Here is the transcription of the page in Markdown": a sentence of the
# model's own, sometimes written before the page despite the prompt.
_CHATTER = re.compile(
    r"^\s*(here is|here's|the following is|below is)\b.*(transcri|markdown|latex)",
    re.IGNORECASE,
)
_RULE = re.compile(r"^\s*(-{3,}|\*{3,}|_{3,})\s*$")
_HEADING = re.compile(r"^#{1,6}\s+")
_QUOTE = re.compile(r"^\s*>\s?", re.MULTILINE)
_BULLET = re.compile(r"^\s*[-*+]\s+", re.MULTILINE)
_LIST_ITEM = re.compile(r"^\s*(\d+[.)]|[-*+•])\s")
# Emphasis markers around prose: **bold**, __bold__, *italic*, _italic_.
_EMPHASIS = re.compile(
    r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1|(?<![\w*])([*_])(?=\S)(.+?)(?<=\S)\3(?![\w*])"
)
_ESCAPED = re.compile(r"\\([*_#`>\[\]()!.+\-|{}])")
_COMMAND = re.compile(r"\\[A-Za-z]+")


def _signature(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKC", text).lower())


def _without_margins(
    lines: list[str], margins: tuple[str, ...], body: str
) -> list[str]:
    """The lines without the running header and footer: as many copies of a
    margin line as the transcription has beyond those the page's body has
    too, since a section heading can read like the running header."""
    wanted = {_signature(m) for m in margins} - {""}
    by_block = Counter(_signature(block) for block in body.split("\n\n"))
    by_line = Counter(_signature(line) for line in body.split("\n"))
    in_body = by_block | by_line  # a heading may be one line, or one block
    have = Counter(_signature(line) for line in lines)
    surplus = {s: have[s] - in_body[s] for s in wanted if have[s] > in_body[s]}
    kept = []
    for line in lines:
        s = _signature(line)
        if surplus.get(s, 0) > 0:
            surplus[s] -= 1
            continue
        kept.append(line)
    return kept


def _paragraphs(lines: list[str]) -> list[str]:
    """Blank-line separated paragraphs, a displayed formula never split, and
    each list item a paragraph of its own, as the text layer has them."""
    paragraphs: list[str] = []
    current: list[str] = []

    def close():
        if current:
            paragraphs.append("\n".join(current))
            current.clear()

    dollars, brackets = False, 0  # inside $$ ... $$, and \\[ ... \\] depth
    for line in lines:
        inside = dollars or brackets > 0
        if not line.strip() and not inside:
            close()
            continue
        if not inside and current and _LIST_ITEM.match(line):
            close()
        current.append(line)
        dollars ^= line.count("$$") % 2 == 1
        brackets = max(0, brackets + line.count("\\[") - line.count("\\]"))
    close()
    return paragraphs


def _prose(text: str) -> str:
    """Markdown's marks taken out of prose, the formulas left alone."""
    prose, restore = maths.prose(text)
    prose = _QUOTE.sub("", prose)
    prose = _BULLET.sub("• ", prose)
    previous = None
    while previous != prose:
        previous = prose
        prose = _EMPHASIS.sub(lambda m: m.group(2) or m.group(4), prose)
    prose = _ESCAPED.sub(r"\1", prose)
    if _COMMAND.search(prose):
        raise Unusable("It has LaTeX outside a formula.")
    return restore(prose)


def without_chatter(markdown: str) -> str:
    """The model's answer without a first sentence of its own ("Here is the
    transcription of the page"). A page read in halves is two answers, and
    either may begin with one."""
    lines = markdown.replace("\r\n", "\n").split("\n")
    first = next((i for i, line in enumerate(lines) if line.strip()), None)
    if first is not None and _CHATTER.match(lines[first]):
        del lines[first]
    return "\n".join(lines)


def page_text(markdown: str, layer: PageLayer) -> PageText:
    """The transcription as page text, or Unusable."""
    lines = without_chatter(markdown).split("\n")
    lines = [line for line in lines if not _RULE.match(line)]
    lines = _without_margins(lines, layer.margins, layer.required)

    text, blocks = "", []
    for paragraph in _paragraphs(lines):
        heading = bool(_HEADING.match(paragraph))
        paragraph = _HEADING.sub("", paragraph)
        paragraph = _prose(maths.from_model(paragraph))
        paragraph = re.sub(r"\s*\n\s*", " ", paragraph).strip()
        if not paragraph:
            continue
        reason = maths.problem(paragraph)
        if reason:
            raise Unusable(f"A formula would not render: {reason}.")
        if text:
            text += PARAGRAPH_BREAK
        blocks.append(ParsedBlock(len(text), len(text) + len(paragraph), heading))
        text += paragraph
    if not text:
        raise Unusable("It is empty.")
    return PageText(text, tuple(blocks))


# --- the characters ---------------------------------------------------------------


def _counts(text: str) -> tuple[Counter, Counter, Counter]:
    shown = maths.shown(text)
    digits = Counter(c for c in shown if c.isdigit())
    letters = Counter(c for c in shown if c.isalpha())
    operators = Counter(c for c in shown if not c.isalnum())
    return digits, letters, operators


# --- the check -------------------------------------------------------------------


@dataclass(frozen=True)
class Check:
    """How a transcription compares with the page's text layer: for digits,
    letters and operators, what the layer has that it lacks, and what it
    has that the layer does not."""

    missing: dict[str, Counter]
    extra: dict[str, Counter]
    letters_in_layer: int

    @property
    def reason(self) -> str | None:
        """Why the transcription disagrees with the text layer, or None."""
        for kind in ("digits", "operators"):
            missing, extra = self.missing[kind], self.extra[kind]
            if missing or extra:
                return f"Its {kind} differ from the PDF's text: {_describe(missing, extra)}."
        letters = sum(self.missing["letters"].values()) + sum(
            self.extra["letters"].values()
        )
        allowed = max(LETTER_SLACK_MIN, int(self.letters_in_layer * LETTER_SLACK))
        if letters > allowed:
            return (
                f"Its words differ from the PDF's text: {letters} letters, "
                f"{_describe(self.missing['letters'], self.extra['letters'])}."
            )
        return None


def _describe(missing: Counter, extra: Counter) -> str:
    def few(counter: Counter) -> str:
        return " ".join(
            f"{c}×{n}" if n > 1 else c for c, n in counter.most_common(5)
        ) + (" …" if len(counter) > 5 else "")

    parts = []
    if missing:
        parts.append(f"{sum(missing.values())} missing ({few(missing)})")
    if extra:
        parts.append(f"{sum(extra.values())} added ({few(extra)})")
    return ", ".join(parts)


def check(page: PageText, layer: PageLayer) -> Check:
    """Compare a transcription, as page text, with the page's text layer."""
    required = _counts(layer.required)
    optional = _counts(layer.optional)
    found = _counts(page.text)
    names = ("digits", "letters", "operators")
    return Check(
        missing={n: r - f for n, r, f in zip(names, required, found, strict=True)},
        extra={
            n: f - (r + o)
            for n, r, o, f in zip(names, required, optional, found, strict=True)
        },
        letters_in_layer=sum(required[1].values()),
    )
