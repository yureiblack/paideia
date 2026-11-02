"""Tests for app/chunking.py: parsed pages in, deterministic chunks out.

Purpose: prove the rules in the module's docstring on hand-built documents,
where every boundary is known exactly. No PDFs, no database.
"""

import uuid

import pytest

from app.chunking import MAX_CHARS, TARGET_CHARS, chunk_document, passage
from app.parsing import ParsedDocument, ParsedPage
from tests.parsed import H, P, document, words

DOC = uuid.UUID("00000000-0000-0000-0000-000000000001")


# --- determinism and identity -----------------------------------------------


def test_the_same_document_gives_the_same_chunks_every_time():
    parsed = document([H("Title"), P(words(500)), P(words(500))], [P(words(900))])

    assert chunk_document(DOC, parsed) == chunk_document(DOC, parsed)


def test_ids_belong_to_the_document_but_hashes_only_to_the_text():
    parsed = document([P("Same text in two documents.")])
    other = uuid.UUID("00000000-0000-0000-0000-000000000002")

    [a], [b] = chunk_document(DOC, parsed), chunk_document(other, parsed)

    assert a.id != b.id
    assert a.content_hash == b.content_hash


def test_repeated_paragraphs_get_distinct_ids():
    repeated = words(900, "again")
    chunks = chunk_document(DOC, document([P(repeated)], [P(repeated)]))

    assert len(chunks) == 2
    assert chunks[0].content_hash == chunks[1].content_hash
    assert chunks[0].id != chunks[1].id


def test_editing_one_section_leaves_other_sections_ids_alone():
    before = document([H("A"), P(words(300, "alpha"))], [H("B"), P(words(300, "beta"))])
    after = document([H("A"), P(words(300, "gamma"))], [H("B"), P(words(300, "beta"))])

    old, new = chunk_document(DOC, before), chunk_document(DOC, after)

    assert old[0].id != new[0].id
    assert old[1].id == new[1].id


def test_ordinals_count_from_zero():
    chunks = chunk_document(
        DOC, document([H("A"), P("x."), H("B"), P("y."), H("C"), P("z.")])
    )

    assert [chunk.ordinal for chunk in chunks] == [0, 1, 2]


# --- packing and sizes ------------------------------------------------------


def test_short_paragraphs_are_packed_until_the_target():
    parsed = document([P(words(300, f"p{n}")) for n in range(6)])

    chunks = chunk_document(DOC, parsed)

    assert len(chunks) == 2  # three 300-character paragraphs pass the 800 target
    assert all(TARGET_CHARS <= len(chunk.content) <= MAX_CHARS for chunk in chunks)


def test_no_chunk_exceeds_the_maximum():
    parsed = document([P(words(n * 97 % 1100 + 50, f"w{n}")) for n in range(40)])

    assert all(len(chunk.content) <= MAX_CHARS for chunk in chunk_document(DOC, parsed))


def test_a_long_paragraph_is_split_at_sentence_ends():
    sentences = " ".join(
        f"Sentence number {n} talks about processes." for n in range(80)
    )
    chunks = chunk_document(DOC, document([P(sentences)]))

    assert len(chunks) > 1
    assert all(len(chunk.content) <= MAX_CHARS for chunk in chunks)
    assert all(chunk.content.endswith("processes.") for chunk in chunks)


def test_a_sentence_longer_than_the_maximum_is_cut_at_a_space():
    chunks = chunk_document(DOC, document([P(words(3000))]))

    assert all(len(chunk.content) <= MAX_CHARS for chunk in chunks)
    assert all(not chunk.content.startswith(" ") for chunk in chunks)
    assert "".join(c.content.replace(" ", "") for c in chunks) == words(3000).replace(
        " ", ""
    )


# --- headings ---------------------------------------------------------------


def test_every_heading_starts_a_chunk_and_names_it():
    parsed = document(
        [
            H("3.1 States"),
            P("Ready and running."),
            H("3.2 Scheduling"),
            P("Round robin."),
        ]
    )

    chunks = chunk_document(DOC, parsed)

    assert [chunk.content for chunk in chunks] == [
        "3.1 States\n\nReady and running.",
        "3.2 Scheduling\n\nRound robin.",
    ]
    assert [chunk.heading for chunk in chunks] == ["3.1 States", "3.2 Scheduling"]


def test_consecutive_headings_stay_with_the_paragraph_after_them():
    chunks = chunk_document(
        DOC, document([H("Chapter 3"), H("3.1 States"), P("Ready.")])
    )

    assert [chunk.content for chunk in chunks] == ["Chapter 3\n\n3.1 States\n\nReady."]
    assert chunks[0].heading == "3.1 States"


def test_chunks_after_a_heading_keep_its_name_until_the_next():
    parsed = document([H("Long section")] + [P(words(700, f"p{n}")) for n in range(3)])

    chunks = chunk_document(DOC, parsed)

    assert len(chunks) == 3
    assert {chunk.heading for chunk in chunks} == {"Long section"}


def test_text_before_any_heading_has_no_heading():
    chunks = chunk_document(DOC, document([P("Preface."), H("One"), P("Body.")]))

    assert chunks[0].heading is None


# --- positions --------------------------------------------------------------


def test_a_chunk_can_continue_across_a_page_break():
    parsed = document([P(words(400, "end"))], [P(words(300, "start"))])

    [chunk] = chunk_document(DOC, parsed)

    assert (chunk.page_start, chunk.page_end) == (1, 2)
    assert chunk.content.startswith("end") and chunk.content.endswith("start.")


@pytest.mark.parametrize("seed", range(5))
def test_offsets_rebuild_every_chunk_exactly(seed: int):
    pages = [
        [H(f"Heading {p}")]
        + [P(words((p * 7 + n * 13 + seed) % 900 + 40, f"t{p}{n}")) for n in range(5)]
        for p in range(6)
    ]
    pages.insert(3, [])  # a page with no text in the middle
    parsed = document(*pages)

    for chunk in chunk_document(DOC, parsed):
        rebuilt = passage(
            parsed.pages,
            chunk.page_start,
            chunk.char_start,
            chunk.page_end,
            chunk.char_end,
        )
        assert rebuilt == chunk.content


def test_a_page_without_block_information_is_one_paragraph():
    parsed = ParsedDocument(
        pages=[ParsedPage(1, "  Plain text from a simple parser.  ")], repaired=False
    )

    [chunk] = chunk_document(DOC, parsed)

    assert chunk.content == "Plain text from a simple parser."


def test_a_document_without_text_has_no_chunks():
    assert chunk_document(DOC, document([], [])) == []
