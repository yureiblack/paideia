"""Turning a PDF file into page-numbered text, paragraph by paragraph.

Purpose
-------
Everything that knows how to read a PDF lives here, behind a small interface:
a Parser takes a file path and returns the text of each page, numbered from 1,
or raises ParseError with a message fit to show the user. Nothing else in the
backend imports pymupdf, so another library could replace it by adding one
class to this file.

Each page's text is stored as paragraphs separated by a blank line, and the
parser also reports where each paragraph sits in that text and whether it is a
heading. The chunker builds on that structure.

Rules found by prototyping PyMuPDF 1.28.2 (decision records 03 and 04):
- A PDF is recognised by doc.is_pdf as well as its first bytes, because
  PyMuPDF will happily open a PNG as a one-page "document".
- Password-protected files open but cannot be read; zero-page files open
  without complaint. Both are refused here.
- Damaged files are often repaired on open with every page intact. They are
  accepted and flagged as repaired.
- NUL characters survive extraction and Postgres text refuses them.
- Text is taken in the PDF's own block order; the sort option interleaves the
  two columns of a two-column page.
- Ligatures such as "ﬁ" are expanded to "fi", or "files" would never match a
  search for files.
- PyMuPDF's own dehyphenation flag does nothing, so words broken across lines
  are rejoined here, guided by the document's own vocabulary.
- Running headers, footers and page numbers come out as ordinary blocks. They
  are dropped, or they would land in the middle of paragraphs.

Reading a document's maths (decision record 26) needs three more things from
the PDF, also here: which pages set many characters in maths fonts, a page's
image for the vision model, and the page's text split into what a
transcription must contain and what it may leave out.
"""

import math
import re
import threading
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import pymupdf

from app import ocr
from app.config import settings

# MuPDF prints its complaints about damaged files straight to the console.
# Problems are reported through the document's status instead.
pymupdf.TOOLS.mupdf_display_errors(False)

# PyMuPDF's documentation: it "does not support running on multiple threads -
# doing so may cause incorrect behaviour or even crash Python itself." Parsing
# runs in background tasks, which run on threads, so every PyMuPDF call holds
# this lock. Reading 300 pages takes well under a second, so taking turns
# costs little.
_PYMUPDF_LOCK = threading.Lock()

# dict mode reports every block, line and span with its font size and style.
# Two of its defaults are switched off: ligatures are expanded so search
# matches, and images are skipped because only text is used.
_TEXT_FLAGS = (
    pymupdf.TEXTFLAGS_DICT
    & ~pymupdf.TEXT_PRESERVE_LIGATURES
    & ~pymupdf.TEXT_PRESERVE_IMAGES
)
_BOLD = 16  # the bold bit in a span's flags

PARAGRAPH_BREAK = "\n\n"

# A heading is short, and either clearly larger than body text or bold at
# body size.
HEADING_MAX_CHARS = 150
HEADING_MAX_LINES = 3
HEADING_SIZE_RATIO = 1.15

# Running headers and footers: short blocks in the top or bottom margin that
# repeat, digits treated alike, on at least half the pages of a document of
# at least this many pages.
BOILERPLATE_MIN_PAGES = 3
BOILERPLATE_MAX_CHARS = 100
# The outer 7% of the page at top and bottom: about half an inch on letter or
# A4 paper, where running headers and footers sit. Body text conventionally
# starts an inch from the edge, so it stays outside this band. A band of an
# eighth of the page was tried first and swallowed real first lines.
BOILERPLATE_MARGIN = 0.07


class ParseError(Exception):
    """The file cannot be read as a PDF. The message is shown to the user."""


@dataclass(frozen=True)
class ParsedBlock:
    """One paragraph or heading: page.text[start:end] is its text."""

    start: int
    end: int
    is_heading: bool
    # Where the block lies on the page, in PDF points, when it came from the
    # text layer: a figure read by the model takes the place of the blocks
    # inside it (record 29). Not part of what makes two blocks equal.
    box: tuple[float, float, float, float] | None = field(default=None, compare=False)
    # The figure reading this block is, when it is one (record 29).
    figure: str | None = None


@dataclass(frozen=True)
class ParsedPage:
    number: int  # counted from 1, as a reader would
    text: str
    # Empty only for a page with no text. A Parser that cannot tell
    # paragraphs apart may leave it empty; the chunker then treats the whole
    # page text as one paragraph.
    blocks: tuple[ParsedBlock, ...] = ()
    # Its text was read from a picture of the page by OCR (record 29).
    ocr: bool = False
    # The figures on the page, each with where all its text is (record 31).
    figures: tuple["PlacedFigure", ...] = ()


@dataclass(frozen=True)
class ParsedDocument:
    pages: list[ParsedPage]
    # True when the file was damaged and had to be repaired to be read. Its
    # content may be complete, or the damage may have taken some of it.
    repaired: bool

    @property
    def pages_with_text(self) -> int:
        """Pages with any text at all. Zero usually means a scanned PDF."""
        return sum(1 for page in self.pages if page.text.strip())

    @property
    def pages_ocr(self) -> int:
        """Pages whose text was read from a picture of the page."""
        return sum(1 for page in self.pages if page.ocr)


class Parser(Protocol):
    """Anything that can turn a PDF file into page-numbered text."""

    def parse(self, path: Path) -> ParsedDocument: ...


@dataclass(frozen=True)
class _RawBlock:
    """A text block as PyMuPDF reports it, before any cleaning."""

    lines: tuple[str, ...]
    size: float  # the largest font size in the block
    bold: bool  # every visible span is bold
    in_margin: bool  # sits in the top or bottom margin band
    chars_by_size: tuple[tuple[float, int], ...]
    bbox: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)


class PyMuPDFParser:
    """The Parser used in production, built on PyMuPDF."""

    def parse(self, path: Path) -> ParsedDocument:
        with _PYMUPDF_LOCK:
            try:
                document = pymupdf.open(path, filetype="pdf")
            except pymupdf.FileNotFoundError as exc:
                raise ParseError(
                    "The stored file is missing. Upload it again."
                ) from exc
            except pymupdf.FileDataError as exc:  # also covers an empty file
                raise ParseError("The file is not a readable PDF.") from exc

            with document:
                if not document.is_pdf:
                    raise ParseError("The file is not a PDF.")
                if document.needs_pass:
                    raise ParseError("The PDF is password-protected.")
                if document.page_count == 0:
                    raise ParseError("The PDF has no pages.")
                if document.page_count > settings.max_pages:
                    raise ParseError(
                        f"The PDF has {document.page_count} pages; at most "
                        f"{settings.max_pages} are accepted."
                    )
                raw_pages, read = [], set()
                for page in document.pages():
                    blocks = _raw_blocks(page)
                    chars = sum(len(line.strip()) for b in blocks for line in b.lines)
                    # A scanned page: its text read from its picture (record 29).
                    if ocr.available() and ocr.is_scanned(page, chars):
                        blocks = _raw_blocks(page, ocr.text_page(page, _TEXT_FLAGS))
                        read.add(page.number)
                    raw_pages.append(blocks)
                repaired = document.is_repaired

        # Everything below is plain Python on the extracted data, so it runs
        # outside the lock.
        return ParsedDocument(pages=_build_pages(raw_pages, read), repaired=repaired)


def _raw_blocks(
    page: pymupdf.Page, textpage: pymupdf.TextPage | None = None
) -> list[_RawBlock]:
    height = page.rect.height
    blocks = []
    found = page.get_text("dict", flags=_TEXT_FLAGS, textpage=textpage)
    for block in found["blocks"]:
        if block.get("type") != 0:
            continue
        spans = [span for line in block["lines"] for span in line["spans"]]
        visible = [span for span in spans if span["text"].strip()]
        if not visible:
            continue
        top, bottom = block["bbox"][1], block["bbox"][3]
        sizes: Counter[float] = Counter()
        for span in visible:
            sizes[round(span["size"] * 2) / 2] += len(span["text"].strip())
        blocks.append(
            _RawBlock(
                lines=tuple(
                    "".join(span["text"] for span in line["spans"])
                    for line in block["lines"]
                ),
                size=max(span["size"] for span in visible),
                bold=all(span["flags"] & _BOLD for span in visible),
                in_margin=(
                    bottom <= height * BOILERPLATE_MARGIN
                    or top >= height * (1 - BOILERPLATE_MARGIN)
                ),
                chars_by_size=tuple(sizes.items()),
                bbox=tuple(block["bbox"]),
            )
        )
    return blocks


def _build_pages(
    raw_pages: list[list[_RawBlock]],
    read: set[int] = frozenset(),  # type: ignore[assignment]
) -> list[ParsedPage]:
    """Clean every block and assemble each page's text and block positions."""
    body_size = _body_font_size(raw_pages)
    boilerplate = _boilerplate_signatures(raw_pages)
    vocabulary = {
        word
        for blocks in raw_pages
        for block in blocks
        for line in block.lines
        for word in re.findall(r"[a-z]+", line.lower())
    }

    pages = []
    for index, raw_blocks in enumerate(raw_pages):
        text, blocks = "", []
        for raw in raw_blocks:
            if raw.in_margin and _signature(raw) in boilerplate:
                continue
            paragraph = _join_lines(raw.lines, vocabulary).replace("\x00", "").strip()
            if not paragraph:
                continue
            if text:
                text += PARAGRAPH_BREAK
            blocks.append(
                ParsedBlock(
                    start=len(text),
                    end=len(text) + len(paragraph),
                    is_heading=_is_heading(raw, paragraph, body_size),
                    box=raw.bbox,
                )
            )
            text += paragraph
        pages.append(
            ParsedPage(
                number=index + 1, text=text, blocks=tuple(blocks), ocr=index in read
            )
        )
    return pages


def _body_font_size(raw_pages: list[list[_RawBlock]]) -> float | None:
    """The font size used by the most characters in the document."""
    sizes: Counter[float] = Counter()
    for blocks in raw_pages:
        for block in blocks:
            for size, chars in block.chars_by_size:
                sizes[size] += chars
    return sizes.most_common(1)[0][0] if sizes else None


def _signature(block: _RawBlock) -> str:
    """A block's text with digits treated alike: page 3 matches page 4."""
    return re.sub(r"\d+", "#", " ".join(" ".join(block.lines).split())).lower()


def _boilerplate_signatures(raw_pages: list[list[_RawBlock]]) -> set[str]:
    """Short margin blocks that repeat on at least half the pages."""
    if len(raw_pages) < BOILERPLATE_MIN_PAGES:
        return set()
    pages_with: Counter[str] = Counter()
    for blocks in raw_pages:
        pages_with.update(
            {
                _signature(block)
                for block in blocks
                if block.in_margin and len(_signature(block)) <= BOILERPLATE_MAX_CHARS
            }
        )
    needed = max(BOILERPLATE_MIN_PAGES, math.ceil(len(raw_pages) / 2))
    return {signature for signature, count in pages_with.items() if count >= needed}


_HYPHENATED_END = re.compile(r"([A-Za-z]+)-$")
_LOWERCASE_START = re.compile(r"^([a-z]+)")


def _join_lines(lines: tuple[str, ...], vocabulary: set[str]) -> str:
    """Join a block's lines into one paragraph, rejoining hyphenated words.

    A line ending in letter + "-" followed by a line starting in lowercase is
    a word broken at the line end, or a compound that happened to break at its
    own hyphen. If the joined word occurs elsewhere in the document, it is
    joined without the hyphen ("pro-" "cess" becomes "process"); otherwise the
    hyphen is kept and only the line break removed ("well-defined").
    """
    text = ""
    for line in (line.strip() for line in lines):
        if not line:
            continue
        if not text:
            text = line
            continue
        end, start = _HYPHENATED_END.search(text), _LOWERCASE_START.match(line)
        if end and start:
            joined = (end.group(1) + start.group(1)).lower()
            text = text[:-1] + line if joined in vocabulary else text + line
        else:
            text = f"{text} {line}"
    return text


def _is_heading(raw: _RawBlock, text: str, body_size: float | None) -> bool:
    if body_size is None or len(text) > HEADING_MAX_CHARS:
        return False
    if len(raw.lines) > HEADING_MAX_LINES:
        return False
    if raw.size >= body_size * HEADING_SIZE_RATIO:
        return True
    return raw.bold and raw.size >= body_size * 0.95


# --- maths (decision record 26) -------------------------------------------------

# Fonts that set mathematics, by the names PDFs give them: TeX's own (CMMI,
# CMSY, CMEX, the AMS MSAM and MSBM, Euler, RSFS), every family with "Math"
# in its name (MathDesign, Cambria Math, Latin Modern Math, STIX Two Math,
# TeX Gyre ... Math), STIX and XITS, MathTime and MTPro, and Symbol.
MATHS_FONT = re.compile(
    r"math|cmmi|cmsy|cmex|msam|msbm|eufm|eurm|eusm|rsfs|stix|xits|mtpro|symbol",
    re.IGNORECASE,
)
# A page holds maths when at least this many of its characters are set in
# maths fonts. Fewer is a stray symbol in prose, not worth half a minute of
# the model: on a linear algebra textbook, 386 of 455 pages reach it.
MATHS_MIN_CHARS = 10

# The extension fonts hold big operators and delimiters, whose text layer is
# often not the symbol drawn: a summation sign reads "X" (_span_text).
_EXTENSION_FONT = re.compile(r"cmex|-Ex\b|extension", re.IGNORECASE)
# The symbol fonts, laid out as TeX's CMSY, set symbols in the places of the
# lowercase letters: a square root reads "p". They set no lowercase letter
# of text, so those are left out, but for the root. Their capitals are
# calligraphic letters.
_SYMBOL_FONT = re.compile(r"cmsy|-Sy\b", re.IGNORECASE)

# The model scales every image to the same budget of about 1,600 tokens, so
# a whole page gains nothing above 110 dpi. A half page at 150 dpi is seen
# about twice as large, which is what a second attempt needs.
PAGE_DPI = 110
HALF_PAGE_DPI = 150

# Text inside a large drawing or picture belongs to a figure: its labels may
# be left out of a transcription. Large means at least this share of the
# page's width and height; label means at most this many characters, since a
# framed box of text is a drawing too and its text must not be lost.
FIGURE_MIN_WIDTH = 0.15
FIGURE_MIN_HEIGHT = 0.08
FIGURE_LABEL_CHARS = 60


@dataclass(frozen=True)
class PageLayer:
    """A page's text layer, as a transcription of the page is checked
    against it."""

    # Blocks are separated by a blank line, a block's lines by a line break.
    required: str  # what a faithful transcription contains
    # What it may contain or leave out: figure labels, equation numbers,
    # footnote marks, and the lines in the margin band.
    optional: str
    # The lines in the top and bottom margin band, and each such block's
    # lines joined: a running header or footer, to drop from the
    # transcription, or a book's own first or last line (decision record 29).
    margins: tuple[str, ...]


# An equation's number at the end of its line, "(2.1)", and a footnote mark
# after a word, "Divergence∗": a transcription may leave them out, since
# neither changes the maths (decision record 29). A mark after one letter is
# maths, as in x∗, and stays required.
_EQUATION_NUMBER = re.compile(r"(?:^|(?<=\s))\(\d+(?:\.\d+){0,3}[a-z]?\)\s*$")
_FOOTNOTE_MARK = re.compile(r"(?<=[A-Za-z]{2})[∗*†‡](?=\s|$)")


def _optional_marks(line: str) -> tuple[str, list[str]]:
    """The line without its equation number and footnote marks, and those."""
    marks = _FOOTNOTE_MARK.findall(line)
    line = _FOOTNOTE_MARK.sub("", line)
    number = _EQUATION_NUMBER.search(line)
    if number:
        marks.append(number.group().strip())
        line = line[: number.start()].rstrip()
    return line, marks


def _open(path: Path) -> pymupdf.Document:
    try:
        return pymupdf.open(path, filetype="pdf")
    except (pymupdf.FileNotFoundError, pymupdf.FileDataError) as exc:
        raise ParseError("The file is not a readable PDF.") from exc


def maths_pages(path: Path) -> dict[int, int]:
    """How many characters each page sets in maths fonts, for the pages with
    at least MATHS_MIN_CHARS, numbered from 1."""
    found = {}
    with _PYMUPDF_LOCK, _open(path) as document:
        for page in document.pages():
            chars = sum(
                len(span["text"].strip())
                for block in page.get_text("dict", flags=_TEXT_FLAGS)["blocks"]
                if block.get("type") == 0
                for line in block["lines"]
                for span in line["spans"]
                if MATHS_FONT.search(span["font"])
            )
            if chars >= MATHS_MIN_CHARS:
                found[page.number + 1] = chars
    return found


def _split_at(page: pymupdf.Page) -> float:
    """Where to cut a page in two: the gap between text blocks nearest its
    middle, so no line is cut through."""
    middle = page.rect.height / 2
    gaps, bottom = [], None
    for top, low in sorted(
        (block[1], block[3]) for block in page.get_text("blocks") if block[6] == 0
    ):
        if bottom is not None and top > bottom:
            gaps.append((bottom + top) / 2)
        bottom = low if bottom is None else max(bottom, low)
    return min(gaps, key=lambda y: abs(y - middle)) if gaps else middle


def page_image(path: Path, page_number: int, half: str | None = None) -> bytes:
    """A page as a PNG for the vision model: whole, or its "top" or "bottom"
    half, cut between two blocks of text."""
    with _PYMUPDF_LOCK, _open(path) as document:
        page = document[page_number - 1]
        if half is None:
            return page.get_pixmap(dpi=PAGE_DPI).tobytes("png")
        cut, rect = _split_at(page), page.rect
        clip = (
            pymupdf.Rect(rect.x0, rect.y0, rect.x1, cut)
            if half == "top"
            else pymupdf.Rect(rect.x0, cut, rect.x1, rect.y1)
        )
        return page.get_pixmap(dpi=HALF_PAGE_DPI, clip=clip).tobytes("png")


# TeX's extension fonts (the OMX layout) hold big operators and radicals in
# the places of letters; a text layer without the font's own names for them
# reads a summation as "P" or "X". Each is read as the symbol it draws, and
# the rest of such a font, big brackets and their pieces, is left out.
_EXTENSION_SYMBOLS = {
    **dict.fromkeys("PX∑", "∑"),
    **dict.fromkeys("QY∏", "∏"),
    **dict.fromkeys("RZ∫", "∫"),
    **dict.fromkeys("HI∮", "∮"),
    # Not the display sizes, "[" and a backslash: those are also brackets'.
    **dict.fromkeys("S∪⋃", "∪"),
    **dict.fromkeys("T∩⋂", "∩"),
    **dict.fromkeys("pqrst√", "√"),
}


def _span_text(text: str, font: str) -> str:
    """A span's text as a transcription is checked against it: an extension
    font's big operators and radicals as the symbols they draw, and nothing
    else of it; no lowercase letter from a symbol font, but its radical,
    "p", as the root it is."""
    if _EXTENSION_FONT.search(font):
        return " ".join(_EXTENSION_SYMBOLS[c] for c in text if c in _EXTENSION_SYMBOLS)
    if _SYMBOL_FONT.search(font):
        return re.sub("[a-z]", "", text.replace("p", "√"))
    return text


def page_layer(path: Path, page_number: int) -> PageLayer:
    """The page's text layer, split as a transcription is checked against
    it: the running header and footer apart, figure labels apart, the
    extension fonts' big symbols left out."""
    with _PYMUPDF_LOCK, _open(path) as document:
        page = document[page_number - 1]
        width, height = page.rect.width, page.rect.height
        figures = [
            rect
            for rect in [
                *page.cluster_drawings(),
                *(pymupdf.Rect(image["bbox"]) for image in page.get_image_info()),
            ]
            if rect.width >= width * FIGURE_MIN_WIDTH
            and rect.height >= height * FIGURE_MIN_HEIGHT
        ]
        # A figure as found by its caption takes in labels set beside its
        # drawing, such as a plot's tick labels (record 29).
        figures += [
            pymupdf.Rect(f.rect) for f in _page_figures(page, document.page_count == 1)
        ]
        blocks = page.get_text("dict", flags=_TEXT_FLAGS)["blocks"]
    required, optional, margins = [], [], []
    for block in blocks:
        if block.get("type") != 0:
            continue
        lines = [
            "".join(
                _span_text(span["text"], span["font"]) for span in line["spans"]
            ).strip()
            for line in block["lines"]
        ]
        lines = [line for line in lines if line]
        if not lines:
            continue
        x0, top, x1, bottom = block["bbox"]
        if bottom <= height * BOILERPLATE_MARGIN or top >= height * (
            1 - BOILERPLATE_MARGIN
        ):
            # A running header, or the page's own first or last line where a
            # book has no header: the transcription may have it or not.
            margins += [*lines, " ".join(lines)]
            optional.append("\n".join(lines))
            continue
        marked = [_optional_marks(line) for line in lines]
        optional += [mark for _, marks in marked for mark in marks]
        lines = [line for line, _ in marked if line]
        if not lines:
            continue
        text = "\n".join(lines)  # line ends kept: a hyphen there joins a word
        centre = pymupdf.Point((x0 + x1) / 2, (top + bottom) / 2)
        in_figure = any(centre in rect for rect in figures)
        if in_figure and len(text) <= FIGURE_LABEL_CHARS:
            optional.append(text)
        else:
            required.append(text)
    return PageLayer("\n\n".join(required), "\n\n".join(optional), tuple(margins))


# --- figures (decision record 29) -----------------------------------------------

# A caption: "Figure 2.1.", "Fig. 3:", "Table 4 -", at the start of a block,
# the number followed by punctuation. "Figure 2.15 shows" begins a paragraph
# that talks about a figure, and is not one's caption.
CAPTION = re.compile(
    r"^\s*(figure|fig\.|table|chart|diagram|plate|exhibit)\s+"
    r"([A-Z]?\d+(?:[.\-–]\d+)*[a-z]?)\s*[.:—–\-](?:\s|$)",
    re.IGNORECASE,
)
# A paragraph: a block of at least this many words, most of them words of
# letters. A figure's labels, a table's cells and a sequence of letters are
# not, however long. Paragraphs outside figures part one figure from the
# next, and a drawing mostly filled by one is a framed box of text.
PARAGRAPH_WORDS = 25
PARAGRAPH_WORDY = 0.6
FRAMED_TEXT = 0.5
# A picture covering this much of its page is the page itself, scanned or
# photographed: its text is read by OCR (record 29), and it is a figure only
# in a document of one page, an uploaded picture.
PAGE_PICTURE = 0.8
# Parts of one figure lie this close, in points.
FIGURE_GAP = 6
# Labels set just above a drawing, such as a row of plot titles, within this.
LABELS_ABOVE = 24
# A caption with nothing drawn near it marks a figure of thin lines only when
# the space above it is at least this share of the page high.
LINE_FIGURE_MIN_HEIGHT = 0.08
# The resolution of a figure's picture for the model and for the reader.
FIGURE_DPI = 200


@dataclass(frozen=True)
class Figure:
    """A figure or drawn table on a page: where it is, in PDF points, and its
    caption, which lies outside rect, if it has one."""

    page: int
    rect: tuple[float, float, float, float]
    caption: str | None = None
    caption_rect: tuple[float, float, float, float] | None = None

    @property
    def key(self) -> str:
        """The figure's identity within a version of the file."""
        return f"{self.page}:" + ",".join(f"{v:.0f}" for v in self.rect)

    @property
    def crop(self) -> tuple[float, float, float, float]:
        """The figure with its caption, as the model and the reader see it."""
        rect = pymupdf.Rect(self.rect)
        if self.caption_rect:
            rect |= pymupdf.Rect(self.caption_rect)
        return (rect.x0, rect.y0, rect.x1, rect.y1)


@dataclass(frozen=True)
class PlacedFigure:
    """A figure in its page (decision record 31): page.text[start:end] is all
    its text there, gathered in one place, which the reader shows as the
    figure's picture. start equals end for a figure with no text. reading is
    the figure reading whose passage is part of that text, if one was
    accepted."""

    figure: Figure
    start: int
    end: int
    reading: str | None = None


@dataclass
class _TextBlock:
    rect: pymupdf.Rect
    text: str
    size: float = 0.0  # the font size of its first line
    lines: int = 1

    @property
    def is_paragraph(self) -> bool:
        words = self.text.split()
        wordy = [w for w in words if sum(c.isalpha() for c in w) >= 2]
        return (
            len(words) >= PARAGRAPH_WORDS and len(wordy) >= len(words) * PARAGRAPH_WORDY
        )


def _line_size(line: dict) -> float:
    spans = [s for s in line["spans"] if s["text"].strip()]
    return round(max((s["size"] for s in spans), default=0.0), 1)


def _text_blocks(page: pymupdf.Page) -> list[_TextBlock]:
    """The page's blocks of text. A caption is a block of its own, its lines
    those that share its first line's size: PyMuPDF can put a table's cells
    in the same block as the caption above them."""
    found = []
    for block in page.get_text("dict", flags=_TEXT_FLAGS)["blocks"]:
        if block.get("type") != 0:
            continue
        lines = [
            (
                pymupdf.Rect(line["bbox"]),
                "".join(s["text"] for s in line["spans"]),
                _line_size(line),
            )
            for line in block["lines"]
        ]
        lines = [line for line in lines if line[1].strip()]
        groups = [lines]
        if lines and CAPTION.match(lines[0][1]):
            size = lines[0][2]
            n = 1
            while n < len(lines) and abs(lines[n][2] - size) <= 0.3:
                n += 1
            groups = [lines[:n], lines[n:]]
        for group in groups:
            if not group:
                continue
            rect = pymupdf.Rect(group[0][0])
            for line in group[1:]:
                rect |= line[0]
            text = " ".join(" ".join(line[1] for line in group).split())
            found.append(_TextBlock(rect, text, group[0][2], len(group)))
    return found


def _merged(rects: list[pymupdf.Rect]) -> list[pymupdf.Rect]:
    """Rectangles that touch, or nearly, joined into one."""
    rects = [pymupdf.Rect(r) for r in rects]
    joined = True
    while joined:
        joined = False
        for i, a in enumerate(rects):
            for b in rects[i + 1 :]:
                if (a + (-FIGURE_GAP, -FIGURE_GAP, FIGURE_GAP, FIGURE_GAP)).intersects(
                    b
                ):
                    rects.remove(b)
                    rects[i] = a | b
                    joined = True
                    break
            if joined:
                break
    return sorted(rects, key=lambda r: (r.y0, r.x0))


def _candidates(page: pymupdf.Page, one_page: bool) -> list[pymupdf.Rect]:
    """What is drawn or pictured on the page, large enough to be a figure."""
    width, height = page.rect.width, page.rect.height
    area = width * height
    found = []
    for rect in [
        *page.cluster_drawings(),
        *(pymupdf.Rect(image["bbox"]) for image in page.get_image_info()),
    ]:
        rect &= page.rect
        if (
            rect.width < width * FIGURE_MIN_WIDTH
            or rect.height < height * FIGURE_MIN_HEIGHT
        ):
            continue
        if rect.width * rect.height >= area * PAGE_PICTURE and not one_page:
            continue  # the page itself, scanned
        found.append(rect)
    return _merged(found)


def _overlap(a: pymupdf.Rect, b: pymupdf.Rect) -> float:
    """How far two rectangles overlap side to side."""
    return max(0.0, min(a.x1, b.x1) - max(a.x0, b.x0))


def _join_caption_lines(blocks: list[_TextBlock], captions: list[_TextBlock]) -> None:
    """A caption's next line can be a block of its own, just below it: one
    line, in the caption's size."""
    for caption in captions:
        for b in blocks:
            if b in captions or b.lines != 1 or abs(b.size - caption.size) > 0.3:
                continue
            if (
                0 <= b.rect.y0 - caption.rect.y1 < 7
                and _overlap(b.rect, caption.rect) > 0
            ):
                caption.rect |= b.rect
                caption.text = f"{caption.text} {b.text}"
                blocks.remove(b)
                break


def _page_figures(page: pymupdf.Page, one_page: bool) -> list[Figure]:
    width, height = page.rect.width, page.rect.height
    blocks = _text_blocks(page)
    captions = [b for b in blocks if CAPTION.match(b.text)]
    _join_caption_lines(blocks, captions)
    drawn = _candidates(page, one_page)

    def framed(r: pymupdf.Rect) -> bool:
        return any(
            b.is_paragraph
            and r.contains(b.rect)
            and b.rect.width * b.rect.height >= r.width * r.height * FRAMED_TEXT
            for b in blocks
        )

    parts = [r for r in drawn if not framed(r)]
    # What parts one figure from the next: captions, and paragraphs that are
    # not text drawn inside a figure.
    stops = captions + [
        b
        for b in blocks
        if b.is_paragraph
        and b not in captions
        and not any(r.contains(b.rect) for r in parts)
    ]

    def blocked(top: float, bottom: float, caption: _TextBlock) -> bool:
        return any(
            s is not caption and s.rect.y0 >= top - 2 and s.rect.y1 <= bottom + 2
            for s in stops
        )

    def eligible(
        caption: _TextBlock, r: pymupdf.Rect, below: bool, side: bool = True
    ) -> bool:
        if side and _overlap(caption.rect, r) <= 0:
            return False
        if below:
            return r.y0 >= caption.rect.y1 - 4 and not blocked(
                caption.rect.y1, r.y0, caption
            )
        return r.y1 <= caption.rect.y0 + 4 and not blocked(
            r.y1, caption.rect.y0, caption
        )

    def is_table(caption: _TextBlock) -> bool:
        return caption.text.lstrip().lower().startswith("table")

    def thin_lines(caption: _TextBlock) -> pymupdf.Rect | None:
        """What is drawn or written above a caption, up to the text above:
        a figure of thin lines that no drawing cluster is large enough for."""
        top = max(
            (
                s.rect.y1
                for s in stops
                if s is not caption and s.rect.y1 <= caption.rect.y0
            ),
            default=0.0,
        )
        space = pymupdf.Rect(0, top, width, caption.rect.y0)
        there = [
            pymupdf.Rect(d["rect"])
            for d in page.get_drawings()
            if pymupdf.Rect(d["rect"]) in space
        ] + [b.rect for b in blocks if b.rect in space and b not in captions]
        if not there:
            return None
        tight = pymupdf.Rect(there[0])
        for r in there[1:]:
            tight |= r
        return tight if tight.height >= height * LINE_FIGURE_MIN_HEIGHT else None

    owned: dict[int, list[pymupdf.Rect]] = {id(c): [] for c in captions}
    free = list(parts)

    def assign(conventional: bool, wanting: list[_TextBlock]) -> None:
        """Each free drawing to the caption it lies under or over by the
        given convention and overlaps most; then the drawings beside one
        already given, in the same row, to the same caption."""
        for r in list(free):
            options = [
                c for c in wanting if eligible(c, r, below=is_table(c) == conventional)
            ]
            if options:
                best = max(
                    options,
                    key=lambda c: (
                        _overlap(c.rect, r),
                        -min(abs(c.rect.y0 - r.y1), abs(r.y0 - c.rect.y1)),
                    ),
                )
                owned[id(best)].append(r)
                free.remove(r)
        for r in list(free):
            for c in wanting:
                row = any(
                    min(o.y1, r.y1) - max(o.y0, r.y0) > 0.5 * min(o.height, r.height)
                    for o in owned[id(c)]
                )
                if row and eligible(
                    c, r, below=is_table(c) == conventional, side=False
                ):
                    owned[id(c)].append(r)
                    free.remove(r)
                    break

    # By convention a figure's caption is below it and a table's above it.
    assign(True, captions)
    # A figure caption with nothing drawn large enough above it may caption
    # thin lines there; failing that, any caption takes what is on its other
    # side.
    lines: dict[int, pymupdf.Rect] = {}
    for caption in captions:
        if not owned[id(caption)] and not is_table(caption):
            found_lines = thin_lines(caption)
            if found_lines is not None:
                lines[id(caption)] = found_lines
    assign(False, [c for c in captions if not owned[id(c)] and id(c) not in lines])

    found: list[tuple[pymupdf.Rect, _TextBlock | None]] = []
    for caption in captions:
        mine = owned[id(caption)]
        if mine:
            rect = pymupdf.Rect(mine[0])
            for r in mine[1:]:
                rect |= r
            found.append((rect, caption))
        elif id(caption) in lines:
            found.append((lines[id(caption)], caption))
        # A table caption with nothing drawn: an undrawn table is text, and
        # the text layer has it.
    found += [(r, None) for r in free]

    figures = []
    for rect, cap in found:
        # Labels and part titles: short blocks within the figure's band,
        # inside or alongside its drawings, or just above them.
        if cap is not None and cap.rect.y0 >= rect.y1 - 4:
            band = (rect.y0 - LABELS_ABOVE, cap.rect.y0)
        elif cap is not None:
            band = (cap.rect.y1, rect.y1)
        else:
            band = (rect.y0 - LABELS_ABOVE, rect.y1)
        reach = rect | cap.rect if cap is not None else rect
        for b in blocks:
            if b.is_paragraph or b in captions or _overlap(b.rect, reach) <= 0:
                continue
            in_band = b.rect.y0 >= band[0] - 2 and b.rect.y1 <= band[1] + 2
            near = cap is not None or b.rect.intersects(rect + (0, -LABELS_ABOVE, 0, 0))
            if in_band and near:
                rect |= b.rect
        rect &= page.rect
        if rect.is_empty:
            continue
        figures.append(
            Figure(
                page=page.number + 1,
                rect=(rect.x0, rect.y0, rect.x1, rect.y1),
                caption=cap.text if cap else None,
                caption_rect=(
                    (cap.rect.x0, cap.rect.y0, cap.rect.x1, cap.rect.y1)
                    if cap
                    else None
                ),
            )
        )
    return sorted(figures, key=lambda f: (f.rect[1], f.rect[0]))


def figures(path: Path) -> list[Figure]:
    """The figures and drawn tables of a document, in reading order: what is
    drawn or pictured large enough, with its caption when it has one, and
    figures of thin lines found by their caption alone."""
    with _PYMUPDF_LOCK, _open(path) as document:
        one_page = document.page_count == 1
        return [f for page in document.pages() for f in _page_figures(page, one_page)]


def figure_image(path: Path, figure: Figure) -> bytes:
    """The figure with its caption as a PNG."""
    with _PYMUPDF_LOCK, _open(path) as document:
        page = document[figure.page - 1]
        clip = pymupdf.Rect(figure.crop) + (-6, -6, 6, 6)
        return page.get_pixmap(dpi=FIGURE_DPI, clip=clip & page.rect).tobytes("png")


def figure_text(path: Path, figure: Figure) -> str:
    """The text the PDF sets inside the figure: its labels and cells."""
    with _PYMUPDF_LOCK, _open(path) as document:
        page = document[figure.page - 1]
        return page.get_text("text", clip=pymupdf.Rect(figure.rect), flags=_TEXT_FLAGS)
