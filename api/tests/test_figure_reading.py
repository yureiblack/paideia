"""Tests for app/figure_reading.py: a figure's reading by the vision model
split into its parts, checked against the figure's own text, and made into
its passage (decision record 29).

Purpose: prove that the four parts are found however the model sets their
names, that tables are read as rows, that a number the figure does not show
is refused wherever it is written, that the text may differ from the
figure's by a few words but not more, and that the passage marks the
description as the model's.
"""

import pytest

from app.figure_reading import Reading, Table, Unusable, check, numbers, parse, passage

ANSWER = """KIND
plot

TEXT
p1
p2
x
y
0
1
2

TABLE
none

DESCRIPTION
Two points on axes from 0 to 2. Point p1 is at the top left and p2 at the bottom right.
"""

OWN = "p1\np2\nx\ny\n0\n1\n2\nFigure 1. Two points."


def test_the_four_parts_are_read():
    reading = parse(ANSWER)

    assert reading.kind == "plot"
    assert reading.text == ("p1", "p2", "x", "y", "0", "1", "2")
    assert reading.tables == ()
    assert reading.description.startswith("Two points on axes from 0 to 2.")


def test_parts_may_be_named_as_headings_in_bold_or_with_a_colon():
    answer = (
        "## Kind\nFlowchart\n\n**Text:**\n- Search Strategy\n- Evaluation\n\n"
        "Table: none\n\nDescription: Attributes go to a search strategy."
    )

    reading = parse(answer)

    assert reading.kind == "flowchart"
    assert reading.text == ("Search Strategy", "Evaluation")
    assert reading.description == "Attributes go to a search strategy."


def test_a_line_naming_a_table_is_not_taken_for_a_part():
    reading = parse("KIND\ntable\n\nTEXT\nTable 2.1\n\nDESCRIPTION\nA table.")

    assert reading.text == ("Table 2.1",)


def test_tables_are_rows_of_cells_each_with_the_title_above_it():
    answer = (
        "KIND\ntable\n\nTEXT\nnone\n\nTABLE\n(a) Record data.\n"
        "| Tid | Refund |\n|---|---|\n| 1 | Yes |\n| 2 | No |\n\n"
        "(b) Transaction data.\n| TID | ITEMS |\n| --- | --- |\n| 1 | Bread, Soda |\n\n"
        "DESCRIPTION\nTwo tables."
    )

    reading = parse(answer)

    assert reading.tables == (
        Table("(a) Record data.", (("Tid", "Refund"), ("1", "Yes"), ("2", "No"))),
        Table("(b) Transaction data.", (("TID", "ITEMS"), ("1", "Bread, Soda"))),
    )


def test_the_caption_written_again_in_the_text_is_left_out():
    answer = "KIND\nplot\n\nTEXT\nFigure 1. Two points.\np1\n\nDESCRIPTION\nPoints."

    assert parse(answer, caption="Figure 1. Two points.").text == ("p1",)


def test_an_answer_without_its_parts_is_unusable():
    with pytest.raises(Unusable, match="four parts"):
        parse("The figure shows two points.")
    with pytest.raises(Unusable, match="no description"):
        parse("KIND\nplot\n\nDESCRIPTION\n")


def test_a_faithful_reading_passes():
    assert check(parse(ANSWER), OWN) is None


def test_a_number_the_figure_does_not_show_is_refused_wherever_it_is():
    # On a data mining textbook: a grid of 3 by 7 plots called 3 by 9, and a
    # point placed at an x the axis never labels.
    in_description = ANSWER.replace("from 0 to 2", "from 0 to 9")
    in_text = ANSWER.replace("p2\n", "p2\n7\n")

    assert check(parse(in_description), OWN) == (
        "It gives numbers the figure does not show: 9."
    )
    assert "7" in (check(parse(in_text), OWN) or "")


def test_numbers_are_compared_as_values():
    # ".5" set without its zero is not taken for a number; "−3" is 3, as
    # signs are read apart from numbers on an axis.
    assert numbers("0.50, .5 is not read, −3 and 1983–1993") == [
        "0.5",
        "3",
        "1983",
        "1993",
    ]
    assert numbers("p1 and x2 are labels") == []


def test_a_few_words_may_differ_but_not_more():
    own = "Selected Attributes\nStopping Criterion\nEvaluation\nSearch Strategy\nAttributes"
    one_typo = Reading(
        "flowchart",
        ("Selected Atributes", "Stopping Criterion", "Evaluation", "Search Strategy"),
        (),
        "A loop.",
    )
    made_up = Reading(
        "flowchart",
        ("Gradient Descent", "Learning Rate", "Momentum", "Batch"),
        (),
        "A loop.",
    )

    assert check(one_typo, own) is None
    assert "differs from the figure's" in (check(made_up, own) or "")


def test_a_picture_with_no_text_of_its_own_is_checked_for_numbers_only():
    reading = Reading("photograph", ("Benzene",), (), "A ring of six atoms.")

    assert check(reading, "") is None
    assert check(Reading("photograph", (), (), "A ring of 6 atoms."), "") is not None


def test_the_passage_says_what_is_written_then_what_the_model_described():
    reading = Reading(
        "plot",
        ("p1", "p2"),
        (Table("Points", (("x", "y"), ("0", "2"))),),
        "Two points.",
    )

    assert passage(reading) == (
        "Plot: p1; p2. Points: x | y / 0 | 2. Described by the model: Two points."
    )


def test_a_long_word_set_apart_in_the_pdf_is_found_but_short_scraps_are_not():
    own = "new value = a * old value + b"
    joined = Reading("table", ("new_value", "old_value"), (), "A rule.")
    scraps = Reading("table", ("ewv", "alu", "ldv", "lue"), (), "A rule.")

    assert check(joined, own) is None
    assert "differs from the figure's" in (check(scraps, own) or "")


def test_tables_written_under_text_are_tables_their_header_cells_as_lines():
    # How the model wrote a textbook's figure of four tables: each table's
    # header cells as lines, a rule, then its rows; one with named rows has
    # no corner cell.
    answer = (
        "KIND\ntable\n\nTEXT\nTid\nRefund\n\n---\n\n| 1 | Yes |\n| 2 | No |\n\n---\n\n"
        "team\ncoach\n\n| Document 1 | 3 | 0 |\n| Document 2 | 0 | 7 |\n\n"
        "DESCRIPTION\nTwo tables.\n\n---\n"
    )

    reading = parse(answer)

    assert reading.tables == (
        Table(None, (("Tid", "Refund"), ("1", "Yes"), ("2", "No"))),
        Table(
            None,
            (("", "team", "coach"), ("Document 1", "3", "0"), ("Document 2", "0", "7")),
        ),
    )
    assert reading.text == ()
    assert reading.description == "Two tables."
