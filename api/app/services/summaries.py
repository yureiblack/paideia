"""A concise, cited summary of one document, written by the language model.

Purpose
-------
The model is given the document's passages, numbered [1], [2] and so on in
reading order, and asked for an overview and a few key points, each citing
the numbers of the passages it rests on. The numbers are short and easy for a
model to copy, unlike chunk ids, and the answer's shape only allows numbers
it was actually given. Each number is then turned back into its passage's
Citation, the same object search results carry (decision record 07).

A document that fits one request is summarized in one call. A longer one is
cut into sections that each fit, every section is summarized on its own,
keeping the document-wide passage numbers, and one more call combines the
sections' notes into the summary of the whole, citing only numbers the notes
cited. On request, at most MAX_SECTIONS sections are summarized; a longer
document is refused with the reason (decision record 08).

Nothing is stored yet; each request generates a fresh summary.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import prompting
from app.llm import LLMProvider
from app.models import Document, DocumentChunk
from app.schemas import DocumentSummary, SummaryPoint
from app.services import sources

MIN_POINTS, MAX_POINTS = 3, 7
MAX_SOURCES = 4  # passages one key point may cite

# How much passage text one request carries, estimated in tokens at four
# characters each. Real tokenizers fit more characters into a token, so the
# estimate errs on the safe side: 10,000 estimated tokens of passages, plus
# the instructions and the answer, stay within the default 16,384-token
# context.
SECTION_TOKENS = 10_000
CHARS_PER_TOKEN = 4
MAX_SECTIONS = 4


class NotReadyToSummarize(Exception):
    """The document has not been read successfully yet."""


class CannotSummarize(Exception):
    """The document cannot be summarized: no text, or too long for a request."""


def answer_schema(numbers: Sequence[int]) -> type[BaseModel]:
    """The shape the model must answer in, allowing only the given passage
    numbers. Ollama constrains generation to this shape, so a number the model
    was not given cannot be written at all; validation checks it again.

    A run of consecutive numbers becomes a range, any other set a list of
    allowed values. Every list has a limit, without which a constrained model
    can keep writing until its context is full.
    """
    if list(numbers) == list(range(numbers[0], numbers[-1] + 1)):
        Number = Annotated[int, Field(ge=numbers[0], le=numbers[-1])]
    else:
        Number = Literal[tuple(numbers)]

    class KeyPoint(BaseModel):
        point: str
        sources: list[Number] = Field(min_length=1, max_length=MAX_SOURCES)

    class Answer(BaseModel):
        overview: str
        key_points: list[KeyPoint] = Field(
            min_length=min(MIN_POINTS, len(numbers)), max_length=MAX_POINTS
        )

    return Answer


def _passages(numbered: Sequence[tuple[int, DocumentChunk]]) -> str:
    return "\n\n".join(f"[{n}] {sources.with_heading(c)}" for n, c in numbered)


def _sections(chunks: Sequence[DocumentChunk]) -> list[list[tuple[int, DocumentChunk]]]:
    """The chunks, numbered from 1, cut into runs that each fit one request."""
    sections: list[list[tuple[int, DocumentChunk]]] = [[]]
    size = 0
    for number, chunk in enumerate(chunks, start=1):
        tokens = len(sources.with_heading(chunk)) // CHARS_PER_TOKEN + 1
        if sections[-1] and size + tokens > SECTION_TOKENS:
            sections.append([])
            size = 0
        sections[-1].append((number, chunk))
        size += tokens
    return sections


def _points_text(answer) -> str:
    return "\n".join(
        f"- {kp.point} [{', '.join(map(str, kp.sources))}]" for kp in answer.key_points
    )


def summarize_document(
    session: Session, document: Document, llm: LLMProvider
) -> DocumentSummary:
    """A fresh summary of the document, every key point cited."""
    if document.status != "ready":
        raise NotReadyToSummarize("This document has not been read yet.")
    chunks = list(
        session.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document.id)
            .order_by(DocumentChunk.ordinal)
        )
    )
    if not chunks:
        raise CannotSummarize("This document has no text to summarize.")
    sections = _sections(chunks)
    if len(sections) > MAX_SECTIONS:
        raise CannotSummarize(
            f"This document is too long to summarize on request: it has "
            f"{len(sections)} sections' worth of text, and at most {MAX_SECTIONS} "
            "can be summarized at once."
        )

    def ask(name: str, numbers: Sequence[int], **values):
        prompt = prompting.render(
            name,
            "v1",
            filename=document.filename,
            min_points=min(MIN_POINTS, len(numbers)),
            max_points=MAX_POINTS,
            **values,
        )
        return llm.generate_structured(prompt, answer_schema(numbers))

    generated = [
        ask(
            "document_summary",
            [n for n, _ in section],
            passages=_passages(section),
        )
        for section in sections
    ]
    if len(sections) > 1:
        notes = "\n\n".join(
            f"Section {i} (passages {s[0][0]} to {s[-1][0]})\n"
            f"Overview: {g.value.overview}\nKey points:\n{_points_text(g.value)}"
            for i, (s, g) in enumerate(zip(sections, generated, strict=True), start=1)
        )
        cited = sorted(
            {n for g in generated for kp in g.value.key_points for n in kp.sources}
        )
        generated.append(ask("combine_summaries", cited, notes=notes))

    final = generated[-1].value
    citations = sources.cite_all(session, chunks)  # citations[n - 1] is passage n
    return DocumentSummary(
        document_id=document.id,
        overview=final.overview,
        key_points=[
            SummaryPoint(
                text=kp.point,
                citations=[citations[n - 1] for n in dict.fromkeys(kp.sources)],
            )
            for kp in final.key_points
        ],
        model=generated[-1].model,
        prompt_versions=list(dict.fromkeys(g.prompt_version for g in generated)),
        sections=len(sections),
        seconds=round(sum(g.seconds for g in generated), 1),
        generated_at=datetime.now(UTC),
    )
