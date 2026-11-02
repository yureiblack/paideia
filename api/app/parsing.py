"""Turning a PDF file into page-numbered text.

Purpose
-------
Everything that knows how to read a PDF lives here, behind a small interface:
a Parser takes a file path and returns the text of each page, numbered from 1,
or raises ParseError with a message fit to show the user. Nothing else in the
backend imports pymupdf, so another library could replace it by adding one
class to this file.

The PyMuPDF implementation follows rules found by prototyping the library
before writing this; decision record 03 has the details:
- A PDF is recognised by doc.is_pdf as well as its first bytes, because
  PyMuPDF will happily open a PNG as a one-page "document".
- Password-protected files open but cannot be read, so needs_pass is checked
  first. A file with zero pages opens without complaint and is refused here.
- Damaged files are often repaired on open with every page intact. They are
  accepted and flagged as repaired rather than failed.
- NUL characters survive extraction and Postgres TEXT refuses them.
- Text is taken in the PDF's own order; the sort option interleaves the two
  columns of a two-column page.
"""

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import pymupdf

# MuPDF prints its complaints about damaged files straight to the console.
# Problems are reported through the document's status instead.
pymupdf.TOOLS.mupdf_display_errors(False)

# PyMuPDF's documentation: it "does not support running on multiple threads -
# doing so may cause incorrect behaviour or even crash Python itself." Parsing
# runs in background tasks, which run on threads, so every PyMuPDF call holds
# this lock. Parsing 300 pages takes well under a tenth of a second, so taking
# turns costs almost nothing.
_PYMUPDF_LOCK = threading.Lock()


class ParseError(Exception):
    """The file cannot be read as a PDF. The message is shown to the user."""


@dataclass(frozen=True)
class ParsedPage:
    number: int  # counted from 1, as a reader would
    text: str


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

                pages = [
                    ParsedPage(number=index + 1, text=_clean(page.get_text()))
                    for index, page in enumerate(document)
                ]
                return ParsedDocument(pages=pages, repaired=document.is_repaired)


def _clean(text: str) -> str:
    """Remove NUL characters, which some PDFs contain and Postgres refuses."""
    return text.replace("\x00", "")
