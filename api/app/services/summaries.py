"""Document summaries: written by the language model, cited, and kept.

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
cited (decision record 08).

Summaries are stored in generated_artifacts and written in the background as
soon as a document is read (decision record 09). Each is identified by what
it was written from: the document's text (source_version), the model and the
prompt versions. The same again finds the existing summary; anything new is
written as a new one, and the old ones are kept.
"""

import hashlib
import logging
import threading
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import prompting
from app.db import SessionFactory
from app.llm import LLMError, LLMProvider
from app.models import Document, DocumentChunk, GeneratedArtifact
from app.schemas import Citation, SummaryPoint, SummaryRead
from app.services import sources

logger = logging.getLogger(__name__)

ARTIFACT_TYPE = "document_summary"
SUMMARY_PROMPT = ("document_summary", "v1")
COMBINE_PROMPT = ("combine_summaries", "v1")

MIN_POINTS, MAX_POINTS = 3, 7
MAX_SOURCES = 4  # passages one key point may cite

# How much passage text one request carries, estimated in tokens at four
# characters each. Real tokenizers fit more characters into a token, so the
# estimate errs on the safe side: 10,000 estimated tokens of passages, plus
# the instructions and the answer, stay within the default 16,384-token
# context.
SECTION_TOKENS = 10_000
CHARS_PER_TOKEN = 4

# The most sections combined into one summary: their notes, about 450 tokens
# each, must fit in the combining request. About 300 dense pages.
MAX_SECTIONS = 20

# How long a summary may be generating before asking again treats it as
# abandoned, by a server restart for example. Longer than documents'
# processing timeout, since a long document takes many model calls.
STALE_GENERATING = timedelta(hours=1)

# Summaries are written one at a time in this process (see write_summary).
_ONE_AT_A_TIME = threading.Lock()


class NotReadyToSummarize(Exception):
    """The document has not been read successfully yet."""


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


@dataclass(frozen=True)
class Plan:
    """What a summary of the document, as it is now, would read and use."""

    chunks: list[DocumentChunk]
    sections: list[list[tuple[int, DocumentChunk]]]
    source_version: str
    prompt_version: str  # every prompt version, in order, comma-separated
    problem: str | None  # why it cannot be written, if it cannot


def plan(session: Session, document: Document) -> Plan:
    """The passages, sections, prompts and fingerprint of a summary of the
    document as it is now. Nothing is written."""
    if document.status != "ready":
        raise NotReadyToSummarize("This document has not been read yet.")
    chunks = list(
        session.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document.id)
            .order_by(DocumentChunk.ordinal)
        )
    )
    sections = _sections(chunks) if chunks else []
    prompts = [SUMMARY_PROMPT] + ([COMBINE_PROMPT] if len(sections) > 1 else [])
    fingerprint = f"{document.sha256}:" + ",".join(str(c.id) for c in chunks)
    problem = None
    if not chunks:
        problem = "This document has no text to summarize."
    elif len(sections) > MAX_SECTIONS:
        problem = (
            f"This document is too long to summarize: it has {len(sections)} "
            f"sections' worth of text, and at most {MAX_SECTIONS} can be combined."
        )
    return Plan(
        chunks=chunks,
        sections=sections,
        source_version=hashlib.sha256(fingerprint.encode()).hexdigest(),
        prompt_version=",".join(f"{name}/{version}" for name, version in prompts),
        problem=problem,
    )


def _find(session: Session, document: Document, plan_: Plan, model: str):
    return session.scalar(
        select(GeneratedArtifact).where(
            GeneratedArtifact.document_id == document.id,
            GeneratedArtifact.artifact_type == ARTIFACT_TYPE,
            GeneratedArtifact.source_version == plan_.source_version,
            GeneratedArtifact.model_name == model,
            GeneratedArtifact.prompt_version == plan_.prompt_version,
        )
    )


def current_summary(
    session: Session, document: Document, llm: LLMProvider
) -> GeneratedArtifact | None:
    """The summary of the document as it is now, by this model with these
    prompts, if one has been asked for."""
    if document.status != "ready":
        return None
    return _find(session, document, plan(session, document), llm.model_name)


def request_summary(
    session: Session, document: Document, llm: LLMProvider
) -> tuple[GeneratedArtifact, bool]:
    """Make sure a summary of the document as it is now exists or is coming.

    Returns the summary's row and whether it must be written now. The same
    document, text, model and prompts always find the same row, so asking
    twice never writes twice. A failed attempt is tried again in its own row;
    so is one abandoned while generating, by a server restart for example. A
    document that cannot be summarized at all gets a failed row with the
    reason, which asking again does not change.
    """
    plan_ = plan(session, document)
    artifact = _find(session, document, plan_, llm.model_name)
    if artifact is None:
        artifact = GeneratedArtifact(
            environment_id=document.environment_id,
            document_id=document.id,
            artifact_type=ARTIFACT_TYPE,
            source_version=plan_.source_version,
            model_name=llm.model_name,
            prompt_version=plan_.prompt_version,
            status="failed" if plan_.problem else "pending",
            error=plan_.problem,
            metadata_json={
                "passages": len(plan_.chunks),
                "sections": len(plan_.sections),
            },
        )
        session.add(artifact)
        try:
            session.commit()
        except IntegrityError:
            # Another request created the same row a moment ago: use that.
            session.rollback()
            return _find(session, document, plan_, llm.model_name), False
        return artifact, plan_.problem is None
    abandoned = (
        artifact.status == "generating"
        and datetime.now(UTC) - artifact.updated_at > STALE_GENERATING
    )
    if (artifact.status == "failed" and plan_.problem is None) or abandoned:
        artifact.status, artifact.error = "pending", None
        session.commit()
        return artifact, True
    return artifact, False


def _compose(
    filename: str,
    sections: list[list[tuple[int, str]]],
    citations: list[Citation],
    llm: LLMProvider,
) -> tuple[dict, float]:
    """Ask the model for the summary: one call per section, then one more to
    combine them if there are several. Returns the content and the seconds
    the model took. Works on plain values, so no database work waits on it."""

    def ask(prompt: tuple[str, str], numbers: Sequence[int], **values):
        rendered = prompting.render(
            *prompt,
            filename=filename,
            min_points=min(MIN_POINTS, len(numbers)),
            max_points=MAX_POINTS,
            **values,
        )
        return llm.generate_structured(rendered, answer_schema(numbers))

    generated = [
        ask(
            SUMMARY_PROMPT,
            [n for n, _ in section],
            passages="\n\n".join(f"[{n}] {text}" for n, text in section),
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
        generated.append(ask(COMBINE_PROMPT, cited, notes=notes))

    final = generated[-1].value
    content = {
        "overview": final.overview,
        "key_points": [
            {
                "text": kp.point,
                "citations": [
                    citations[n - 1].model_dump(mode="json")
                    for n in dict.fromkeys(kp.sources)
                ],
            }
            for kp in final.key_points
        ],
    }
    return content, round(sum(g.seconds for g in generated), 1)


def write_summary(
    session_factory: SessionFactory, artifact_id: uuid.UUID, llm: LLMProvider
) -> None:
    """Write a pending summary. Runs as a background task.

    One summary is written at a time in this process: the model serves one
    request at a time well, and many documents arriving together then queue
    instead of competing for memory. The row is claimed under a lock, the
    model works outside any transaction, and the result is stored under the
    lock again, so a summary always ends ready or failed with a reason.
    """
    with _ONE_AT_A_TIME:
        with session_factory() as session:
            artifact = session.get(GeneratedArtifact, artifact_id, with_for_update=True)
            if artifact is None or artifact.status != "pending":
                return  # written, or taken, by someone else
            document = session.get(Document, artifact.document_id)
            plan_ = plan(session, document) if document.status == "ready" else None
            if (
                plan_ is None
                or plan_.source_version != artifact.source_version
                or plan_.prompt_version != artifact.prompt_version
                or llm.model_name != artifact.model_name
            ):
                artifact.status = "failed"
                artifact.error = "The document changed before this summary was written."
                session.commit()
                return
            filename = document.filename
            sections = [
                [(n, sources.with_heading(chunk)) for n, chunk in section]
                for section in plan_.sections
            ]
            citations = sources.cite_all(session, plan_.chunks)
            artifact.status = "generating"
            session.commit()

        problem, content, seconds = None, None, None
        try:
            content, seconds = _compose(filename, sections, citations, llm)
        except LLMError as exc:
            problem = str(exc)
        except Exception:
            logger.exception("Writing summary %s failed", artifact_id)
            problem = "An unexpected error occurred while writing the summary."

        with session_factory() as session:
            artifact = session.get(GeneratedArtifact, artifact_id, with_for_update=True)
            if artifact is None or artifact.status != "generating":
                return  # its document was deleted meanwhile
            if problem is None:
                artifact.status, artifact.content = "ready", content
                artifact.metadata_json = {**artifact.metadata_json, "seconds": seconds}
            else:
                artifact.status, artifact.error = "failed", problem
            session.commit()


def summarize_when_ready(
    session_factory: SessionFactory, document_id: uuid.UUID, llm: LLMProvider
) -> None:
    """After processing: make sure the document has a summary, and write it if
    it needs writing. Runs as a background task; does nothing for a document
    that did not end up ready."""
    with session_factory() as session:
        document = session.get(Document, document_id)
        if document is None or document.status != "ready":
            return
        artifact, write_now = request_summary(session, document, llm)
        artifact_id = artifact.id
    if write_now:
        write_summary(session_factory, artifact_id, llm)


def history(session: Session, document: Document) -> list[GeneratedArtifact]:
    """Every summary of the document ever asked for, newest first."""
    return list(
        session.scalars(
            select(GeneratedArtifact)
            .where(
                GeneratedArtifact.document_id == document.id,
                GeneratedArtifact.artifact_type == ARTIFACT_TYPE,
            )
            .order_by(GeneratedArtifact.created_at.desc(), GeneratedArtifact.id)
        )
    )


def to_read(artifact: GeneratedArtifact, current: bool) -> SummaryRead:
    """A stored summary as the API shows it."""
    content = artifact.content or {}
    return SummaryRead(
        id=artifact.id,
        document_id=artifact.document_id,
        status=artifact.status,
        error=artifact.error,
        overview=content.get("overview"),
        key_points=[SummaryPoint(**kp) for kp in content.get("key_points", [])],
        model=artifact.model_name,
        prompt_versions=artifact.prompt_version.split(","),
        source_version=artifact.source_version,
        sections=artifact.metadata_json.get("sections"),
        seconds=artifact.metadata_json.get("seconds"),
        current=current,
        created_at=artifact.created_at,
        updated_at=artifact.updated_at,
    )
