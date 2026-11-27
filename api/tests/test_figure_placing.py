"""Tests for putting every figure in its page (app/services/figures.py,
with_figures and its _place, decision records 29 and 31).

Purpose: prove that each figure's text is gathered in one place and the page
records where, so the reader can show the figure's picture there instead:
a figure not read keeps the PDF's text, gathered; a figure read takes the
place of its caption and of the text inside it that its reading repeats,
with what it leaves out kept beside it; on a page whose maths was read,
which keeps no places, the figure takes its caption's paragraph or else
goes at the end; a figure with no text is placed where its height puts it.
And that the passage is what is written in the figure, never the model's
description.
"""

import uuid

from app.models import FigureReading
from app.parsing import PARAGRAPH_BREAK, Figure, ParsedBlock, ParsedPage
from app.services.figures import _place, _says_only, as_figure

CAPTION = "Figure 1. Two points."
FIGURE = (100.0, 100.0, 300.0, 200.0)
CAPTION_RECT = (100.0, 205.0, 300.0, 215.0)
READING_ID = "11111111-2222-3333-4444-555555555555"


def row(text=("p1", "p2"), caption=CAPTION) -> FigureReading:
    return FigureReading(
        id=uuid.UUID(READING_ID),
        page_number=1,
        figure_key=Figure(1, FIGURE).key,
        rect=list(FIGURE),
        caption=caption,
        caption_rect=list(CAPTION_RECT) if caption else None,
        kind="plot",
        text=list(text),
        tables=[],
        description="Two points, one above the other.",
    )


def read(reading: FigureReading):
    return (as_figure(reading), reading)


def found(rect=FIGURE, caption: str | None = CAPTION, caption_rect=CAPTION_RECT):
    return (Figure(1, rect, caption, caption_rect if caption else None), None)


def page(*pieces: tuple[str, tuple | None]) -> ParsedPage:
    text, blocks = "", []
    for piece, box in pieces:
        if text:
            text += PARAGRAPH_BREAK
        blocks.append(ParsedBlock(len(text), len(text) + len(piece), False, box))
        text += piece
    return ParsedPage(1, text, tuple(blocks))


def shown(placed: ParsedPage, index: int = 0) -> str:
    """The text the reader shows as the figure's picture."""
    figure = placed.figures[index]
    return placed.text[figure.start : figure.end]


PASSAGE = f"{CAPTION} Plot: p1; p2."


def test_the_figure_takes_the_place_of_its_caption_and_the_labels_it_repeats():
    placed = _place(
        page(
            ("Above.", (100, 50, 300, 90)),
            ("p1", (110, 110, 120, 120)),
            ("p2", (280, 180, 290, 190)),
            (CAPTION, (100, 205, 300, 215)),
            ("Below.", (100, 230, 300, 260)),
        ),
        [read(row())],
    )

    assert placed.text.split(PARAGRAPH_BREAK) == ["Above.", PASSAGE, "Below."]
    figure = placed.blocks[1]
    assert figure.figure == READING_ID
    assert placed.text[figure.start : figure.end] == PASSAGE
    assert shown(placed) == PASSAGE
    assert placed.figures[0].reading == READING_ID


def test_the_passage_never_holds_the_models_description():
    placed = _place(page((CAPTION, (100, 205, 300, 215))), [read(row())])

    assert "Two points, one above" not in placed.text
    assert "Described by the model" not in placed.text


def test_text_inside_the_figure_that_its_reading_leaves_out_stays_beside_it():
    placed = _place(
        page(
            ("p1", (110, 110, 120, 120)),
            ("0 1 2 3", (100, 192, 300, 199)),  # tick labels the model skipped
            (CAPTION, (100, 205, 300, 215)),
        ),
        [read(row())],
    )

    assert placed.text.split(PARAGRAPH_BREAK) == [PASSAGE, "0 1 2 3"]
    # Both are the figure's: the reader shows its picture for both.
    assert shown(placed) == f"{PASSAGE}{PARAGRAPH_BREAK}0 1 2 3"


def test_a_figure_not_read_gathers_its_own_text_in_one_place():
    placed = _place(
        page(
            ("p1", (110, 110, 120, 120)),
            # Beside the figure, in the other column: not the figure's.
            ("A paragraph beside it.", (320, 150, 500, 170)),
            ("0 1 2 3", (100, 192, 300, 199)),
            (CAPTION, (100, 205, 300, 215)),
            ("Below.", (100, 230, 300, 260)),
        ),
        [found()],
    )

    assert placed.text.split(PARAGRAPH_BREAK) == [
        "p1",
        "0 1 2 3",
        CAPTION,
        "A paragraph beside it.",
        "Below.",
    ]
    assert shown(placed) == PARAGRAPH_BREAK.join(["p1", "0 1 2 3", CAPTION])
    assert placed.figures[0].reading is None
    assert placed.figures[0].figure.key == Figure(1, FIGURE).key
    # The text stays ordinary text, for search and the summary.
    assert not any(b.figure for b in placed.blocks)


def test_on_a_page_whose_maths_was_read_the_figure_takes_its_captions_paragraph():
    # A page read by the vision model keeps no places on the page.
    transcribed = page(("Above.", None), (CAPTION, None), ("Below.", None))

    placed = _place(transcribed, [read(row())])
    unread = _place(transcribed, [found()])

    assert placed.text.split(PARAGRAPH_BREAK) == ["Above.", PASSAGE, "Below."]
    assert shown(placed) == PASSAGE
    assert unread.text == transcribed.text
    assert shown(unread) == CAPTION


def test_a_figure_without_a_caption_or_places_goes_at_the_end():
    transcribed = page(("Above.", None), ("Below.", None))

    placed = _place(transcribed, [read(row(caption=None))])

    assert placed.text.split(PARAGRAPH_BREAK)[-1] == "Plot: p1; p2."
    assert shown(placed) == "Plot: p1; p2."


def test_a_figure_with_no_text_is_placed_where_its_height_puts_it():
    placed = _place(
        page(("Above.", (100, 50, 300, 90)), ("Below.", (100, 230, 300, 260))),
        [found(caption=None)],
    )

    figure = placed.figures[0]
    assert placed.text == f"Above.{PARAGRAPH_BREAK}Below."
    assert figure.start == figure.end == len("Above.")


def test_two_figures_each_have_their_own_place_in_order():
    second = (100.0, 300.0, 300.0, 400.0)
    placed = _place(
        page(
            ("p1", (110, 110, 120, 120)),
            (CAPTION, (100, 205, 300, 215)),
            ("Between.", (100, 230, 300, 260)),
            ("q1", (110, 310, 120, 320)),
            ("Figure 2. Another.", (100, 405, 300, 415)),
        ),
        [
            found(second, "Figure 2. Another.", (100.0, 405.0, 300.0, 415.0)),
            found(),
        ],
    )

    assert [shown(placed, i) for i in range(2)] == [
        f"p1{PARAGRAPH_BREAK}{CAPTION}",
        f"q1{PARAGRAPH_BREAK}Figure 2. Another.",
    ]
    assert placed.text.split(PARAGRAPH_BREAK)[2] == "Between."


# A page whose maths was read, as the model wrote out page 6 of the data
# mining chapter: the tables' rows among the prose, with no places.
TRANSCRIBED = [
    "Above, a paragraph about distances.",
    "Table 2.8. x and y coordinates of four points.",
    r"point | \(x\) coordinate | \(y\) coordinate",
    "p1 | 0 | 2",
    "p2 | 2 | 0",
    "Table 2.9. Euclidean distance matrix for Table 2.8.",
    "p1 | p2",
    "p1 | 0.0 | 2.8",
    r"Table 2.11. | \(L_\infty\) distance matrix for Table 2.8.",
    r"\(L_\infty\) | p1",
    "p1 | 0.0 | 2.0",
    "```",
    r"2. Symmetry \(d(\mathbf{x}, \mathbf{y}) = d(\mathbf{y}, \mathbf{x})\) for all.",
]
TABLES = {
    "Table 2.8. x and y coordinates of four points.": (
        (19.0, 195.0, 188.0, 257.0),
        "point\nx coordinate\ny coordinate\np1\n0\n2\np2\n2\n0",
    ),
    "Table 2.9. Euclidean distance matrix for Table 2.8.": (
        (229.0, 195.0, 352.0, 257.0),
        "p1\np2\np1\n0.0\n2.8",
    ),
    "Table 2.11. L∞distance matrix for Table 2.8.": (
        (226.0, 293.0, 353.0, 355.0),
        "L∞\np1\n0.0\n2.0",  # its corner set as L_\infty, a subscript
    ),
}


def tables() -> tuple[list, dict[str, str]]:
    figures, own = [], {}
    for caption, (rect, text) in TABLES.items():
        figure = Figure(6, rect, caption, (rect[0], rect[1] - 12, rect[2], rect[1] - 2))
        figures.append((figure, None))
        own[figure.key] = f"{text}\n{caption}"
    return figures, own


def test_on_a_page_whose_maths_was_read_a_table_takes_the_rows_written_out_for_it():
    figures, own = tables()

    placed = _place(page(*((t, None) for t in TRANSCRIBED)), figures, own)

    assert [shown(placed, i).split(PARAGRAPH_BREAK) for i in range(3)] == [
        TRANSCRIBED[1:5],
        TRANSCRIBED[5:8],
        TRANSCRIBED[8:11],  # its caption, set out of order, found by its name
    ]
    # Prose stays prose, and a fence between a table and prose stays out.
    rest = placed.text[: placed.figures[0].start] + placed.text[placed.figures[2].end :]
    assert rest.split(PARAGRAPH_BREAK) == [
        "Above, a paragraph about distances.",
        "",
        "```",
        TRANSCRIBED[-1],
    ]


def test_on_a_page_whose_maths_was_read_a_reading_replaces_the_rows_it_repeats():
    figures, own = tables()
    reading = row(text=(), caption="Table 2.8. x and y coordinates of four points.")
    reading.page_number = 6
    reading.rect = list(TABLES[reading.caption][0])
    reading.caption_rect = [19.0, 183.0, 188.0, 193.0]
    reading.figure_key = as_figure(reading).key
    reading.tables = [
        {
            "title": None,
            "rows": [
                ["point", "x coordinate", "y coordinate"],
                ["p1", "0", "2"],
                ["p2", "2", "0"],
            ],
        }
    ]
    figures[0] = read(reading)

    placed = _place(page(*((t, None) for t in TRANSCRIBED)), figures, own)

    assert shown(placed) == (
        "Table 2.8. x and y coordinates of four points. Table: point | x coordinate"
        " | y coordinate / p1 | 0 | 2 / p2 | 2 | 0."
    )
    # The rows the reading repeats are gone from the page; the next table's
    # are its own.
    assert placed.text.split(PARAGRAPH_BREAK)[2:5] == TRANSCRIBED[5:8]


def test_latex_says_nothing_a_figure_could_and_a_subscript_is_joined():
    # L_1 is the PDF's L1, no number 1 of its own; \mathbf and \( are markup.
    own = "L1\np1\n4.0\nx coordinate"
    assert _says_only(r"\(L_1\) | p1 | 4.0 | \(\mathbf{x}\) coordinate", own) is True
    assert _says_only("p1 | 0.0 | 4.0", "L1\np1\n0.0\n2.0") is False
    assert _says_only("```", "L1") is None
