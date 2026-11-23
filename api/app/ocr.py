"""Reading text from pictures with Tesseract (decision record 29).

Purpose
-------
A scanned page, a photograph of a board or a screenshot has no text layer:
its words are pixels. Tesseract reads them, through PyMuPDF, which returns
what it read in the same form as a PDF's own text, so the parser handles a
scanned page as it handles any other. It is fast, about a second a page, and
makes no guesses of its own: it reads what is there or misses it. So it runs
by itself whenever a document is read, unlike the vision model.

It also reads a figure's picture, to check a figure reading's words and
numbers against (app/figure_reading.py).

Tesseract is a program of its own, installed apart from Python (docs/setup.md).
Without it, or with settings.ocr off, scanned pages keep no text, as before.
"""

from functools import lru_cache

import pymupdf

from app.config import settings

# A page needs reading when it holds fewer characters of text than this and a
# picture covers at least PICTURE_SHARE of it: a scan may carry a stamped
# page number, and a page of text with a photo on it is not a scan.
SCANNED_MAX_CHARS = 20
PICTURE_SHARE = 0.5


@lru_cache
def tessdata() -> str | None:
    """Where Tesseract keeps its languages, or None if it is not installed."""
    try:
        found = pymupdf.get_tessdata()
    except RuntimeError:  # how PyMuPDF says Tesseract is not installed
        return None
    return found or None


def available() -> bool:
    return settings.ocr and tessdata() is not None


def is_scanned(page: pymupdf.Page, chars: int) -> bool:
    """Whether a page with this many characters of text is a picture of a
    page: little or no text, and a picture over most of it."""
    if chars >= SCANNED_MAX_CHARS:
        return False
    area = page.rect.width * page.rect.height
    return any(
        (pymupdf.Rect(image["bbox"]) & page.rect).get_area() >= area * PICTURE_SHARE
        for image in page.get_image_info()
    )


def text_page(page: pymupdf.Page, flags: int) -> pymupdf.TextPage:
    """The page's text as Tesseract reads it from the page drawn as an image."""
    return page.get_textpage_ocr(
        flags=flags,
        language=settings.ocr_language,
        dpi=settings.ocr_dpi,
        full=True,
        tessdata=tessdata(),
    )


def picture_text(png: bytes) -> str:
    """The text Tesseract reads in a picture, or "" without Tesseract."""
    if not available():
        return ""
    pixmap = pymupdf.Pixmap(png)
    data = pixmap.pdfocr_tobytes(language=settings.ocr_language, tessdata=tessdata())
    with pymupdf.open("pdf", data) as document:
        return document[0].get_text()
