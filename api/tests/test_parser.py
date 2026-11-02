"""Tests for app/parsing.py: PDFs in, page-numbered text or ParseError out.

Purpose: prove page numbers survive, empty and scanned pages are kept rather
than failed, and every kind of unreadable file fails with a clear message.
The parser is tested on its own, with no database and no HTTP.
"""

from pathlib import Path

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
