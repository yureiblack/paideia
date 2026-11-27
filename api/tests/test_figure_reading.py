"""Tests for app/figure_reading.py: a figure's reading by the vision model
split into its parts, checked against the figure's own text, and made into
its passage (decision records 29 and 31).

Purpose: prove that the four parts are found however the model sets their
names, that tables are read as rows, with or without bars at their ends,
that an underscore inside a word is kept, that a number the figure does not
show is refused wherever it is written, that a table's reading must give
most of its numbers, that the text may differ from the figure's by a few
words but not more, and that the passage is what is written in the figure,
never the model's description.
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


def test_the_passage_says_what_is_written_never_what_the_model_described():
    reading = Reading(
        "plot",
        ("p1", "p2"),
        (Table("Points", (("x", "y"), ("0", "2"))),),
        "Two points.",
    )

    assert passage(reading) == "Plot: p1; p2. Points: x | y / 0 | 2."
    assert passage(Reading("photograph", (), (), "A ring of atoms.")) == ""


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


# Table 2.9 of a textbook as its PDF sets it, and the model's answer, which
# gave the headers and none of the distances.
DISTANCES = (
    "p1 p2 p3 p4\np1 0.0 2.8 3.2 5.1\np2 2.8 0.0 1.4 3.2\n"
    "p3 3.2 1.4 0.0 2.0\np4 5.1 3.2 2.0 0.0"
)
HEADERS_ONLY = (
    "KIND\nTable\n\nTEXT\nTable 2.9.\nEuclidean distance matrix for Table 2.8.\n\n"
    "p1\np2\np3\np4\n\nDESCRIPTION\nA square matrix of distances between four points.\n"
)


def test_a_table_that_leaves_out_its_numbers_is_refused():
    own = DISTANCES + "\nTable 2.9. Euclidean distance matrix for Table 2.8."
    reading = parse(HEADERS_ONLY)

    assert check(reading, own) is None  # all it says is in the figure
    assert (
        check(reading, own, table_text=DISTANCES)
        # The caption written again gives 2.8, which the table also sets.
        == "It leaves out numbers the table shows: 15 of 16."
    )

    rows = "\n".join(
        f"| {line.replace(' ', ' | ')} |" for line in DISTANCES.split("\n")[1:]
    )
    complete = parse(
        f"KIND\ntable\n\nTABLE\n| | p1 | p2 | p3 | p4 |\n|---|---|---|---|---|\n{rows}\n\nDESCRIPTION\nDistances.\n"
    )
    assert check(complete, own, table_text=DISTANCES) is None


def test_a_table_may_leave_out_a_few_of_its_numbers():
    own = DISTANCES
    rows = DISTANCES.split("\n")[1:4]  # three of the four rows: 12 of 16 numbers
    answer = (
        "KIND\ntable\n\nTABLE\n"
        + "\n".join(f"| {line.replace(' ', ' | ')} |" for line in rows)
        + "\n\nDESCRIPTION\nDistances.\n"
    )

    assert check(parse(answer), own, table_text=DISTANCES) == (
        "It leaves out numbers the table shows: 4 of 16."
    )
    four = DISTANCES.split("\n")[1:5]
    answer = (
        "KIND\ntable\n\nTABLE\n"
        + "\n".join(f"| {line.replace(' ', ' | ')} |" for line in four)
        + "\n\nDESCRIPTION\nDistances.\n"
    )
    assert check(parse(answer), own, table_text=DISTANCES) is None


def test_rows_without_bars_at_their_ends_are_a_table_beside_a_separator():
    # How the model wrote a textbook's Table 2.4: no bar at either end of a
    # row, and a last column of ellipses, under the separator too.
    answer = (
        "KIND\nTable\n\nTEXT\nTransaction ID\nItem\n\nTABLE\n```\n"
        "Transaction ID | Item   | Price   | …\n"
        "--------------|--------|---------| …\n"
        "101123        | Watch  | $25.99  | …\n"
        "101124        | Shoes  | $75.00  | …\n"
        "```\n\nDESCRIPTION\nPurchases.\n"
    )

    reading = parse(answer)

    assert reading.tables == (
        Table(
            None,
            (
                ("Transaction ID", "Item", "Price", "…"),
                ("101123", "Watch", "$25.99", "…"),
                ("101124", "Shoes", "$75.00", "…"),
            ),
        ),
    )


def test_a_bar_in_a_line_of_text_is_no_table():
    answer = (
        "KIND\ntable\n\nTEXT\nd = |x - y|/(n - 1)\ns = 1 - d\nd = |x - y|\n\n"
        "DESCRIPTION\nFormulas.\n"
    )

    reading = parse(answer)

    assert reading.tables == ()
    assert reading.text == ("d = |x - y|/(n - 1)", "s = 1 - d", "d = |x - y|")


def test_an_underscore_inside_a_word_is_kept_and_emphasis_is_not():
    # The model wrote these right; the parser took min_d)/(max_ for italics.
    answer = (
        "KIND\ntable\n\nTEXT\nnew_value = f(old_value)\n"
        "s = 1 - (d - min_d)/(max_d - min_d)\n_Ordinal_\n**Ratio**\n*Interval*\n\n"
        "DESCRIPTION\nThe _new_value_ column.\n"
    )

    reading = parse(answer)

    assert reading.text == (
        "new_value = f(old_value)",
        "s = 1 - (d - min_d)/(max_d - min_d)",
        "Ordinal",
        "Ratio",
        "Interval",
    )
    assert reading.description == "The new_value column."


def test_two_tables_one_after_the_other_are_two_tables():
    # How the model wrote a textbook's Figure 2.4(a): two tables with a blank
    # line between them, each with its header and separator.
    answer = (
        "KIND\ntable\n\nTABLE\n| Time | Customer | Items |\n|---|---|---|\n"
        "| t1 | C1 | A, B |\n| t2 | C3 | A, C |\n\n"
        "| Customer | Time and Items |\n|---|---|\n| C1 | (t1: A,B) |\n| C3 | (t2: A, C) |\n\n"
        "DESCRIPTION\nTwo tables.\n"
    )

    reading = parse(answer)

    assert reading.tables == (
        Table(
            None,
            (("Time", "Customer", "Items"), ("t1", "C1", "A, B"), ("t2", "C3", "A, C")),
        ),
        Table(
            None,
            (("Customer", "Time and Items"), ("C1", "(t1: A,B)"), ("C3", "(t2: A, C)")),
        ),
    )
