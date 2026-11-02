"""Tests for app/parsing.py: PDFs in, page-numbered text or ParseError out.

Purpose: prove page numbers survive, paragraphs and headings are recovered,
text is cleaned for search, empty and scanned pages are kept rather than
failed, and every kind of unreadable file fails with a clear message. The
parser is tested on its own, with no database and no HTTP.
"""

from pathlib import Path

import pymupdf
import pytest

from app.parsing import ParseError, PyMuPDFParser
from tests import pdfs

parser = PyMuPDFParser()


def parse(tmp_path: Path, data: bytes):
    path = tmp_path / "upload.pdf"
    path.write_bytes(data)
    return parser.parse(path)


def test_each_page_keeps_its_number_and_text(tmp_path: Path):
    parsed = parse(tmp_path, pdfs.pdf("Processes", "Threads", "Memory"))

    assert [page.number for page in parsed.pages] == [1, 2, 3]
    assert [page.text.strip() for page in parsed.pages] == [
        "Processes",
        "Threads",
        "Memory",
    ]
    assert parsed.pages_with_text == 3
    assert parsed.repaired is False


def test_a_blank_page_is_kept_with_empty_text(tmp_path: Path):
    parsed = parse(tmp_path, pdfs.pdf("First", "", "Third"))

    assert [page.number for page in parsed.pages] == [1, 2, 3]
    assert parsed.pages[1].text == ""
    assert parsed.pages_with_text == 2


def test_a_scanned_page_parses_but_has_no_text(tmp_path: Path):
    parsed = parse(tmp_path, pdfs.scanned_pdf())

    assert len(parsed.pages) == 1
    assert parsed.pages_with_text == 0


def test_nul_characters_are_removed(tmp_path: Path):
    parsed = parse(tmp_path, pdfs.pdf("a\x00b"))

    assert "\x00" not in parsed.pages[0].text
    assert parsed.pages[0].text.strip() == "ab"


def test_a_damaged_but_repairable_file_parses_and_is_flagged(tmp_path: Path):
    parsed = parse(tmp_path, pdfs.cut(pdfs.long_pdf(200), 0.9))

    assert parsed.repaired is True
    assert len(parsed.pages) == 200


@pytest.mark.parametrize(
    ("data", "message"),
    [
        pytest.param(b"", "not a readable PDF", id="empty file"),
        pytest.param(b"%PDF-1.7\n", "not a readable PDF", id="header only"),
        pytest.param(b"plainly not a pdf\n" * 20, "not a readable PDF", id="text file"),
        pytest.param(
            pdfs.cut(pdfs.long_pdf(200), 0.5), "not a readable PDF", id="cut in half"
        ),
        pytest.param(pdfs.png(), "not a PDF", id="png"),
        pytest.param(pdfs.encrypted_pdf(), "password-protected", id="encrypted"),
        pytest.param(pdfs.ZERO_PAGE_PDF, "no pages", id="zero pages"),
    ],
)
def test_unreadable_files_raise_a_clear_parse_error(
    tmp_path: Path, data: bytes, message: str
):
    with pytest.raises(ParseError, match=message):
        parse(tmp_path, data)


def test_a_missing_file_raises_a_parse_error(tmp_path: Path):
    with pytest.raises(ParseError, match="missing"):
        parser.parse(tmp_path / "gone.pdf")


# --- paragraphs, headings and cleaning ----------------------------------------


def blocks_of(page) -> list[tuple[str, bool]]:
    return [(page.text[b.start : b.end], b.is_heading) for b in page.blocks]


def test_paragraphs_are_separated_by_a_blank_line_and_lines_are_joined(tmp_path: Path):
    html = (
        "<p>A process is a program in execution. It has its own address space, open"
        " files and at least one thread of control, which is long enough to wrap.</p>"
        "<p>The operating system keeps a process control block for each process.</p>"
    )
    page = parse(tmp_path, pdfs.html_pdf(html)).pages[0]

    first, second = page.text.split("\n\n")
    assert "\n" not in first  # its line wrap was joined
    assert first.startswith("A process is a program") and first.endswith("wrap.")
    assert second.startswith("The operating system keeps")


def test_headings_are_flagged_by_size_or_by_bold(tmp_path: Path):
    html = (
        "<h1>Chapter 3. Processes</h1><p>Body text about processes.</p>"
        "<h2>3.1 States</h2><p>Body text about states.</p>"
        "<p><b>Context switches</b></p><p>Body text about switching.</p>"
    )
    page = parse(tmp_path, pdfs.html_pdf(html)).pages[0]

    assert blocks_of(page) == [
        ("Chapter 3. Processes", True),
        ("Body text about processes.", False),
        ("3.1 States", True),
        ("Body text about states.", False),
        ("Context switches", True),
        ("Body text about switching.", False),
    ]


def test_block_positions_point_at_their_own_text(tmp_path: Path):
    html = "<h1>Title</h1><p>First paragraph.</p><p>Second paragraph.</p>"
    page = parse(tmp_path, pdfs.html_pdf(html)).pages[0]

    texts = [page.text[b.start : b.end] for b in page.blocks]
    assert texts == ["Title", "First paragraph.", "Second paragraph."]
    assert page.text == "\n\n".join(texts)


def test_ligatures_are_expanded(tmp_path: Path):
    page = parse(
        tmp_path, pdfs.html_pdf("<p>Open files and a well defined flow.</p>")
    ).pages[0]

    assert "\ufb01" not in page.text  # the single-character "fi" ligature
    assert "files" in page.text and "defined" in page.text


def test_a_word_broken_across_lines_is_rejoined(tmp_path: Path):
    data = pdfs.lines_pdf(
        "Every process has an entry. The kernel keeps a pro-", "cess table."
    )
    page = parse(tmp_path, data).pages[0]

    assert "keeps a process table." in page.text


def test_a_compound_broken_at_its_own_hyphen_keeps_the_hyphen(tmp_path: Path):
    page = parse(
        tmp_path, pdfs.lines_pdf("It has a well-", "defined lifecycle.")
    ).pages[0]

    assert "a well-defined lifecycle." in page.text


def test_two_columns_are_read_one_column_at_a_time(tmp_path: Path):
    data = pdfs.two_column_pdf("Left one.\n\nLeft two.", "Right one.\n\nRight two.")
    page = parse(tmp_path, data).pages[0]

    assert [text for text, _ in blocks_of(page)] == [
        "Left one.",
        "Left two.",
        "Right one.",
        "Right two.",
    ]


def test_running_headers_and_page_numbers_are_dropped(tmp_path: Path):
    pages = [f"<p>Content of page {n}.</p>" for n in range(1, 5)]
    data = pdfs.html_pdf(
        *pages, header="Operating Systems, Lecture 3", page_numbers=True
    )

    parsed = parse(tmp_path, data)

    for number, page in enumerate(parsed.pages, start=1):
        assert page.text == f"Content of page {number}."


def test_body_text_matching_a_running_header_is_kept(tmp_path: Path):
    # The title runs in every page's top margin and also opens page 1 as a
    # heading. Only the margin copies are headers.
    pages = ["<h1>Operating Systems</h1><p>Welcome.</p>"] + [
        f"<p>Content of page {n}.</p>" for n in range(2, 5)
    ]
    parsed = parse(tmp_path, pdfs.html_pdf(*pages, header="Operating Systems"))

    assert parsed.pages[0].text == "Operating Systems\n\nWelcome."
    assert parsed.pages[1].text == "Content of page 2."


def test_only_repetition_inside_the_margins_makes_a_header(tmp_path: Path):
    # "Note N." repeats in the body of pages 1-3 and appears once in the
    # bottom margin of page 4. Body repetition does not make it a header, so
    # the margin copy stays too.
    document = pymupdf.open()
    for n in range(1, 5):
        page = document.new_page()
        page.insert_text(
            (72, 300), f"Body text of page {n}, long enough to be content."
        )
        if n < 4:
            page.insert_text((72, 400), f"Note {n}.")
        else:
            page.insert_text((72, 805), "Note 4.")
    parsed = parse(tmp_path, document.tobytes())

    assert parsed.pages[3].text.endswith("Note 4.")


def test_a_short_document_keeps_its_headers(tmp_path: Path):
    # Two pages are too few to tell a running header from real content.
    data = pdfs.html_pdf(
        "<p>One.</p>", "<p>Two.</p>", header="Lecture 3", page_numbers=True
    )

    parsed = parse(tmp_path, data)

    assert "Lecture 3" in parsed.pages[0].text


def test_repeated_long_content_is_not_mistaken_for_a_header(tmp_path: Path):
    # Every page of long_pdf repeats "Page N. Some sentence..." with only the
    # number changing; it is content, not a running header.
    parsed = parse(tmp_path, pdfs.long_pdf(4))

    assert all(page.text.startswith(f"Page {page.number}.") for page in parsed.pages)
