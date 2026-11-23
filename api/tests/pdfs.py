"""Fixture PDFs, built in code so no binary files live in the repository.

Each builder returns the bytes of a small PDF with one particular property.
Damaged files are made by cutting bytes off a good one.

Every call produces a different file, even with the same text: PyMuPDF writes
a random file id into each PDF it saves. A test that needs "the same file
twice" must build it once and send those bytes twice.
"""

import io

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


SCANNED_TEXT = "This text is only an image."


def scanned_pdf() -> bytes:
    """One page holding only a picture of text: no text layer, like a scan,
    at a resolution a scanner uses, so OCR can read it (record 29)."""
    source = pymupdf.open()
    source.new_page().insert_text((72, 120), SCANNED_TEXT, fontsize=20)
    picture = source[0].get_pixmap(dpi=150)
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


def gif() -> bytes:
    """A GIF: a picture of a kind uploads do not take."""
    return b"GIF89a" + b"\x00" * 2000


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


def maths_pdf(*pages: tuple[str, str] | str, header: str | None = None) -> bytes:
    """Pages of prose, each either a plain string or (prose, formula): the
    formula set in the Symbol font, as a maths page names a maths font, on
    its own line below the prose. Optionally a running header."""
    document = pymupdf.open()
    for page_content in pages:
        page = document.new_page()
        if header:
            page.insert_text((72, 40), header, fontsize=8)
        prose, formula = (
            page_content if isinstance(page_content, tuple) else (page_content, "")
        )
        page.insert_textbox(pymupdf.Rect(72, 100, 540, 300), prose)
        if formula:
            page.insert_text((72, 330), formula, fontname="symb", fontsize=12)
    data = document.tobytes()
    document.close()
    return data


def figure_pdf(label: str, framed: str) -> bytes:
    """One page with a figure, a large drawing holding a short label, and a
    framed box of text, a large drawing holding a long paragraph."""
    document = pymupdf.open()
    page = document.new_page()
    page.insert_textbox(pymupdf.Rect(72, 80, 540, 120), "Some prose above.")
    figure = pymupdf.Rect(100, 150, 500, 350)
    page.draw_rect(figure)
    page.draw_line(figure.tl, figure.br)
    page.insert_text((250, 250), label)
    frame = pymupdf.Rect(72, 400, 540, 560)
    page.draw_rect(frame)
    page.insert_textbox(frame + (10, 10, -10, -10), framed)
    data = document.tobytes()
    document.close()
    return data


PROSE = (
    "A data set can often be viewed as a collection of data objects, and data "
    "objects are described by a number of attributes that capture the basic "
    "characteristics of an object, such as the mass of a physical object or the "
    "time at which an event occurred, which this paragraph goes on to discuss."
)


def figures_pdf() -> bytes:
    """Pages laid out as a textbook sets its figures (decision record 29):

    1. a paragraph, a drawn figure with labels and a caption below it, a
       paragraph; then a paragraph beginning "Figure 3 shows", which talks
       about a figure and is no caption;
    2. two drawings side by side, each with a part title, and one caption
       below both; then a ruled table with its caption above it;
    3. a figure of thin lines, too small one by one to be found as drawings,
       found by its caption; and a framed box of text, which is no figure.
    """
    document = pymupdf.open()

    page = document.new_page()
    page.insert_textbox(pymupdf.Rect(72, 60, 540, 140), PROSE, fontsize=10)
    figure = pymupdf.Rect(150, 160, 450, 360)
    page.draw_rect(figure)
    page.draw_line(figure.tl, figure.br)
    page.insert_text((160, 180), "p1", fontsize=9)
    page.insert_text((400, 340), "p2", fontsize=9)
    page.insert_text(
        (150, 385), "Figure 1. A drawn figure with two labels.", fontsize=8
    )
    page.insert_textbox(pymupdf.Rect(72, 400, 540, 480), PROSE, fontsize=10)
    page.insert_textbox(
        pymupdf.Rect(72, 500, 540, 600),
        "Figure 3 shows the next idea. " + PROSE,
        fontsize=10,
    )

    page = document.new_page()
    page.insert_textbox(pymupdf.Rect(72, 40, 540, 110), PROSE, fontsize=10)
    for x0 in (80, 330):
        part = pymupdf.Rect(x0, 130, x0 + 200, 280)
        page.draw_rect(part)
        page.draw_circle(part.tl + (100, 75), 40)
    page.insert_text((140, 300), "(a) Before.", fontsize=8)
    page.insert_text((390, 300), "(b) After.", fontsize=8)
    page.insert_text((200, 325), "Figure 2. Two parts of one figure.", fontsize=8)
    page.insert_textbox(pymupdf.Rect(72, 345, 540, 420), PROSE, fontsize=10)
    page.insert_text((180, 445), "Table 1. Some values.", fontsize=8)
    table = pymupdf.Rect(150, 455, 450, 545)
    page.draw_rect(table)
    for y in (485, 515):
        page.draw_line((150, y), (450, y))
    page.draw_line((300, 455), (300, 545))
    for row, (a, b) in enumerate((("Name", "Value"), ("alpha", "12"), ("beta", "34"))):
        page.insert_text((160, 475 + row * 30), a, fontsize=10)
        page.insert_text((310, 475 + row * 30), b, fontsize=10)

    page = document.new_page()
    page.insert_textbox(pymupdf.Rect(72, 40, 540, 110), PROSE, fontsize=10)
    for n in range(4):
        y = 140 + n * 30
        page.draw_line((200, y), (200 + 20 * (n + 1), y))
        page.insert_text((180, y + 3), str(n + 1), fontsize=8)
    page.insert_text((150, 280), "Figure 4. Lines of four lengths.", fontsize=8)
    frame = pymupdf.Rect(72, 330, 540, 400)
    page.draw_rect(frame)
    page.insert_textbox(frame + (10, 10, -10, -10), PROSE, fontsize=10)

    data = document.tobytes()
    document.close()
    return data


def picture_pdf(pages: int = 1) -> bytes:
    """Pages that are each one picture filling the page, as a scan or an
    uploaded photograph is."""
    source = pymupdf.open(stream=pdf("A picture."), filetype="pdf")
    picture = source[0].get_pixmap(dpi=40).tobytes("png")
    source.close()
    document = pymupdf.open()
    for _ in range(pages):
        page = document.new_page()
        page.insert_image(page.rect, stream=picture)
    data = document.tobytes()
    document.close()
    return data


def photo(text: str, orientation: int = 1) -> bytes:
    """A JPEG of a line of text, as a phone saves it: with orientation 6 the
    pixels lie on their side and the EXIF tag says to turn them upright."""
    from PIL import Image

    source = pymupdf.open()
    page = source.new_page(width=500, height=150)
    page.insert_text((20, 90), text, fontsize=28)
    upright = Image.frombytes("RGB", (1000, 300), source[0].get_pixmap(dpi=144).samples)
    source.close()
    # Tag 6: the stored pixels lie a quarter turn counter-clockwise, and
    # are viewed after a quarter turn clockwise.
    stored = upright.rotate(90, expand=True) if orientation == 6 else upright
    exif = Image.Exif()
    exif[0x0112] = orientation
    buffer = io.BytesIO()
    stored.save(buffer, "JPEG", exif=exif.tobytes(), quality=90)
    return buffer.getvalue()
