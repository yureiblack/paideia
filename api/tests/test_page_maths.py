"""Tests for the maths side of app/parsing.py (decision record 26): which pages
hold maths, a page's image for the vision model, and its text layer split as
a transcription is checked against it.

Purpose: prove that maths is found by the fonts a PDF names and only where
there is enough of it, that a page is cut in two between lines, never
through one, and that the running header and a figure's labels are set
apart while a framed box of text is not.
"""

from pathlib import Path

import pymupdf

from app import parsing
from tests import pdfs


def saved(tmp_path: Path, data: bytes) -> Path:
    path = tmp_path / "document.pdf"
    path.write_bytes(data)
    return path


def test_pages_with_enough_maths_in_maths_fonts_are_found(tmp_path):
    path = saved(
        tmp_path,
        pdfs.maths_pdf(
            ("The characteristic polynomial is", "l2 - 6l + 1 = 0"),
            "A page of prose only, about the determinant.",
            ("A stray symbol", "l"),
        ),
    )

    found = parsing.maths_pages(path)

    assert list(found) == [1]
    assert found[1] >= parsing.MATHS_MIN_CHARS


def test_maths_fonts_are_known_by_their_names():
    for font in ("MathDesign-CH-Regular-Sy", "CMMI10", "CambriaMath", "Symbol"):
        assert parsing.MATHS_FONT.search(font), font
    for font in ("CharterBT-Roman", "Helvetica", "TimesNewRoman"):
        assert not parsing.MATHS_FONT.search(font), font


def test_the_running_header_is_set_apart(tmp_path):
    path = saved(
        tmp_path,
        pdfs.maths_pdf(("Some prose.", "l2 - 6l + 1 = 0"), header="5.2. EIGENVALUES"),
    )

    layer = parsing.page_layer(path, 1)

    assert "5.2. EIGENVALUES" in layer.margins
    assert "EIGENVALUES" not in layer.required
    assert "Some prose." in layer.required
    assert "l2 - 6l + 1 = 0" in layer.required


def test_a_figures_labels_are_optional_but_a_framed_box_is_not(tmp_path):
    framed = (
        "Recipe: parametric form. Write the system as an augmented matrix, row "
        "reduce it, and move every free variable to the right-hand side."
    )
    path = saved(tmp_path, pdfs.figure_pdf("(0, 2)", framed))

    layer = parsing.page_layer(path, 1)

    assert layer.optional == "(0, 2)"
    assert "Recipe: parametric form." in layer.required
    assert "(0, 2)" not in layer.required


def test_a_page_image_is_a_png_whole_or_in_halves(tmp_path):
    path = saved(tmp_path, pdfs.maths_pdf(("Some prose.", "l2 - 6l + 1 = 0")))
    with pymupdf.open(path) as opened:
        size = opened[0].rect

    whole = pymupdf.Pixmap(parsing.page_image(path, 1))
    top = pymupdf.Pixmap(parsing.page_image(path, 1, "top"))
    bottom = pymupdf.Pixmap(parsing.page_image(path, 1, "bottom"))

    def pixels(points: float, dpi: int) -> float:
        return points * dpi / 72

    assert abs(whole.width - pixels(size.width, parsing.PAGE_DPI)) <= 1
    # Each half is seen larger: drawn at a higher resolution than the page.
    assert abs(top.width - pixels(size.width, parsing.HALF_PAGE_DPI)) <= 1
    assert top.width == bottom.width
    assert (
        abs(top.height + bottom.height - pixels(size.height, parsing.HALF_PAGE_DPI))
        <= 2
    )


def test_a_page_is_cut_between_lines_nearest_its_middle(tmp_path):
    document = pymupdf.open()
    page = document.new_page()
    page.insert_textbox(pymupdf.Rect(72, 100, 540, 330), "First paragraph. " * 20)
    page.insert_textbox(pymupdf.Rect(72, 460, 540, 700), "Second paragraph. " * 20)
    path = saved(tmp_path, document.tobytes())

    with pymupdf.open(path) as opened:
        cut = parsing._split_at(opened[0])
        blocks = [b for b in opened[0].get_text("blocks") if b[6] == 0]

    first_bottom = max(b[3] for b in blocks if b[1] < 400)
    second_top = min(b[1] for b in blocks if b[1] > 400)
    assert first_bottom < cut < second_top


def test_symbols_whose_text_layer_is_a_letter_are_read_as_what_they_draw():
    # TeX's symbol fonts set the radical sign where "p" would be, and the
    # extension fonts a summation sign where "X" would be (decision record
    # 30). A test PDF cannot embed those fonts, so the rule is checked on
    # spans as PyMuPDF gives them.
    assert parsing._span_text("p", "MathDesign-CH-Regular-Sy") == "√"
    assert parsing._span_text("−A", "CMSY10") == "−A"  # capitals: calligraphic
    assert parsing._span_text("bx", "CMSY10") == ""  # other symbols: left out
    assert parsing._span_text("X", "MathDesign-CH-Regular-Ex") == "∑"
    assert parsing._span_text("PQRZISTp", "CMEX10") == "∑ ∏ ∫ ∫ ∮ ∪ ∩ √"
    assert parsing._span_text('()[]"#{}DE', "CMEX10") == ""  # big brackets
    assert parsing._span_text("∑∫√", "CMEX10") == "∑ ∫ √"  # already symbols
    assert parsing._span_text("det p", "CharterBT-Roman") == "det p"


def test_lines_in_the_margin_band_are_optional_as_well(tmp_path):
    # A running header, or a book's own first line where it has none: the
    # transcription may have it or not (decision record 29).
    path = saved(
        tmp_path,
        pdfs.maths_pdf(("Some prose.", "l2 - 6l + 1 = 0"), header="5.2. EIGENVALUES"),
    )

    layer = parsing.page_layer(path, 1)

    assert "5.2. EIGENVALUES" in layer.optional


def test_equation_numbers_and_footnote_marks_are_optional(tmp_path):
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 120), "Bregman Divergence* This section is optional.")
    page.insert_text((72, 160), "d(x, y) = x - y,")
    page.insert_text((400, 160), "(2.1)")
    page.insert_text((72, 200), "The value x* is the optimum, see (2.1) above.")
    path = saved(tmp_path, document.tobytes())

    layer = parsing.page_layer(path, 1)

    assert "Bregman Divergence This section is optional." in layer.required
    assert "(2.1)" in layer.optional.split("\n")
    assert "*" in layer.optional.split("\n")
    # A star after one letter is maths, and a number mid-sentence is text.
    assert "The value x* is the optimum, see (2.1) above." in layer.required


def test_a_figures_labels_beside_its_drawing_are_optional_too(tmp_path):
    # A plot's tick labels sit beside its axes, outside the drawing: the
    # figure as found by its caption takes them in (record 29).
    path = saved(tmp_path, pdfs.figures_pdf())

    layer = parsing.page_layer(path, 3)

    assert ["1", "2", "3", "4"] == [
        n for n in layer.optional.split("\n\n") if n.isdigit()
    ]
    assert "1" not in layer.required.split("\n\n")
