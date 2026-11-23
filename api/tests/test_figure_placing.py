"""Tests for putting a figure read by the model in its page
(app/services/figures.with_figures and its _place, decision record 29).

Purpose: prove that the figure takes the place of its caption and of the
text inside it that its reading repeats, that text it leaves out stays in
the page, and that on a page whose maths was read, which keeps no places,
the figure takes its caption's paragraph or else goes at the end.
"""

import uuid

from app.models import FigureReading
from app.parsing import PARAGRAPH_BREAK, ParsedBlock, ParsedPage
from app.services.figures import _place

CAPTION = "Figure 1. Two points."
FIGURE = (100.0, 100.0, 300.0, 200.0)


def row(text=("p1", "p2"), caption=CAPTION) -> FigureReading:
    return FigureReading(
        id=uuid.UUID("11111111-2222-3333-4444-555555555555"),
        page_number=1,
        rect=list(FIGURE),
        caption=caption,
        caption_rect=[100.0, 205.0, 300.0, 215.0] if caption else None,
        kind="plot",
        text=list(text),
        tables=[],
        description="Two points.",
    )


def page(*pieces: tuple[str, tuple | None]) -> ParsedPage:
    text, blocks = "", []
    for piece, box in pieces:
        if text:
            text += PARAGRAPH_BREAK
        blocks.append(ParsedBlock(len(text), len(text) + len(piece), False, box))
        text += piece
    return ParsedPage(1, text, tuple(blocks))


PASSAGE = f"{CAPTION} Plot: p1; p2. Described by the model: Two points."


def test_the_figure_takes_the_place_of_its_caption_and_the_labels_it_repeats():
    placed = _place(
        page(
            ("Above.", (100, 50, 300, 90)),
            ("p1", (110, 110, 120, 120)),
            ("p2", (280, 180, 290, 190)),
            (CAPTION, (100, 205, 300, 215)),
            ("Below.", (100, 230, 300, 260)),
        ),
        [row()],
    )

    assert placed.text.split(PARAGRAPH_BREAK) == ["Above.", PASSAGE, "Below."]
    figure = placed.blocks[1]
    assert figure.figure == "11111111-2222-3333-4444-555555555555"
    assert placed.text[figure.start : figure.end] == PASSAGE


def test_text_inside_the_figure_that_its_reading_leaves_out_stays():
    placed = _place(
        page(
            ("p1", (110, 110, 120, 120)),
            ("0 1 2 3", (100, 192, 300, 199)),  # tick labels the model skipped
            (CAPTION, (100, 205, 300, 215)),
        ),
        [row()],
    )

    assert placed.text.split(PARAGRAPH_BREAK) == [PASSAGE, "0 1 2 3"]


def test_on_a_page_whose_maths_was_read_the_figure_takes_its_captions_paragraph():
    # A page read by the vision model keeps no places on the page.
    read = page(("Above.", None), (CAPTION, None), ("Below.", None))

    placed = _place(read, [row()])

    assert placed.text.split(PARAGRAPH_BREAK) == ["Above.", PASSAGE, "Below."]


def test_a_figure_without_a_caption_or_places_goes_at_the_end():
    read = page(("Above.", None), ("Below.", None))

    placed = _place(read, [row(caption=None)])

    assert placed.text.split(PARAGRAPH_BREAK)[-1] == (
        "Plot: p1; p2. Described by the model: Two points."
    )
