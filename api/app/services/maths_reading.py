"""Reading a document's maths with the vision model (decision records 26
and 31).

Purpose
-------
A PDF's text layer keeps the prose but loses the maths: a matrix becomes a
row of numbers, λ² becomes "λ2". The local model can read a page's image
and write it out with its maths in LaTeX, at about a minute a page. Every
page that sets maths in maths fonts is read as part of reading the document
(record 31): its reading job, one step per page, comes after the first
reading of the text, so the text is there to read at once.

Each page is read whole, and if what comes back disagrees with the page's
text layer (app/transcription.py), once more in two halves, each seen
larger. A page that still disagrees keeps its text layer, and the update
says why.

The pages read are kept per version of the file. After the pages, the
document is read again; reading it uses every page read so far in place of
its text layer, and what follows redoes only what changed (record 17). A
reading stopped part way keeps the pages it read, and reading the document
again later reads the rest.
"""

import logging
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import parsing, prompting, storage, transcription
from app.db import SessionFactory
from app.llm import LLMError, LLMProvider
from app.models import Document, DocumentPage, MaterialUpdate, PageTranscription

logger = logging.getLogger(__name__)

PROMPT = ("page_transcription", "v1")
PROMPT_ID = "/".join(PROMPT)  # as Prompt.id writes it

# --- what there is to read ---------------------------------------------------


def _latest(session: Session, document: Document) -> dict[int, PageTranscription]:
    """The reading in use of each page of the document's current file: the
    newest accepted one, or if none was accepted the newest."""
    rows = session.scalars(
        select(PageTranscription).where(
            PageTranscription.document_id == document.id,
            PageTranscription.sha256 == document.sha256,
        )
    )
    ordered = sorted(rows, key=lambda r: (r.status == "accepted", r.created_at))
    return {row.page_number: row for row in ordered}


def not_read(
    session: Session, document: Document, llm: LLMProvider, pages: list[int]
) -> list[int]:
    """Of the pages of the document's file that set maths, those not yet
    read with this model and prompt."""
    done = {
        row.page_number
        for row in session.scalars(
            select(PageTranscription).where(
                PageTranscription.document_id == document.id,
                PageTranscription.sha256 == document.sha256,
                PageTranscription.model == llm.model_name,
                PageTranscription.prompt_version == PROMPT_ID,
            )
        )
    }
    return [p for p in pages if p not in done]


def _current_pages(session: Session, document: Document) -> dict[int, str]:
    """Each page's text as the document holds it now."""
    return {
        page.page_number: page.content
        for page in session.scalars(
            select(DocumentPage).where(DocumentPage.document_id == document.id)
        )
    }


def _waiting(session: Session, document: Document) -> list[int]:
    """Pages read and accepted whose text is not the page's text yet."""
    current = _current_pages(session, document)
    return [
        p
        for p, row in _latest(session, document).items()
        if row.status == "accepted" and current.get(p) != row.content
    ]


# --- reading one page ------------------------------------------------------------


@dataclass(frozen=True)
class _Reading:
    status: str
    page: transcription.PageText | None
    reason: str | None
    attempts: int
    seconds: float


def _read(llm: LLMProvider, path: Path, page_number: int) -> _Reading:
    """Read a page whole, and if that fails its check, again in two halves.
    An LLMError is left to the job, which tries again later."""
    layer = parsing.page_layer(path, page_number)
    prompt = prompting.render(*PROMPT)
    seconds, reason = 0.0, None
    for attempt, halves in enumerate(((None,), ("top", "bottom"))):
        parts = []
        for half in halves:
            answer = llm.transcribe(prompt, parsing.page_image(path, page_number, half))
            seconds += answer.seconds
            parts.append(transcription.without_chatter(answer.value).strip())
        try:
            page = transcription.page_text("\n\n".join(parts), layer)
        except transcription.Unusable as exc:
            reason = str(exc)
            continue
        reason = transcription.check(page, layer).reason
        if reason is None:
            return _Reading("accepted", page, None, attempt + 1, seconds)
    return _Reading("rejected", None, reason, 2, seconds)


def _tally(
    session: Session,
    update_id: uuid.UUID | None,
    page_number: int,
    status: str,
    total: int,
) -> None:
    """Record the page on the update's maths step: which pages were read
    and which kept their text, so far."""
    if update_id is None:
        return
    update = session.get(MaterialUpdate, update_id, with_for_update=True)
    if update is None or update.status != "running":
        return
    steps = []
    for step in update.steps:
        if step["name"] == "maths":
            tally = step.get("result") or {"read": [], "kept": []}
            read, kept = set(tally["read"]), set(tally["kept"])
            (read if status == "accepted" else kept).add(page_number)
            kept -= read
            step = {
                **step,
                "state": "running",
                "detail": (
                    f"Page {page_number}, {len(read) + len(kept)} of {total}: "
                    f"{len(read)} read, {len(kept)} keep the PDF's own text."
                ),
                "result": {"read": sorted(read), "kept": sorted(kept)},
            }
        steps.append(step)
    update.steps = steps


def transcribe_page(
    session_factory: SessionFactory,
    document_id: uuid.UUID,
    page_number: int,
    llm: LLMProvider,
    update_id: uuid.UUID | None = None,
    total: int = 1,
) -> str | None:
    """A job step: read one page's maths, unless this model has read it for
    this version of the file already. Returns accepted or rejected, or None
    if the document is gone or being read meanwhile."""
    with session_factory() as session:
        document = session.get(Document, document_id)
        if document is None or document.status != "ready":
            return None
        sha256 = document.sha256
        path = storage.document_path(document.environment_id, document.id)
        known = session.scalar(
            select(PageTranscription).where(
                PageTranscription.document_id == document_id,
                PageTranscription.sha256 == sha256,
                PageTranscription.page_number == page_number,
                PageTranscription.model == llm.model_name,
                PageTranscription.prompt_version == PROMPT_ID,
            )
        )
        status = known.status if known is not None else None

    if status is None:
        try:
            reading = _read(llm, path, page_number)
        except LLMError as exc:
            with session_factory() as session:
                update = (
                    session.get(MaterialUpdate, update_id, with_for_update=True)
                    if update_id
                    else None
                )
                if update is not None and update.status == "running":
                    update.steps = [
                        {**s, "state": "failed", "detail": str(exc)}
                        if s["name"] == "maths"
                        else s
                        for s in update.steps
                    ]
                    session.commit()
            raise
        except parsing.ParseError:
            return None  # the file went away meanwhile
        status = reading.status
        with session_factory() as session:
            session.add(
                PageTranscription(
                    document_id=document_id,
                    sha256=sha256,
                    page_number=page_number,
                    status=reading.status,
                    content=reading.page.text if reading.page else None,
                    blocks=(
                        [[b.start, b.end, b.is_heading] for b in reading.page.blocks]
                        if reading.page
                        else None
                    ),
                    reason=reading.reason,
                    attempts=reading.attempts,
                    model=llm.model_name,
                    prompt_version=PROMPT_ID,
                    seconds=reading.seconds,
                )
            )
            try:
                session.commit()
            except IntegrityError:
                session.rollback()  # read at the same moment by another job
        logger.info(
            "Page %s %s",
            page_number,
            reading.status,
            extra={"page": page_number, "reason": reading.reason},
        )

    with session_factory() as session:
        _tally(session, update_id, page_number, status, total)
        session.commit()
    return status


# --- putting the pages in place -------------------------------------------------


def apply(
    session_factory: SessionFactory, document_id: uuid.UUID, found: int = 0
) -> dict | None:
    """A step of reading the document again after its maths was read: put
    it back in the queue to be read if any page read differs from the
    page's text now. Returns the pages read and kept, for the update, and
    how many of the found were not read at all, as when the reading was
    stopped; None if the document is gone."""
    with session_factory() as session:
        document = session.get(
            Document, document_id, with_for_update=True, populate_existing=True
        )
        if document is None:
            return None
        latest = _latest(session, document)
        changed = _waiting(session, document)
        if changed and document.status == "ready":
            document.status = "uploaded"
            document.error = None
        session.commit()
        return {
            "read": sorted(p for p, r in latest.items() if r.status == "accepted"),
            "kept": {
                str(p): r.reason
                for p, r in sorted(latest.items())
                if r.status == "rejected"
            },
            "not_read": max(0, found - len(latest)),
            "changed": len(changed),
        }


def with_transcriptions(
    session: Session, document: Document, parsed: parsing.ParsedDocument
) -> parsing.ParsedDocument:
    """The parsed document with each page whose maths was read, and
    accepted, in its read form."""
    accepted = {
        p: row
        for p, row in _latest(session, document).items()
        if row.status == "accepted" and row.content is not None
    }
    if not accepted:
        return parsed
    pages = [
        parsing.ParsedPage(
            number=page.number,
            text=accepted[page.number].content or "",
            blocks=tuple(
                parsing.ParsedBlock(start, end, bool(heading))
                for start, end, heading in accepted[page.number].blocks or []
            ),
        )
        if page.number in accepted
        else page
        for page in parsed.pages
    ]
    return parsing.ParsedDocument(pages=pages, repaired=parsed.repaired)
