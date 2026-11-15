"""Tests for app/filenames.py: the name an upload is shown by.

Purpose: a client chooses the name, so it is cleaned before it is stored
(decision record 21): only the last part of a path, normalised Unicode, no
control or invisible formatting characters, whitespace collapsed, and at
most 200 characters with the extension kept. Nothing displayable left is
refused.
"""

import unicodedata

import pytest
from fastapi.testclient import TestClient

from app.filenames import MAX_LENGTH, BadFilename, display_name
from tests import pdfs
from tests.test_documents_api import new_environment, upload

RLO = "\u202e"  # right-to-left override
ZWSP = "\u200b"  # zero-width space


@pytest.mark.parametrize(
    ("raw", "shown"),
    [
        ("notes.pdf", "notes.pdf"),
        ("../../etc/notes.pdf", "notes.pdf"),
        ("C:\\Users\\ana\\Week 5.pdf", "Week 5.pdf"),
        ("  Week\t5\n\nnotes .pdf  ", "Week 5 notes .pdf"),
        (f"invoice{RLO}fdp.exe", "invoicefdp.exe"),
        (f"lec{ZWSP}ture.pdf", "lecture.pdf"),
        ("bell\x07 and null\x00.pdf", "bell and null.pdf"),
        ("line\u2028break.pdf", "line break.pdf"),
        ("Lecture – Ω.pdf", "Lecture – Ω.pdf"),
    ],
)
def test_names_are_cleaned(raw, shown):
    assert display_name(raw) == shown


def test_unicode_is_normalised():
    decomposed = unicodedata.normalize("NFD", "café.pdf")

    assert decomposed != "café.pdf"
    assert display_name(decomposed) == "café.pdf"


def test_long_names_are_cut_keeping_the_extension():
    shown = display_name("a" * 300 + ".pdf")

    assert len(shown) == MAX_LENGTH
    assert shown.endswith("aaa.pdf")
    # An "extension" too long to be one is just part of the name.
    assert (
        display_name("b" * 150 + "." + "c" * 150)
        == ("b" * 150 + "." + "c" * 150)[:MAX_LENGTH]
    )


@pytest.mark.parametrize("raw", ["", "   ", "/", "../", "..", "...", f"{RLO}{ZWSP}"])
def test_nothing_displayable_is_refused(raw):
    with pytest.raises(BadFilename):
        display_name(raw)


def test_an_upload_is_stored_under_its_cleaned_name(client: TestClient):
    env = new_environment(client)

    response = upload(client, env, pdfs.pdf("Threads."), f"../{RLO}Week  5.pdf")
    refused = upload(client, env, pdfs.pdf("Other."), "../..")

    assert (response.status_code, response.json()["filename"]) == (201, "Week 5.pdf")
    assert (refused.status_code, refused.json()["detail"]) == (
        422,
        "filename must name a file",
    )
