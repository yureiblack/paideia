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


def test_symbols_whose_text_layer_is_a_letter_are_left_out():
    # TeX's symbol fonts set the radical sign where "p" would be, and the
    # extension fonts a summation sign where "X" would be. A test PDF cannot
    # embed those fonts, so the rule is checked on spans as PyMuPDF gives them.
    assert parsing._span_text("p", "MathDesign-CH-Regular-Sy") == ""
    assert parsing._span_text("−A", "CMSY10") == "−A"  # capitals: calligraphic
    assert parsing._span_text("X", "MathDesign-CH-Regular-Ex") == ""
    assert parsing._span_text("det p", "CharterBT-Roman") == "det p"
