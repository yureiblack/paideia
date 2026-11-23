"""Tests for finding a document's figures (app/parsing.figures, decision
record 29).

Purpose: prove that a figure is found with its labels and its caption, that
the parts of one figure are one figure, that a table's caption above it is
its own, that a figure of thin lines is found by its caption, and that
neither a paragraph about a figure, a framed box of text, nor a scanned
page is taken for one.
"""

from pathlib import Path

import pymupdf

from app import parsing
from tests import pdfs


def saved(tmp_path: Path, data: bytes) -> Path:
    path = tmp_path / "document.pdf"
    path.write_bytes(data)
    return path


def test_figures_are_found_with_their_captions_and_labels(tmp_path):
    path = saved(tmp_path, pdfs.figures_pdf())

    found = parsing.figures(path)

    assert [(f.page, f.caption) for f in found] == [
        (1, "Figure 1. A drawn figure with two labels."),
        (2, "Figure 2. Two parts of one figure."),
        (2, "Table 1. Some values."),
        (3, "Figure 4. Lines of four lengths."),
    ]
    first = found[0]
    assert "p1" in parsing.figure_text(path, first)
    assert "p2" in parsing.figure_text(path, first)
    # The caption lies outside the figure, inside what is cropped.
    assert pymupdf.Rect(first.caption_rect).y0 >= first.rect[3] - 1
    assert pymupdf.Rect(first.crop).contains(pymupdf.Rect(first.caption_rect))


def test_the_parts_of_one_figure_are_one_figure(tmp_path):
    path = saved(tmp_path, pdfs.figures_pdf())

    both = parsing.figures(path)[1]

    rect = pymupdf.Rect(both.rect)
    assert rect.x0 <= 80 and rect.x1 >= 530  # both drawings
    text = parsing.figure_text(path, both)
    assert "(a) Before." in text and "(b) After." in text


def test_a_tables_caption_above_it_is_its_own(tmp_path):
    path = saved(tmp_path, pdfs.figures_pdf())

    table = parsing.figures(path)[2]

    assert table.caption_rect[3] <= table.rect[1] + 1
    assert parsing.figure_text(path, table).split() == [
        "Name",
        "Value",
        "alpha",
        "12",
        "beta",
        "34",
    ]


def test_a_figure_of_thin_lines_is_found_by_its_caption(tmp_path):
    path = saved(tmp_path, pdfs.figures_pdf())

    lines = parsing.figures(path)[3]

    assert parsing.figure_text(path, lines).split() == ["1", "2", "3", "4"]


def test_a_paragraph_about_a_figure_and_a_framed_box_are_no_figures(tmp_path):
    path = saved(tmp_path, pdfs.figures_pdf())

    found = parsing.figures(path)

    assert not any("Figure 3" in (f.caption or "") for f in found)
    assert all(f.page != 3 or f.caption for f in found)  # the framed box


def test_a_page_that_is_one_picture_is_a_scan_unless_it_is_the_document(tmp_path):
    assert parsing.figures(saved(tmp_path, pdfs.picture_pdf(pages=2))) == []
    single = parsing.figures(saved(tmp_path, pdfs.picture_pdf(pages=1)))
    assert len(single) == 1 and single[0].caption is None


def test_a_figure_image_is_a_png_of_the_figure_and_its_caption(tmp_path):
    path = saved(tmp_path, pdfs.figures_pdf())
    figure = parsing.figures(path)[0]

    image = pymupdf.Pixmap(parsing.figure_image(path, figure))

    crop = pymupdf.Rect(figure.crop)
    assert abs(image.width - (crop.width + 12) * parsing.FIGURE_DPI / 72) < 3


def test_a_figures_key_is_its_page_and_place():
    figure = parsing.Figure(page=3, rect=(10.4, 20.6, 300.0, 400.2))
    assert figure.key == "3:10,21,300,400"


def test_captions_are_known_by_their_label_and_punctuation():
    for caption in (
        "Figure 2.1. Lines",
        "Fig. 3: A plot",
        "Table 4 - Values",
        "FIGURE 7. X",
    ):
        assert parsing.CAPTION.match(caption), caption
    for prose in ("Figure 2.15 shows four points", "Tables are text", "A figure 1."):
        assert not parsing.CAPTION.match(prose), prose
