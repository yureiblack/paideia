"""A figure read by the vision model: its answer in parts, checked against
the figure's own text, and made into the figure's passage (decision record
29).

Purpose
-------
A figure's meaning is in its picture: the PDF's text layer keeps a plot's
tick labels and a table's cells, out of order, and nothing of what is drawn.
The local vision model can look at the figure and say what it shows. On a
data mining textbook it copied labels and table cells almost without fault,
and got a detail of its description wrong in about half the figures: a point
placed at x = 4 instead of 3, a 3 by 7 grid called 3 by 9, the gaps of a
plot read as points.

So the answer is asked for in four parts (KIND, TEXT, TABLE, DESCRIPTION)
and they are treated differently:

- What it says is written in the figure, its text and tables, is checked
  against the figure's own text: the PDF's text inside the figure, its
  caption, and Tesseract's reading of its picture. Words may differ a
  little, as OCR misreads and the model corrects a typo now and then.
- Every number it gives, in any part, must be one of the figure's own: a
  number the figure does not show is made up.
- The description cannot be checked further. It is kept, marked as the
  model's, never as the book's: it is shown beside the picture, found by
  search, and nothing is written from it (app/services/figures.py).

This module is pure: it neither calls the model nor opens the PDF.
"""

import re
import unicodedata
from dataclasses import dataclass

# The parts, by the names the prompt gives them, in capitals on a line of
# their own. Set as a heading ("## Text"), in bold, or followed by a colon and
# the part's first line ("Kind: plot"), a name may be in any case; alone on a
# line it must be in capitals, since "table" there is the figure's kind.
_PART = re.compile(
    r"^\s*(?P<marks>#+\s*|\*\*)?\s*(?P<name>kind|text|tables?|description)\s*(?:\*\*)?\s*"
    r"(?:(?P<colon>:)\s*(?:\*\*)?\s*(?P<rest>.*?)\s*(?:\*\*)?\s*|)$",
    re.IGNORECASE,
)
_FENCE = re.compile(r"^\s*```")
_ITEM = re.compile(r"^\s*(?:[-*+•]|\d+[.)])\s+")
_ROW = re.compile(r"^\s*\|.*\|\s*$")
_RULE = re.compile(r"^\s*(-{3,}|\*{3,}|_{3,})\s*$")
_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")
_EMPHASIS = re.compile(r"(\*\*|__|\*|_)(?=\S)(.+?)(?<=\S)\1")
_NONE = {"none", "n/a", "no text", "no table", "-", ""}

# A number as written: "12", "0.25", "−3", "1,000" counts as 1 and 000. Not
# the digits of a label such as p1 or x2, which are part of a word.
_NUMBER = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?")
_WORD = re.compile(r"[^\W\d_]{3,}")

# Words of the text and tables not found in the figure's own text: this many
# are allowed, or this share of them, whichever is more.
WORDS_MISSING = 2
WORDS_MISSING_SHARE = 0.05
SQUASHED_MIN = 5
KIND_CHARS = 40


class Unusable(Exception):
    """The answer is not in the parts asked for. The message says why."""


@dataclass(frozen=True)
class Table:
    title: str | None
    rows: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class Reading:
    kind: str
    text: tuple[str, ...]  # the labels and numbers written in the figure
    tables: tuple[Table, ...]
    description: str


def _plain(line: str) -> str:
    line = _ITEM.sub("", line).strip()
    previous = None
    while previous != line:
        previous = line
        line = _EMPHASIS.sub(lambda m: m.group(2), line)
    return line.strip().strip('"“”').strip()


def _parts(answer: str) -> dict[str, list[str]]:
    parts: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in answer.replace("\r\n", "\n").split("\n"):
        if _FENCE.match(line):
            continue
        found = _PART.match(line)
        if found and (found["marks"] or found["colon"] or found["name"].isupper()):
            name = found["name"].lower()
            name = "table" if name.startswith("table") else name
            current = parts.setdefault(name, [])
            if found["rest"]:
                current.append(found["rest"])
            continue
        if current is not None:
            current.append(line)
    return parts


def _cells(line: str) -> tuple[str, ...]:
    return tuple(_plain(c) for c in line.strip().strip("|").split("|"))


def _tables(lines: list[str], titled: bool) -> tuple[tuple[Table, ...], list[str]]:
    """The Markdown tables among the lines, and the lines that are not in a
    table. A table's header is its first row when a separator row follows
    it; the model also sets the header cells as lines of their own just
    before the rows, and they are its header when there are as many as the
    first row has cells. With titled, the line above a table is its title."""
    tables: list[Table] = []
    rest: list[str] = []
    rows: list[tuple[str, ...]] = []
    header_row = False

    def close() -> None:
        nonlocal rows, header_row
        if rows:
            width = len(rows[0])
            header: list[tuple[str, ...]] = []
            if not header_row and len(rest) >= width and width > 1:
                header = [tuple(rest[-width:])]
                del rest[-width:]
            elif (
                not header_row
                and width > 2
                and len(rest) >= width - 1
                and any(c.isalpha() for c in rows[0][0])
            ):
                # Rows named in their first cell under a header with an empty
                # corner: "Document 1 | 3 | 0" under "team", "coach".
                header = [("", *rest[-(width - 1) :])]
                del rest[-(width - 1) :]
            title = rest.pop() if titled and rest else None
            tables.append(Table(title, tuple(header + rows)))
        rows, header_row = [], False

    for line in lines:
        if not line.strip() or _RULE.match(line):
            continue
        if _ROW.match(line):
            if _SEPARATOR.match(line):
                header_row = header_row or len(rows) == 1
            else:
                rows.append(_cells(line))
            continue
        close()
        plain = _plain(line).rstrip(":") if titled else _plain(line)
        if plain.lower() not in _NONE:
            rest.append(plain)
    close()
    return tuple(tables), rest


def parse(answer: str, caption: str | None = None) -> Reading:
    """The model's answer in its parts, or Unusable."""
    parts = _parts(answer)
    if "description" not in parts or "kind" not in parts:
        raise Unusable("It is not in the four parts asked for.")
    kind = next((_plain(line) for line in parts["kind"] if line.strip()), "")
    kind = kind.rstrip(".").lower()[:KIND_CHARS] or "figure"
    # The model writes tables under TABLE as asked, and as often under TEXT.
    in_text, text = _tables(parts.get("text", []), titled=False)
    in_table, loose = _tables(parts.get("table", []), titled=True)
    own_caption = _signature(caption or "")
    text = [
        line
        for line in text + loose
        if line.lower() not in _NONE
        and not (own_caption and _signature(line) == own_caption)
    ]
    description = " ".join(
        _plain(line)
        for line in parts["description"]
        if line.strip() and not _RULE.match(line)
    ).strip()
    if not description:
        raise Unusable("It has no description.")
    return Reading(kind, tuple(text), in_text + in_table, description)


# --- the check -------------------------------------------------------------------


def _normal(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    return text.replace("−", "-").replace("–", "-").replace("—", "-")


def _signature(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", _normal(text).lower())


def numbers(text: str) -> list[str]:
    """The numbers written in a text, as values: 0.50 and .5 are 0.5."""
    found = []
    for match in _NUMBER.findall(_normal(text)):
        value = float(match)
        found.append(f"{abs(value):g}")
    return found


def words(text: str) -> list[str]:
    return [w.lower() for w in _WORD.findall(_normal(text))]


def _written(reading: Reading) -> str:
    """What the reading says is written in the figure."""
    cells = [cell for table in reading.tables for row in table.rows for cell in row]
    titles = [table.title for table in reading.tables if table.title]
    return "\n".join([*reading.text, *titles, *cells])


def check(reading: Reading, own_text: str) -> str | None:
    """Why the reading disagrees with the figure's own text, or None.

    own_text is everything the figure is known to show: the PDF's text
    inside it, its caption, and Tesseract's reading of its picture."""
    own_numbers = set(numbers(own_text))
    said = numbers(_written(reading)) + numbers(reading.description)
    made_up = sorted(
        {n for n in said if n not in own_numbers}, key=lambda n: (len(n), n)
    )
    if made_up:
        return f"It gives numbers the figure does not show: {', '.join(made_up[:8])}."
    own_words = set(words(own_text))
    if not own_words:
        return None  # a picture with no text to compare its text with
    # A word may be set apart in the PDF's text and joined in the picture,
    # "new value" and new_value: a long word found in the figure's text with
    # its spaces taken out is found.
    squashed = "".join(words(own_text))
    written = words(_written(reading))
    missing = [
        w
        for w in written
        if w not in own_words and not (len(w) >= SQUASHED_MIN and w in squashed)
    ]
    allowed = max(WORDS_MISSING, int(len(written) * WORDS_MISSING_SHARE))
    if len(missing) > allowed:
        shown = ", ".join(dict.fromkeys(missing))
        return (
            f"Its text differs from the figure's: {len(missing)} of {len(written)} "
            f"words are not in it ({shown[:120]})."
        )
    return None


def repeats(reading: Reading, text: str) -> bool:
    """Whether the reading says all that a piece of the figure's own text
    says, word for word and number for number: then the piece may give way
    to the reading in the page, and nothing of the PDF's text is lost."""
    written = _written(reading)
    have_words, have_numbers = set(words(written)), set(numbers(written))
    squashed = "".join(words(written))
    return all(w in have_words or w in squashed for w in words(text)) and all(
        n in have_numbers for n in numbers(text)
    )


# --- the figure's passage ----------------------------------------------------------


def passage(reading: Reading) -> str:
    """The figure as one paragraph of text, for search and for the page: what
    is written in it, then the model's description, marked as the model's."""
    pieces = []
    if reading.text:
        labels = "; ".join(t.rstrip(".") for t in reading.text)
        pieces.append(f"{reading.kind.capitalize()}: {labels}.")
    for table in reading.tables:
        rows = " / ".join(" | ".join(row) for row in table.rows)
        pieces.append(f"{table.title}: {rows}." if table.title else f"Table: {rows}.")
    pieces.append(f"Described by the model: {reading.description}")
    return " ".join(" ".join(pieces).split())
