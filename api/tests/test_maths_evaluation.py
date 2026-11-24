"""Tests for the maths benchmark in evaluation/ (decision record 30).

Purpose: the maths benchmark's numbers are only as good as its corpus, its
comparison of a reading with the truth, and its planted mistakes. These
check that the lectures are well formed and show every kind of notation
often enough, that the questions hold, that the comparison ignores
presentation and counts every real change, that each kind of planted
mistake makes exactly the change it names, that kept readings are reused
rather than asked for again, and that the report only rewrites its marked
tables. None needs the model or a database; the benchmark itself runs
locally: python scripts/evaluate_maths.py.
"""

import shutil
from collections import Counter

import pytest

from app import maths
from app.llm import Generated
from app.parsing import PageLayer
from evaluation import (
    maths_benchmark,
    maths_compare,
    maths_corpus,
    maths_dataset,
    maths_planted,
    maths_readings,
    maths_report,
    notation,
)

# --- the lectures --------------------------------------------------------------------

SOURCE = """# A Lecture

## A section

Some prose with $x^2$ in it.

$$
a + b = c
$$

and it goes on.

- one item, $y$;
- another.

1. first
2. second
"""


def test_the_source_is_split_into_blocks_of_each_kind():
    blocks = maths_corpus.blocks(SOURCE)

    assert [b.kind for b in blocks] == [
        "title", "heading", "text", "display", "text", "item", "item", "numbered", "numbered",
    ]  # fmt: skip
    assert blocks[3].markdown == "$$\na + b = c\n$$"


def test_a_display_with_prose_after_its_closing_dollars_is_refused():
    with pytest.raises(ValueError, match="must end its block"):
        maths_corpus.blocks("$$\na = b\n$$ and more prose")


def test_the_latex_labels_every_block_and_keeps_maths_as_written():
    lecture = maths_corpus.Lecture(
        "x.pdf", "A Lecture", SOURCE, maths_corpus.blocks(SOURCE)
    )

    latex = maths_corpus.to_latex(lecture)

    assert all(f"\\label{{b{n}}}" in latex for n in range(len(lecture.blocks)))
    assert "$x^2$" in latex and r"\[a + b = c\]" in latex
    # A display belongs to the paragraph before it, and the next goes on.
    assert "it.\n\\label{b3}\\[" in latex and "\\]\n\\label{b4}and it goes on" in latex
    assert (
        latex.count("\\begin{itemize}") == 1 and latex.count("\\begin{enumerate}") == 1
    )
    assert "\\markright{A Lecture}" in latex


def test_prose_is_escaped_for_tex_but_maths_is_not():
    lecture = maths_corpus.Lecture(
        "x.pdf",
        "T",
        "# T\n\nA 50% rise & $a_1$ — done.",
        maths_corpus.blocks("# T\n\nA 50% rise & $a_1$ — done."),
    )

    assert r"A 50\% rise \& $a_1$ --- done." in maths_corpus.to_latex(lecture)


def test_a_page_s_truth_is_the_blocks_that_landed_on_it():
    lecture = maths_corpus.Lecture(
        "x.pdf", "A Lecture", SOURCE, maths_corpus.blocks(SOURCE)
    )
    typeset = maths_corpus.Typeset(b"", (1, 1, 1, 1, 2, 2, 2, 2, 2))

    assert maths_corpus.page_truth(lecture, typeset, 1).endswith("$$\na + b = c\n$$")
    assert maths_corpus.page_truth(lecture, typeset, 2) == (
        "and it goes on.\n\n- one item, $y$;\n- another.\n\n1. first\n2. second"
    )


def test_every_lecture_is_well_formed_and_every_formula_renders():
    lectures = maths_corpus.lectures()

    assert len(lectures) == 10
    for lecture in lectures:
        assert lecture.blocks[0].kind == "title"
        for block in lecture.blocks:
            stored = maths.from_model(block.markdown.replace("\n", " "))
            assert maths.problem(stored) is None, (
                lecture.filename,
                block.markdown[:60],
            )


def test_the_corpus_shows_every_kind_of_notation_often_enough():
    counts: Counter = Counter()
    for lecture in maths_corpus.lectures():
        for block in lecture.blocks:
            for formula in maths.formulas(
                maths.from_model(block.markdown.replace("\n", " "))
            ):
                counts.update(notation.kinds_in(formula))

    short = {
        k.name: counts[k.name]
        for k in notation.KINDS
        if counts[k.name] < notation.MIN_FORMULAS
    }
    assert short == {}


@pytest.mark.parametrize(
    ("latex", "kinds"),
    [
        (
            r"\sum_{i=1}^{n} \sigma_i^2",
            {"sum", "greek", "sigma", "subscript", "superscript"},
        ),
        (
            r"\Delta y \approx f'(x)\,\Delta x",
            {"greek", "delta", "relation", "prime", "derivative"},
        ),
        (
            r"\{ x \in \mathbb{Z} : x^2 < 10 \}",
            {
                "set_builder",
                "set_relation",
                "number_sets",
                "styled",
                "superscript",
                "inequality",
            },
        ),
        (r"\begin{vmatrix} a & b \\ c & d \end{vmatrix}", {"determinant"}),
        (r"\left[\begin{array}{cc|c} 1 & 2 & 3 \end{array}\right]", {"augmented"}),
    ],
)
def test_kinds_of_notation_are_recognised(latex, kinds):
    assert set(notation.kinds_in(latex)) == kinds


@pytest.mark.skipif(shutil.which("tectonic") is None, reason="needs Tectonic")
def test_a_lecture_typesets_and_every_block_lands_on_a_page():
    lecture = maths_corpus.lectures()[0]

    typeset = maths_corpus.typeset(lecture)

    assert typeset.pdf.startswith(b"%PDF-")
    assert len(typeset.pages) == len(lecture.blocks)
    assert typeset.pages == tuple(sorted(typeset.pages))  # in reading order
    assert maths_corpus.typeset(lecture).pdf == typeset.pdf  # the same bytes every time


# --- the questions -----------------------------------------------------------------


def test_the_questions_hold():
    questions = maths_dataset.load()

    assert len(questions) == 48
    assert maths_dataset.problems(questions) == []


def test_broken_questions_are_reported():
    good = maths_dataset.load()
    q = maths_dataset.Question
    e = maths_dataset.Evidence
    broken = [
        q("t99", "term", "What is a widget?", (e("01-linear-systems.pdf", "not in any lecture"),), term="widget"),
        q("m99", "meaning", "What is a determinant?", (e("02-matrices-and-determinants.pdf", "The trace of a square matrix is the sum of its diagonal entries"),), avoid=("determinant",)),
        q("f99", "formula", "x?", (e("01-linear-systems.pdf", "$x_1$"),)),
    ]  # fmt: skip

    found = maths_dataset.problems(good[3:] + broken)

    assert any("kinds are" in p for p in found)
    assert "t99: quote found 0 times in the lectures" in found
    assert "t99: the evidence does not contain the term" in found
    assert "m99: the question uses 'determinant'" in found
    assert (
        "m99: quote found 2 times in the lectures" not in found
    )  # each quote is unique
    assert "f99: the quote holds maths" in found


def test_a_quote_is_found_inexactly_when_a_reading_changed_a_word():
    among = [
        maths_dataset.Passage("a.pdf", 0, "Something else entirely."),
        maths_dataset.Passage(
            "a.pdf", 1, "Each operation can be reversed by another of the same kind."
        ),
        maths_dataset.Passage(
            "b.pdf", 0, "Each operation can be undone by another of the same kind."
        ),
    ]

    found = maths_dataset.holding(
        "Each operation can be undone by another of the same kind", "a.pdf", among
    )

    assert [p.ordinal for p in found] == [1]
    assert maths_dataset.holding("nothing like it at all here", "a.pdf", among) == []


# --- comparing a reading with the truth --------------------------------------------


def _compare(page: str, reading: str) -> maths_compare.Comparison:
    return maths_compare.compare(maths.from_model(page), maths.from_model(reading))


@pytest.mark.parametrize(
    "reading",
    [
        r"So $\dfrac{1}{2} \left( a \right)$ and $\begin{bmatrix} 1 & 2 \end{bmatrix}$ with $\mathbf{x}^{2}$, $x \le 1$.",
        r"So $\frac12 (a)$ and $\begin{pmatrix} 1 & 2 \end{pmatrix}$ with $x^2$, $x \leq 1$.",
        r"So $\frac{1}{2}\,(a)$ and $$\begin{pmatrix} 1 & 2 \end{pmatrix}$$ with $\boldsymbol{x}^2$, $x \leq 1.$",
    ],
)
def test_presentation_is_not_a_difference(reading):
    page = r"So $\frac{1}{2} (a)$ and $\begin{pmatrix} 1 & 2 \end{pmatrix}$ with $x^2$, $x \leq 1$."

    found = _compare(page, reading)

    assert [f.right for f in found.formulas] == [True, True, True, True]
    assert found.maths_errors == found.prose_errors == 0


@pytest.mark.parametrize(
    ("page", "reading"),
    [
        # An aligned derivation, as one environment or one line at a time.
        (
            r"$$\begin{aligned} a &= b \\ &= c \end{aligned}$$",
            r"$$\begin{align} a &= b \\ &= c \end{align}$$",
        ),
        (r"$$\begin{aligned} a &= b \\ &= c \end{aligned}$$", "$$a = b$$\n\n$$= c$$"),
        # An augmented matrix, its bar a rule or a cell.
        (
            r"$\left[\begin{array}{cc|c} 1 & 2 & 3 \end{array}\right]$",
            r"$\begin{bmatrix} 1 & 2 & | & 3 \end{bmatrix}$",
        ),
        # A labelled arrow, a percent sign, and signs or decimals in prose.
        (r"$\xrightarrow{R_2 - R_1}$", r"$\rightarrow_{R_2 - R_1}$"),
        (
            r"about $0.04\%$ here, with $+$ at the corner",
            "about 0.04% here, with + at the corner",
        ),
    ],
)
def test_layout_is_not_a_difference(page, reading):
    assert _compare(f"Then {page} holds.", f"Then {reading} holds.").right


def test_a_determinant_s_bars_are_not_a_matrix_s_brackets():
    assert not _compare(
        r"$\begin{vmatrix} 1 & 2 \end{vmatrix}$",
        r"$\left[\begin{array}{cc} 1 & 2 \end{array}\right]$",
    ).right


def test_a_function_name_outside_its_formula_is_still_right():
    found = _compare(
        r"When $\det A \neq 0$, it holds.", r"When det $A \neq 0$, it holds."
    )

    assert found.right


def test_a_formula_split_in_two_is_still_right():
    found = _compare(r"So $x = 1, y = 2$ here.", r"So $x = 1$, $y = 2$ here.")

    assert found.right


@pytest.mark.parametrize(
    ("page", "reading", "kind"),
    [
        (r"$a - b$", r"$a + b$", "sign"),
        (r"$x = 12$", r"$x = 13$", "digit"),
        (r"$x_i = 1$", r"$x_j = 1$", "letter"),
        (r"$\alpha + 1$", r"$\beta + 1$", "Greek letter"),
        (r"$a + b + c$", r"$a + c$", "left out"),
        (r"$f(x) = 1$", r"$f'(x) = 1$", "added"),
        (r"$\sqrt{2}$", r"$2$", "left out"),
        (
            r"$\begin{vmatrix} 1 & 2 \end{vmatrix}$",
            r"$\begin{pmatrix} 1 & 2 \end{pmatrix}$",
            "structure",
        ),
    ],
)
def test_a_change_to_the_maths_makes_the_formula_wrong(page, reading, kind):
    found = _compare(f"Then {page} holds.", f"Then {reading} holds.")

    [formula] = found.formulas
    assert not formula.right
    assert {c.kind for c in formula.changes} == {kind}
    assert found.maths_errors >= 1


def test_prose_and_maths_errors_are_counted_apart():
    found = _compare(r"The quick fox has $x = 1$ legs.", r"The fox has $x = 1$ legs.")

    assert found.right
    assert (found.prose_errors, found.maths_errors) == (1, 0)
    assert found.maths_tokens == 3


# --- planted mistakes --------------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "latex", "expected"),
    [
        ("sign", "a - b", ["a + b"]),
        ("digit", "x_1 = 9", ["x_2 = 9", "x_1 = 0"]),
        ("greek", r"\sigma^2", [r"\tau^2"]),
        ("delta", r"\Delta x", [r"\delta x"]),
        ("superscript", "e^{-x} + x^2", ["e + x^2", "e^{-x} + x"]),
        ("subscript", r"a_{ij} b_k", ["a b_k", "a_{ij} b"]),
        ("prime", "f''(x)", ["f'(x)", "f'(x)"]),
        ("root", r"\sqrt{x + 1}", ["x + 1"]),
        (
            "accent",
            r"\hat{\theta} = \bar{x}",
            [r"\theta = \bar{x}", r"\hat{\theta} = x"],
        ),
        ("fraction", r"\frac{a}{b + 1}", [r"\frac{b + 1}{a}"]),
        ("big_operator", r"\sum_{k} \int f", [r"\prod_{k} \int f", r"\sum_{k} \sum f"]),
        ("bounds", r"\int_0^{\infty} f", [r"\int_{\infty}^{0} f"]),
        (
            "partial",
            r"\frac{\partial f}{\partial x}",
            [r"\frac{df}{\partial x}", r"\frac{\partial f}{dx}"],
        ),
        (
            "set_relation",
            r"x \in A \subseteq B",
            [r"x \notin A \subseteq B", r"x \in A \supseteq B"],
        ),
        ("set_operation", r"A \cup B", [r"A \cap B"]),
        (
            "logic",
            r"\forall x \exists y",
            [r"\exists x \exists y", r"\forall x \forall y"],
        ),
        ("relation", r"a \leq b < c", [r"a \geq b < c", r"a \leq b > c"]),
        (
            "entry",
            r"\begin{pmatrix} 1 & 2 \end{pmatrix}",
            [
                r"\begin{pmatrix} & 2 \end{pmatrix}",
                r"\begin{pmatrix} 1 & \end{pmatrix}",
            ],
        ),
        (
            "swapped_entries",
            r"\begin{pmatrix} 1 & 2 \end{pmatrix}",
            [r"\begin{pmatrix} 2 & 1 \end{pmatrix}"],
        ),
    ],
)
def test_each_planted_mistake_makes_the_change_it_names(kind, latex, expected):
    edit = maths_planted.BY_NAME[kind].edit
    assert edit is not None

    assert [" ".join(x.split()) for x in edit(latex)] == [
        " ".join(x.split()) for x in expected
    ]


def test_letters_inside_words_and_environment_names_are_never_changed():
    assert maths_planted.letter(r"\text{if } x \begin{cases} a \end{cases}") == [
        r"\text{if } y \begin{cases} a \end{cases}",
        r"\text{if } x \begin{cases} b \end{cases}",
    ]


def test_planting_is_the_same_every_run_and_limited_per_page():
    page = "Prose here.\n\n$$a + b - c + d - e$$\n\nMore prose with $x + 1$."
    kind = maths_planted.BY_NAME["sign"]

    first = maths_planted.plant(page, kind, "seed")

    assert first == maths_planted.plant(page, kind, "seed")
    assert len(first) == maths_planted.PER_PAGE
    assert all(
        p.page_markdown != page and p.page_markdown.count("$") == page.count("$")
        for p in first
    )


def test_a_word_or_a_whole_display_can_be_left_out():
    page = "Prose words here.\n\n$$a = b$$\n\nMore."
    words = maths_planted._candidates(page, maths_planted.BY_NAME["word"])
    formulas = maths_planted._candidates(page, maths_planted.BY_NAME["formula"])

    assert {p.before for p in words} == {"Prose", "words", "here", "More"}
    assert [p.page_markdown for p in formulas] == ["Prose words here.\n\n\n\nMore."]


# --- kept readings -------------------------------------------------------------------


class _TwoPages:
    page_count = 2

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _Model:
    model_name = "test-model"

    def __init__(self):
        self.asked = 0

    def transcribe(self, prompt, image, again=False):
        self.asked += 1
        return Generated(
            value=f"answer {self.asked}",
            model=self.model_name,
            prompt_version="x",
            seconds=1.0,
        )


def test_readings_are_asked_for_once_and_kept(tmp_path, monkeypatch):
    monkeypatch.setattr(
        maths_readings,
        "image",
        lambda pdf, page, part: f"{pdf.name}:{page}:{part}".encode(),
    )
    monkeypatch.setattr(maths_readings.pymupdf, "open", lambda path: _TwoPages())
    store = tmp_path / "readings.json"
    pdfs = {"a.pdf": tmp_path / "a.pdf"}
    model = _Model()

    first = maths_readings.read_all(pdfs, model, store, progress=lambda s: None)
    again = maths_readings.read_all(pdfs, model, store, progress=lambda s: None)

    assert model.asked == 6  # two pages, three parts each, asked once
    assert [(r.page, r.part) for r in first] == [
        (1, "whole"), (1, "top"), (1, "bottom"), (2, "whole"), (2, "top"), (2, "bottom"),
    ]  # fmt: skip
    assert again == first
    assert maths_readings.load(store) == first


# --- the report ----------------------------------------------------------------------


def test_the_report_rewrites_only_its_marked_tables(monkeypatch):
    monkeypatch.setattr(
        maths_report, "tables", lambda results: {"truth": "NEW", "run": "RUN"}
    )
    document = (
        "Prose before.\n<!-- maths:truth -->\nold\nlines\n<!-- /maths:truth -->\n"
        "Between.\n<!-- maths:run -->\n<!-- /maths:run -->\nAfter."
    )

    assert maths_report.update(document, {}) == (
        "Prose before.\n<!-- maths:truth -->\nNEW\n<!-- /maths:truth -->\n"
        "Between.\n<!-- maths:run -->\nRUN\n<!-- /maths:run -->\nAfter."
    )


# --- scoring the readings, and the report made from them ---------------------------


TRUTH = "Some prose with $x^2 = 1$.\n\n$$\\alpha + b = 2$$"
LAYER = PageLayer("Some prose with x2 = 1.\nα + b = 2", "", ())


def _parts(whole: str, top: str, bottom: str) -> dict:
    def reading(part: str, answer: str) -> maths_readings.Reading:
        return maths_readings.Reading("a.pdf", 1, part, "sha", "m", "p", 10.0, answer)

    return {
        "whole": reading("whole", whole),
        "top": reading("top", top),
        "bottom": reading("bottom", bottom),
    }


@pytest.fixture(scope="module")
def pages() -> list[dict]:
    truth = maths_benchmark.stored_truth(TRUTH).text
    right_top, right_bottom = "Some prose with $x^2 = 1$.", "$$\\alpha + b = 2$$"
    cases = [
        _parts(TRUTH, right_top, right_bottom),  # read right whole
        _parts(
            TRUTH.replace("= 1", "= 7"), right_top, right_bottom
        ),  # a digit: halves kept
        _parts(
            TRUTH.replace("x^2", "y^2"), "garbage $x^2 = 9$", right_bottom
        ),  # a letter, let through
        _parts(
            TRUTH.replace("+", "-"), right_top, "$$\\beta + b = 2$$"
        ),  # refused both ways
    ]
    return [
        {
            "lecture": "a.pdf",
            "page": n,
            **maths_benchmark.score_page(parts, truth, LAYER),
        }
        for n, parts in enumerate(cases, start=1)
    ]


def test_the_app_keeps_the_whole_reading_then_the_halves_then_the_text_layer(pages):
    assert [p["app"]["kept"] for p in pages] == [
        "whole",
        "halves",
        "whole",
        "text layer",
    ]
    assert [p["app"]["seconds"] for p in pages] == [10.0, 30.0, 10.0, 30.0]


def test_the_readings_are_summed_up(pages):
    summary = maths_benchmark.reading_summary(pages)

    assert (summary["whole"]["right"], summary["whole"]["formulas"]) == (5, 8)
    assert summary["whole"]["pages_all_right"] == 1
    assert summary["app"]["kept"] == {"whole": 2, "halves": 1, "text layer": 1}
    assert (
        summary["app"]["right_in_read_pages"],
        summary["app"]["formulas_in_read_pages"],
    ) == (5, 6)
    assert summary["app"]["read_pages_with_a_wrong_formula"] == 1
    assert maths_benchmark.check_on_readings(pages)["whole"] == {
        "right_accepted": 1, "wrong_refused": 2, "wrong_accepted": 1,
    }  # fmt: skip
    notation_rows = maths_benchmark.notation_table(pages)
    assert (
        notation_rows["superscript"]["whole_right"],
        notation_rows["superscript"]["whole_formulas"],
    ) == (2, 4)
    assert (
        notation_rows["greek"]["kept_right"],
        notation_rows["greek"]["kept_formulas"],
    ) == (3, 3)
    assert maths_benchmark.change_kinds(pages) == {
        "digit": 2,
        "letter": 1,
        "sign": 1,
        "Greek letter": 1,
    }


def test_a_table_whose_closing_marker_is_missing_is_left_alone(monkeypatch):
    monkeypatch.setattr(
        maths_report, "tables", lambda results: {"truth": "NEW", "run": "RUN"}
    )
    document = "<!-- maths:truth -->\nkeep me\n<!-- maths:run -->\n<!-- /maths:run -->"

    assert maths_report.update(document, {}) == (
        "<!-- maths:truth -->\nkeep me\n<!-- maths:run -->\nRUN\n<!-- /maths:run -->"
    )


def test_every_report_table_is_made_from_the_results(pages):
    results = {
        "run": {
            "date": "2026-11-24T00:00:00+00:00", "commit": "abc1234", "uncommitted_changes": False,
            "fingerprint": "f00", "machine": {"processor": "M3", "memory_gb": 36, "system": "macOS"},
            "model": "m", "prompt": "page_transcription/v1", "tectonic": "Tectonic 0.17.0", "reviewed": None,
        },
        "corpus": {"lectures": 1, "pages": 4, "formulas": 8, "words": 40,
                   "notation": {k.name: 4 if k.name in ("superscript", "greek") else 0 for k in notation.KINDS}},
        "truth": {"pages": 4, "accepted": 3, "rows": [{"lecture": "a.pdf", "page": 4, "reason": "Its digits differ."}]},
        "planted": {"pages": 3, "per_page": 3, "kinds": {
            "sign": {"label": "A sign flipped", "planted": 3, "caught": 3, "missed": []},
            "fraction": {"label": "A fraction turned upside down", "planted": 2, "caught": 0,
                         "missed": [{"lecture": "a.pdf", "page": 1, "before": "\\frac{1}{2}", "after": "\\frac{2}{1}"}]},
        }},
        "reading": {
            "summary": maths_benchmark.reading_summary(pages),
            "check": maths_benchmark.check_on_readings(pages),
            "notation": maths_benchmark.notation_table(pages),
            "changes": maths_benchmark.change_kinds(pages),
            "pages": pages,
        },
        "timing": {"parse_ms_per_page": 9.1, "find_maths_ms_per_page": 9.3, "page_image_ms": 33.0,
                   "page_layer_ms": 23.0, "check_ms": 3.2, "model_seconds_per_page": 10.0, "hours_for_400_pages": 1.1},
        "retrieval": {"questions": {}, "variants": {
            variant: {
                "name": name, "seconds_to_read_again": 1.5,
                "methods": {"hybrid_rerank": {"name": "D. The app", "recall@5": {"all": 1.0},
                                              "rr": {"all": 0.5, "notation": 0.25}, "hit@1": {"all": 0.5}}},
                "latex_words": {"passages": 3, "commands": {"frac": 2}, "environments": {"pmatrix": 1}},
            }
            for variant, name in maths_benchmark.VARIANTS.items()
        }},
        "practice": {"model": "m", "concepts": 4, "concepts_with_an_exercise": 2, "exercises_offered": 3,
                     "exercises_that_fit": 2, "lecture_types_taught": 5, "lecture_types_offered": 2,
                     "seconds_extracting": 1.0, "seconds_choosing": 2.0,
                     "rows": [{"concept": "Bijection", "lectures": ["08-sets.pdf"], "offered": ["inverse"],
                               "refused_by_words": [], "fit": [], "misfit": ["inverse"], "teachable": []}]},
    }  # fmt: skip

    tables = maths_report.tables(results)

    assert all(table.strip() for table in tables.values())
    findings = tables["findings"]
    assert "accepted the perfect reading of 3 of 4 pages" in findings
    assert "got 5 of 8 formulas right (62.5%)" in findings
    assert "the check let a differing formula through on 1 of them" in findings
    assert "Never caught: a fraction turned upside down." in findings
    assert "Always caught: a sign flipped." in findings
    assert "| a | 4 | Its digits differ. |" in tables["truth"]
    assert "`\\frac{1}{2}` → `\\frac{2}{1}`" in tables["planted"]
    assert "| Bijection | 08 | inverse |" in tables["practice"]
    assert "\\frac 2" in tables["latex-words"]
    assert "Planted mistakes caught: 3 of 5" in maths_report.headline(results)


def test_the_results_file_keeps_only_the_formulas_read_wrong(pages):
    results = {
        "reading": {"summary": maths_benchmark.reading_summary(pages), "pages": pages}
    }

    written = maths_benchmark.slimmed(results)

    kept = [
        f
        for p in written["reading"]["pages"]
        for n in ("whole", "halves")
        for f in p[n]["results"]
    ]
    assert kept and not any(f["right"] for f in kept)
    assert written["reading"]["summary"] == results["reading"]["summary"]
    assert all(
        p["whole"]["results"]
        for p in pages
        if p["whole"]["right"] < p["whole"]["formulas"]
    )
