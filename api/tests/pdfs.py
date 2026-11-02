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
