"""Cutting a document's text into chunks for search, citation and embedding.

Purpose
-------
A chunk is a passage of a few paragraphs: small enough to be a precise search
result and to fit a local embedding model, large enough to carry meaning on
its own. This module is a pure function from parsed pages to chunks. It knows
nothing about databases, files or PDFs, which is what makes its determinism
easy to prove: the same pages always produce the same chunks, ids included.

The rules (decision record 04):
- Whole paragraphs are packed into a chunk until it reaches TARGET_CHARS, and
  a chunk never exceeds MAX_CHARS.
- Every heading starts a new chunk, and opens it. Consecutive headings stay
  together with the paragraph that follows them.
- A paragraph longer than MAX_CHARS is split at sentence ends; a single
  sentence longer than that, at a space.
- Chunks do not overlap.
- Each chunk records where it starts and ends, as (page, character offset)
  into the stored page text, so its exact passage can always be found again.
- A chunk's id is a UUID derived from its document, its content hash and which
  occurrence of that content it is. Identical text in the same document always
  gets the same id, so a reprocess never duplicates chunks, and a paragraph
  repeated within one document still gets distinct ids.
"""

import hashlib
import re
import uuid
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass

from app.parsing import PARAGRAPH_BREAK, ParsedDocument, ParsedPage

TARGET_CHARS = 800
MAX_CHARS = 1200

# Chosen once, at random. Every chunk id is derived from it, so changing it
# would change every chunk id in every database.
CHUNK_NAMESPACE = uuid.UUID("7c1f4e2a-9b3d-4f6a-8e5c-2d9a0b7f3c61")

# The end of a sentence: . ! or ? possibly followed by closing quotes or
# brackets, then whitespace.
_SENTENCE_END = re.compile(r"[.!?][\"')\]]*\s+")


@dataclass(frozen=True)
class Chunk:
    id: uuid.UUID
    ordinal: int  # position in the document, from 0
    page_start: int
    char_start: int  # offset into page_start's text
    page_end: int
    char_end: int  # offset into page_end's text, exclusive
    heading: str | None  # the nearest heading above this chunk, if any
    content: str
    content_hash: str  # SHA-256 of the content with whitespace normalised


@dataclass(frozen=True)
class _Piece:
    """A paragraph, or part of a long one, located in its page's text."""

    page: int
    start: int
    end: int
    text: str
    is_heading: bool


def chunk_document(document_id: uuid.UUID, parsed: ParsedDocument) -> list[Chunk]:
    """Cut a parsed document into chunks. Deterministic."""
    chunks: list[Chunk] = []
    occurrences: Counter[str] = Counter()
    for ordinal, (heading, pieces) in enumerate(_group(_pieces(parsed.pages))):
        first, last = pieces[0], pieces[-1]
        content = passage(parsed.pages, first.page, first.start, last.page, last.end)
        content_hash = hashlib.sha256(" ".join(content.split()).encode()).hexdigest()
        occurrence = occurrences[content_hash]
        occurrences[content_hash] += 1
        chunks.append(
            Chunk(
                id=uuid.uuid5(
                    CHUNK_NAMESPACE, f"{document_id}:{content_hash}:{occurrence}"
                ),
                ordinal=ordinal,
                page_start=first.page,
                char_start=first.start,
                page_end=last.page,
                char_end=last.end,
                heading=heading,
                content=content,
                content_hash=content_hash,
            )
        )
    return chunks


def passage(
    pages: list[ParsedPage],
    page_start: int,
    char_start: int,
    page_end: int,
    char_end: int,
) -> str:
    """The exact text between two (page, offset) positions.

    Pages are joined with the same blank line that separates paragraphs, and
    pages without text are skipped. Chunk contents are built with this, so a
    chunk's text can always be rebuilt from its stored offsets.
    """
    by_number = {page.number: page.text for page in pages}
    if page_start == page_end:
        return by_number[page_start][char_start:char_end]
    parts = [by_number[page_start][char_start:]]
    parts += [by_number[n] for n in range(page_start + 1, page_end) if by_number[n]]
    parts.append(by_number[page_end][:char_end])
    return PARAGRAPH_BREAK.join(parts)


def _pieces(pages: list[ParsedPage]) -> Iterator[_Piece]:
    for page in pages:
        blocks = page.blocks
        if not blocks and page.text.strip():
            # A parser that cannot tell paragraphs apart: the page is one.
            stripped = page.text.strip()
            start = page.text.index(stripped)
            blocks = ((start, start + len(stripped), False),)
        else:
            blocks = tuple((b.start, b.end, b.is_heading) for b in blocks)
        for start, end, is_heading in blocks:
            if is_heading or end - start <= MAX_CHARS:
                yield _Piece(page.number, start, end, page.text[start:end], is_heading)
                continue
            for a, b in _split_long(page.text[start:end]):
                yield _Piece(
                    page.number,
                    start + a,
                    start + b,
                    page.text[start + a : start + b],
                    False,
                )


def _split_long(text: str) -> Iterator[tuple[int, int]]:
    """Split an over-long paragraph into ranges of at most MAX_CHARS.

    Sentences are packed greedily; a sentence longer than MAX_CHARS is cut at
    the last space that fits, or hard at MAX_CHARS if it has no space at all.
    Ranges never start or end with whitespace.
    """
    sentences, start = [], 0
    for match in _SENTENCE_END.finditer(text):
        sentences.append((start, match.end()))
        start = match.end()
    if start < len(text):
        sentences.append((start, len(text)))

    current: tuple[int, int] | None = None
    for a, b in sentences:
        if current and b - current[0] <= MAX_CHARS:
            current = (current[0], b)
            continue
        if current:
            yield _trimmed(text, *current)
        while b - a > MAX_CHARS:
            cut = text.rfind(" ", a, a + MAX_CHARS)
            cut = cut if cut > a else a + MAX_CHARS
            yield _trimmed(text, a, cut)
            a = cut
        current = (a, b)
    if current:
        yield _trimmed(text, *current)


def _trimmed(text: str, a: int, b: int) -> tuple[int, int]:
    while a < b and text[a].isspace():
        a += 1
    while b > a and text[b - 1].isspace():
        b -= 1
    return a, b


def _group(pieces: Iterator[_Piece]) -> Iterator[tuple[str | None, list[_Piece]]]:
    """Pack pieces into chunks, starting a new chunk at every heading."""
    current: list[_Piece] = []
    size = 0
    heading: str | None = None

    for piece in pieces:
        has_body = any(not p.is_heading for p in current)
        if piece.is_heading:
            if has_body:
                yield heading, current
                current, size = [], 0
            heading = piece.text
        elif has_body and size + len(PARAGRAPH_BREAK) + len(piece.text) > MAX_CHARS:
            yield heading, current
            current, size = [], 0

        size += (len(PARAGRAPH_BREAK) if current else 0) + len(piece.text)
        current.append(piece)
        if not piece.is_heading and size >= TARGET_CHARS:
            yield heading, current
            current, size = [], 0

    if current:
        yield heading, current
