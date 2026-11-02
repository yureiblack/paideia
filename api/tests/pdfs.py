"""Fixture PDFs, built in code so no binary files live in the repository.

Each builder returns the bytes of a small PDF with one particular property.
Damaged files are made by cutting bytes off a good one.

Every call produces a different file, even with the same text: PyMuPDF writes
a random file id into each PDF it saves. A test that needs "the same file
twice" must build it once and send those bytes twice.
"""

import pymupdf


def pdf(*pages: str) -> bytes:
    """A PDF with one page per argument, each holding that text. "" is blank."""
    document = pymupdf.open()
    for text in pages:
        page = document.new_page()
        if text:
            page.insert_text((72, 72), text)
    data = document.tobytes()
    document.close()
    return data


def long_pdf(page_count: int) -> bytes:
    """A PDF with substantial text on every page, big enough to damage."""
    return pdf(
        *(
            f"Page {n}. " + "Some sentence about memory. " * 30
            for n in range(1, page_count + 1)
        )
    )


def scanned_pdf() -> bytes:
    """One page holding only a picture of text: no text layer, like a scan."""
    source = pymupdf.open(stream=pdf("This text is only an image."), filetype="pdf")
    picture = source[0].get_pixmap(dpi=50)
    source.close()
    document = pymupdf.open()
    page = document.new_page()
    page.insert_image(page.rect, pixmap=picture)
    data = document.tobytes()
    document.close()
    return data


def encrypted_pdf() -> bytes:
    """A readable PDF locked with a password."""
    document = pymupdf.open(stream=pdf("Secret"), filetype="pdf")
    data = document.tobytes(
        encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="secret", owner_pw="owner"
    )
    document.close()
    return data


def png() -> bytes:
    """A PNG image: not a PDF, though PyMuPDF will open it as one."""
    source = pymupdf.open(stream=pdf("x"), filetype="pdf")
    data = source[0].get_pixmap(dpi=20).tobytes("png")
    source.close()
    return data


def cut(data: bytes, fraction: float) -> bytes:
    """The first part of a file, as a download cut short would leave it."""
    return data[: int(len(data) * fraction)]


# A valid PDF whose page tree is empty. Written by hand because PyMuPDF refuses
# to save a document with no pages.
ZERO_PAGE_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\n"
    b"trailer<</Root 1 0 R>>\n"
    b"%%EOF\n"
)


def html_pdf(
    *pages: str, header: str | None = None, page_numbers: bool = False
) -> bytes:
    """Pages laid out from HTML, as a word processor would, with real
    paragraphs and headings. Optionally a running header in the top margin
    and a page number in the bottom margin of every page.
    """
    document = pymupdf.open()
    for number, html in enumerate(pages, start=1):
        page = document.new_page()
        if header:
            page.insert_text((72, 40), header, fontsize=8)
        page.insert_htmlbox(pymupdf.Rect(72, 110, 540, 720), html)
        if page_numbers:
            page.insert_text((300, 800), str(number), fontsize=8)
    data = document.tobytes()
    document.close()
    return data


def lines_pdf(*lines: str) -> bytes:
    """One page whose text breaks exactly where each argument ends, for
    testing words hyphenated across lines."""
    document = pymupdf.open()
    page = document.new_page()
    page.insert_textbox(pymupdf.Rect(72, 300, 540, 600), "\n".join(lines))
    data = document.tobytes()
    document.close()
    return data


def two_column_pdf(left: str, right: str) -> bytes:
    """One page with two columns side by side."""
    document = pymupdf.open()
    page = document.new_page()
    page.insert_textbox(pymupdf.Rect(72, 300, 290, 700), left)
    page.insert_textbox(pymupdf.Rect(320, 300, 540, 700), right)
    data = document.tobytes()
    document.close()
    return data
