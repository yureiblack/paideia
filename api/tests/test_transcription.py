"""Tests for app/transcription.py: a page's transcription made into page text,
and checked against the PDF's text layer (decision record 26).

Purpose: prove that every kind of mistake the vision model made on a real
textbook is refused (a sign read as a dot, a matrix row lost, a worked
example left out, a sentence of its own), that what only looks different
in a text layer is not (≠ drawn as a struck "=", a summation sign, a long
arrow, the running header, figure labels), and that Markdown becomes plain
page text with its maths in the stored form.
"""

import pytest

from app import maths
from app.parsing import PageLayer
from app.transcription import Unusable, check, page_text


def layer(required: str, optional: str = "", margins: tuple[str, ...] = ()):
    return PageLayer(required, optional, margins)


def reason(markdown: str, page_layer: PageLayer) -> str | None:
    return check(page_text(markdown, page_layer), page_layer).reason


# --- Markdown to page text -----------------------------------------------------


def test_paragraphs_become_blocks_and_headings_are_marked():
    page = page_text(
        "### 5.2 The Characteristic Polynomial\n\nWe will see below that it is a polynomial.",
        layer(
            "5.2 The Characteristic Polynomial\nWe will see below that it is a polynomial."
        ),
    )

    assert page.text == (
        "5.2 The Characteristic Polynomial\n\nWe will see below that it is a polynomial."
    )
    assert [(b.is_heading, page.text[b.start : b.end][:4]) for b in page.blocks] == [
        (True, "5.2 "),
        (False, "We w"),
    ]


def test_maths_is_stored_between_the_stored_delimiters():
    page = page_text(
        "The matrix $A - \\lambda I_n$ has entries\n\n$$\\det(A) = 0$$",
        layer("The matrix A−λIn has entries\ndet(A) = 0"),
    )

    assert (
        page.text
        == "The matrix \\(A - \\lambda I_n\\) has entries\n\n\\[\\det(A) = 0\\]"
    )
    assert maths.problem(page.text) is None


def test_a_displayed_formula_over_several_lines_stays_one_paragraph():
    page = page_text(
        "We have\n\n$$\n\\begin{pmatrix}\n1 & 2 \\\\\n\n3 & 4\n\\end{pmatrix}\n$$\n\nso on.",
        layer("We have\n1\n2\n3\n4\nso on."),
    )

    assert len(page.blocks) == 3
    assert page.text.split("\n\n")[1].startswith("\\[\\begin{pmatrix}")


def test_emphasis_quotes_and_rules_are_taken_out_of_prose_not_maths():
    page = page_text(
        "**Example.** Find *every* solution.\n\n---\n\n> A **free variable** is $x_*$.",
        layer("Example. Find every solution.\nA free variable is x∗."),
    )

    assert page.text == (
        "Example. Find every solution.\n\nA free variable is \\(x_*\\)."
    )


def test_bullets_and_numbered_items_are_paragraphs_of_their_own():
    page = page_text(
        "1. Learn the definition.\n2. Learn the recipe.\n- one\n- two",
        layer("1. Learn the definition.\n2. Learn the recipe.\n• one\n• two"),
    )

    assert page.text.split("\n\n") == [
        "1. Learn the definition.",
        "2. Learn the recipe.",
        "• one",
        "• two",
    ]


def test_a_sentence_of_the_models_own_before_the_page_is_dropped():
    page = page_text(
        "Here is the transcription of the provided page in Markdown with LaTeX:\n\n"
        "The determinant is $\\det(A)$.",
        layer("The determinant is det(A)."),
    )

    assert page.text == "The determinant is \\(\\det(A)\\)."


def test_the_running_header_is_dropped_but_a_heading_like_it_is_kept():
    header = layer(
        "1.2 Row Reduction\nThe method of elimination.",
        margins=("1.2. ROW REDUCTION", "11", "1.2. ROW REDUCTION 11"),
    )
    page = page_text(
        "1.2. ROW REDUCTION\n\n### 1.2 Row Reduction\n\nThe method of elimination.",
        header,
    )

    assert page.text == "1.2 Row Reduction\n\nThe method of elimination."
    assert check(page, header).reason is None


def test_latex_outside_a_formula_is_unusable():
    with pytest.raises(Unusable, match="LaTeX outside a formula"):
        page_text(
            "The columns span \\mathbb{R}^m when", layer("The columns span Rm when")
        )


def test_a_formula_that_would_not_render_is_unusable():
    with pytest.raises(Unusable, match="would not render"):
        page_text("Then $\\frac{1}{2$ holds.", layer("Then 1 2 holds."))


def test_an_empty_transcription_is_unusable():
    with pytest.raises(Unusable, match="empty"):
        page_text("\n---\n", layer("Some text."))


# --- the check: what it refuses ---------------------------------------------------


def test_a_faithful_transcription_passes():
    page_layer = layer("f (λ) = det(A−λI2) = (5 −λ)(1 −λ) −2 · 2 = λ2 −6λ + 1.")
    assert (
        reason(
            "$$f(\\lambda) = \\det(A - \\lambda I_2) = (5 - \\lambda)(1 - \\lambda)"
            " - 2 \\cdot 2 = \\lambda^2 - 6\\lambda + 1.$$",
            page_layer,
        )
        is None
    )


def test_a_minus_read_as_a_dot_is_refused():
    assert (
        reason(
            "$$8(\\tfrac14 \\cdot 0 \\cdot (-\\lambda))$$",
            layer("8(1 4 −0 · −λ)"),
        )
        == "Its operators differ from the PDF's text: 1 missing (−), 1 added (·)."
    )


def test_a_matrix_row_that_lost_its_plus_is_refused():
    assert reason(
        "$$\\begin{pmatrix} - & av & bw & - \\end{pmatrix}$$",
        layer("av + bw"),
    ).startswith("Its operators differ from the PDF's text: 1 missing (+)")


def test_a_worked_example_left_out_is_refused():
    found = reason(
        "We compute it. The answer is $$f(\\lambda) = -\\lambda^3 + 3\\lambda + 2.$$",
        layer(
            "We compute it.\ndet(A−λI3) = 8(1 4 −0) −λ(λ2 −6 · 1 2)\n= −λ3 + 3λ + 2."
        ),
    )

    assert found.startswith("Its digits differ from the PDF's text:")


def test_a_changed_digit_is_refused_even_if_the_book_has_a_typo():
    assert reason("$(-1)^{i+j}$", layer("(−1)i+1")).startswith(
        "Its digits differ from the PDF's text: 1 missing (1)"
    )


def test_more_than_one_percent_of_letters_different_is_refused():
    page = "A deadlock occurs when every thread in a set waits for another. " * 20
    # About 1,000 letters; the added sentence is 2% of them.
    found = reason("We will now prove it in detail. " + page, layer(page))

    assert found and found.startswith("Its words differ from the PDF's text")


# --- the check: what only looks different --------------------------------------


def test_a_word_dropped_or_a_typo_corrected_is_tolerated():
    text = "Finding the characterestic polynomial means computing the determinant. "
    text += "We will see below that it is in fact a polynomial. " * 20  # a page

    assert reason(text.replace("characterestic", "characteristic"), layer(text)) is None
    assert reason(text.replace("below ", "", 1), layer(text)) is None


def test_a_struck_through_equals_sign_is_not_equal():
    assert reason("For $i \\neq 1$ we note", layer("For i̸ = 1 we note")) is None


def test_a_long_arrow_and_a_long_implication_are_one_symbol():
    assert (
        reason(
            "$\\det : M \\to \\mathbb{R}$ and $A \\implies B$",
            layer("det: M −→R and A =⇒B"),
        )
        is None
    )


def test_a_long_labelled_arrow_is_one_arrow():
    # A row operation over a long arrow: the layer draws it in minus signs.
    assert (
        reason(
            "$$\\xrightarrow{R_2 = R_2 + R_1} \\begin{pmatrix} 1 \\end{pmatrix}$$",
            layer("R2=R2+R1\n−−−−−−−→\n1"),
        )
        is None
    )


def test_stars_and_dots_in_any_of_their_forms_match():
    assert (
        reason(
            "$$\\begin{pmatrix} 1 & * & \\cdots \\end{pmatrix} \\cdot x$$",
            layer("1 ⋆ · · · ⋅ x"),
        )
        is None
    )


def test_rules_drawn_as_matrix_cells_are_decoration():
    assert (
        reason(
            "$$\\begin{pmatrix} | & | \\\\ v_1 & v_2 \\\\ | & | \\end{pmatrix}"
            " = \\begin{pmatrix} - & w & - \\end{pmatrix}$$",
            layer("v1 v2 = w"),
        )
        is None
    )


def test_hyphens_in_words_are_not_minus_signs():
    assert (
        reason(
            "the upper-triangular matrix, computed row by row",
            layer("the upper-\ntriangular matrix, com-\nputed row by row"),
        )
        is None
    )


def test_figure_labels_may_be_left_out_or_kept():
    page_layer = layer("The ellipse below.", optional="(0,2)\n266x2 + 405y2 = 0")

    assert reason("The ellipse below.", page_layer) is None
    assert reason("The ellipse below. $266x^2 + 405y^2 = 0$", page_layer) is None


def test_order_is_not_seen_a_known_limit():
    # The book shows B with two columns swapped; the model wrote them back in
    # order. The same characters are there, so the check passes it.
    assert (
        reason(
            "$$B = \\begin{pmatrix} a_{11} & a_{12} & a_{13} \\end{pmatrix}$$",
            layer("B = a11 a13 a12"),
        )
        is None
    )


# --- found on a data mining textbook (decision record 29) -------------------------


def test_a_markdown_table_is_a_paragraph_per_row_its_separator_no_text():
    page_layer = layer(
        "Attribute Type\nDissimilarity\nNominal\nd = 0 if x = y\n"
        "Interval or Ratio\nd = |x − y|"
    )
    page = page_text(
        "| Attribute Type | Dissimilarity |\n|---|:---:|\n"
        "| Nominal | $d = 0$ if $x = y$ |\n| Interval or Ratio | $d = |x-y|$ |",
        page_layer,
    )

    assert page.text == (
        "Attribute Type | Dissimilarity\n\n"
        "Nominal | \\(d = 0\\) if \\(x = y\\)\n\n"
        "Interval or Ratio | \\(d = |x-y|\\)"
    )
    assert len(page.blocks) == 3
    assert check(page, page_layer).reason is None


def test_a_separator_row_would_otherwise_count_as_minus_signs():
    assert maths.shown("|---|---|") == "−−−−−−"  # why it is dropped


def test_subscripts_written_as_html_keep_their_letters():
    page_layer = layer("the L1 and L∞ distances; the ijth entry")
    page = page_text(
        "the L<sub>1</sub> and L<sub>∞</sub> distances; the $ij$<sup>th</sup> entry",
        page_layer,
    )

    assert "<" not in page.text
    assert check(page, page_layer).reason is None


def test_a_books_own_line_in_the_margin_band_may_be_written_or_not():
    # A book without a running header has real text in the band: the page's
    # last line here. The model writes it with LaTeX, so it does not match
    # the layer's line exactly, and must still not count as added.
    last = "(b) d(x, y) = 0 only if x = y."
    page_layer = layer("(a) d(x, x) ≥ 0 for all x.", optional=last, margins=(last,))

    written = "(a) $d(x, x) \\geq 0$ for all $x$.\n\n(b) $d(x, y) = 0$ only if $x = y$."
    assert reason(written, page_layer) is None
    assert reason("(a) $d(x, x) \\geq 0$ for all $x$.", page_layer) is None


def test_an_equation_number_and_a_footnote_mark_may_be_left_out():
    page_layer = layer(
        "Bregman Divergence This section\nd(x, y) = (xk − yk)2,",
        optional="∗\n(2.1)",
    )

    assert (
        reason(
            "Bregman Divergence This section\n\n$$d(x, y) = (x_k - y_k)^2,$$",
            page_layer,
        )
        is None
    )
    assert (
        reason(
            "Bregman Divergence∗ This section\n\n$$d(x, y) = (x_k - y_k)^2, \\quad (2.1)$$",
            page_layer,
        )
        is None
    )


# --- what the maths benchmark found (decision record 30) ------------------------
# Layers below are written as TeX's fonts leave them in a PDF: a prime "′",
# a hat "ˆ" before its letter, \notin as "/∈", a congruence's "(mod n)".


def test_a_line_of_a_displayed_formula_starting_with_e_is_not_a_command():
    # Joined after the repair of JSON's damage, "\n" + "e^x" read as \ne^x.
    page = page_text(
        "so\n\n$$\ne^x = \\sum_{n=0}^{\\infty} \\frac{x^n}{n!}\n$$",
        layer("so\nex =\n∞\nX\nn=0\nxn\nn!"),
    )

    assert page.text == "so\n\n\\[e^x = \\sum_{n=0}^{\\infty} \\frac{x^n}{n!}\\]"


def test_a_hyphen_after_a_formula_joins_a_word():
    page = layer("The n-th derivative and the p-series.")

    assert reason("The $n$-th derivative and the $p$-series.", page) is None


def test_tex_s_not_in_and_a_congruence_s_mod_match():
    page = layer("x /∈A and 38 ≡2 (mod 12)")

    assert reason("$x \\notin A$ and $38 \\equiv 2 \\pmod{12}$", page) is None
    assert reason("$x \\in A$ and $38 \\equiv 2 \\pmod{12}$", page) is not None


def test_a_hat_in_the_layer_is_an_accent_not_a_letter():
    page = layer("ˆθ = ¯x and ˆy, ˆp, ˆβ, ˆx")

    assert (
        reason(
            "$\\hat{\\theta} = \\bar{x}$ and $\\hat{y}$, $\\hat{p}$, $\\hat{\\beta}$, $\\hat{x}$",
            page,
        )
        is None
    )


@pytest.mark.parametrize(
    ("layer_text", "right", "wrong", "what"),
    [
        ("f′(x) = 3x2", "$f'(x) = 3x^2$", "$f(x) = 3x^2$", "operators"),
        ("ω = √k", "$\\omega = \\sqrt{k}$", "$\\omega = k$", "operators"),
        (
            "ˆθ is an estimate",
            "$\\hat{\\theta}$ is an estimate",
            "$\\theta$ is an estimate",
            "operators",
        ),
        # As parsing.page_layer gives TeX's big operators (test_page_maths).
        (
            "∑\nk\nak and ∑\nk ak",
            "$$\\sum_k a_k$$ and $\\sum_k a_k$",
            "$$\\prod_k a_k$$ and $\\sum_k a_k$",
            "operators",
        ),
        ("∫ 1\n0\nf", "$$\\int_0^1 f$$", "$$\\sum_0^1 f$$", "operators"),
        (
            "∂f\n∂x and ∇f",
            "$\\frac{\\partial f}{\\partial x}$ and $\\nabla f$",
            "$\\frac{df}{dx}$ and $\\nabla f$",
            "operators",
        ),
        (
            "∀ε > 0 ∃δ",
            "$\\forall \\varepsilon > 0 \\exists \\delta$",
            "$\\exists \\varepsilon > 0 \\exists \\delta$",
            "operators",
        ),
        (
            "λ2 + 4λ −21",
            "$\\lambda^2 + 4\\lambda - 21$",
            "$\\mu^2 + 4\\lambda - 21$",
            "Greek letters",
        ),
        ("∆x = h", "$\\Delta x = h$", "$\\delta x = h$", "Greek letters"),
    ],
)
def test_symbols_greek_letters_and_accents_are_compared(layer_text, right, wrong, what):
    # Each would have passed before: the check counted none of these
    # symbols, and Greek letters only within the prose's slack.
    page = layer(layer_text)

    assert reason(right, page) is None
    assert reason(wrong, page).startswith(f"Its {what} differ")


def test_a_letter_s_change_is_still_within_the_slack_a_known_limit():
    page = layer("Ri →cRi multiplies row i by c.")

    assert reason("$R_j \\to cR_i$ multiplies row $i$ by $c$.", page) is None


def test_a_symbol_the_layer_never_records_is_not_compared():
    # OpenStax's Calculus draws every radical as lines, and sets a big
    # integral in two pieces, "⌠" over "⌡".
    page = layer("ω = k and ⌠\n⌡ 1\n0 f and ∫ g")

    assert (
        reason("$\\omega = \\sqrt{k}$ and $$\\int_0^1 f$$ and $\\int g$", page) is None
    )
    assert reason("$\\omega = \\sqrt{k}$ and $$\\int_0^1 f$$ and $g$", page).startswith(
        "Its operators differ"
    )


def test_a_hyphen_in_words_inside_a_formula_is_not_a_minus():
    page = layer("(Area below the x-axis) −1")

    assert reason("$(\\text{Area below the } x\\text{-axis}) - 1$", page) is None


def test_a_picture_s_placeholder_is_not_text():
    page = page_text(
        "The car's speed.\n\n![Figure 5.20](image_url)\n\nFigure 5.20 The area under the curve.",
        layer("The car's speed.\nFigure 5.20 The area under the curve."),
    )

    assert page.text == "The car's speed.\n\nFigure 5.20 The area under the curve."


def test_a_hyphen_after_a_number_joins_a_word():
    page = layer("The 1-eigenspace, the −1-eigenspace and the (3 + √2)-eigenspace.")

    assert (
        reason(
            "The $1$-eigenspace, the $-1$-eigenspace and the $(3 + \\sqrt{2})$-eigenspace.",
            page,
        )
        is None
    )
