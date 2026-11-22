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
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import pymupdf

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


@dataclass(frozen=True)
class ParsedPage:
    number: int  # counted from 1, as a reader would
    text: str
    # Empty only for a page with no text. A Parser that cannot tell
    # paragraphs apart may leave it empty; the chunker then treats the whole
    # page text as one paragraph.
    blocks: tuple[ParsedBlock, ...] = ()


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
                raw_pages = [_raw_blocks(page) for page in document.pages()]
                repaired = document.is_repaired

        # Everything below is plain Python on the extracted data, so it runs
        # outside the lock.
        return ParsedDocument(pages=_build_pages(raw_pages), repaired=repaired)


def _raw_blocks(page: pymupdf.Page) -> list[_RawBlock]:
    height = page.rect.height
    blocks = []
    for block in page.get_text("dict", flags=_TEXT_FLAGS)["blocks"]:
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
            )
        )
    return blocks


def _build_pages(raw_pages: list[list[_RawBlock]]) -> list[ParsedPage]:
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
                )
            )
            text += paragraph
        pages.append(ParsedPage(number=index + 1, text=text, blocks=tuple(blocks)))
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
# not the symbol drawn: a summation sign reads "X".
_EXTENSION_FONT = re.compile(r"cmex|-Ex\b|extension", re.IGNORECASE)
# The symbol fonts, laid out as TeX's CMSY, set symbols in the places of the
# lowercase letters: a square root reads "p". They set no lowercase letter
# of text, so those are left out. Their capitals are calligraphic letters.
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
    optional: str  # figure labels, which it may contain or leave out
    margins: tuple[str, ...]  # lines of the running header and footer


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


def _span_text(text: str, font: str) -> str:
    """A span's text as a transcription is checked against it: nothing from
    an extension font, no lowercase letter from a symbol font."""
    if _EXTENSION_FONT.search(font):
        return ""
    if _SYMBOL_FONT.search(font):
        return re.sub("[a-z]", "", text)
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
            margins += [*lines, " ".join(lines)]
            continue
        text = "\n".join(lines)  # line ends kept: a hyphen there joins a word
        centre = pymupdf.Point((x0 + x1) / 2, (top + bottom) / 2)
        in_figure = any(centre in rect for rect in figures)
        if in_figure and len(text) <= FIGURE_LABEL_CHARS:
            optional.append(text)
        else:
            required.append(text)
    return PageLayer("\n\n".join(required), "\n\n".join(optional), tuple(margins))
