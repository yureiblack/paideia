"""Reading a document's figures with the vision model (decision record 29).

Purpose
-------
A figure's text layer is its tick labels and cells, out of order, and
nothing of what it draws. The local model can look at the figure and say
what it shows, at about a quarter of a minute a figure. Like reading maths
(record 26) it is never done unasked: the Materials tab offers it for a
range of pages, with how many figures there are and how long it should take.

A reading is a job on the model lane, one step per figure, so it shows its
progress and can be cancelled between figures. Each figure is read once and,
if its reading disagrees with the figure's own text (app/figure_reading.py),
once more. A figure that still disagrees keeps the PDF's text, and the
document says why.

Readings are kept per version of the file. The reading's last step puts the
document back in the queue to be read; reading it puts each accepted figure
in its page (with_figures), in place of the text-layer blocks inside it,
caption included, as one paragraph that becomes a passage of its own. Search
finds it; summaries and concepts are written from the other passages only,
so nothing written as knowledge rests on the model's description.
"""

import json
import logging
import statistics
import uuid
from dataclasses import dataclass
from pathlib import Path

import pymupdf
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import figure_reading, ocr, parsing, prompting, storage
from app.db import SessionFactory
from app.llm import LLMError, LLMProvider
from app.models import Document, DocumentPage, FigureReading, MaterialUpdate

logger = logging.getLogger(__name__)

PROMPT = ("figure_reading", "v1")
PROMPT_ID = "/".join(PROMPT)

# Seconds a figure takes before this machine has read any: on an Apple M3
# Pro, 12 figures of a textbook took 12 to 44 s, about 15 s typically.
DEFAULT_SECONDS_PER_FIGURE = 20.0
ESTIMATE_FROM = 50


class NothingToRead(Exception):
    """The request names no figure that is still to be read."""


# --- figures as stored ------------------------------------------------------------


def as_figure(row: FigureReading) -> parsing.Figure:
    return parsing.Figure(
        page=row.page_number,
        rect=tuple(row.rect),
        caption=row.caption,
        caption_rect=tuple(row.caption_rect) if row.caption_rect else None,
    )


def as_reading(row: FigureReading) -> figure_reading.Reading:
    return figure_reading.Reading(
        kind=row.kind or "figure",
        text=tuple(row.text or ()),
        tables=tuple(
            figure_reading.Table(t.get("title"), tuple(tuple(r) for r in t["rows"]))
            for t in row.tables or ()
        ),
        description=row.description or "",
    )


def name(figure: parsing.Figure) -> str:
    """How the book names the figure, "Figure 2.11" or "Table 3", else "a figure"."""
    found = parsing.CAPTION.match(figure.caption or "")
    if not found:
        return "a figure"
    return f"{found.group(1).capitalize()} {found.group(2)}"


def encode(figure: parsing.Figure) -> str:
    """A figure as a job step's argument, so the step need not find it again."""
    return json.dumps(
        {
            "page": figure.page,
            "rect": list(figure.rect),
            "caption": figure.caption,
            "caption_rect": list(figure.caption_rect) if figure.caption_rect else None,
        }
    )


def decode(value: str) -> parsing.Figure:
    data = json.loads(value)
    return parsing.Figure(
        page=data["page"],
        rect=tuple(data["rect"]),
        caption=data["caption"],
        caption_rect=tuple(data["caption_rect"]) if data["caption_rect"] else None,
    )


# --- what there is to read ---------------------------------------------------


@dataclass(frozen=True)
class Overview:
    figures: list[parsing.Figure]
    read: list[str]  # keys of figures read and in place
    waiting: list[str]  # read and accepted, not in place yet
    kept: dict[str, str]  # key -> why it kept the PDF's text
    seconds_per_figure: float


def _latest(session: Session, document: Document) -> dict[str, FigureReading]:
    """The reading in use of each figure of the document's current file: the
    newest accepted one, or if none was accepted the newest."""
    rows = session.scalars(
        select(FigureReading).where(
            FigureReading.document_id == document.id,
            FigureReading.sha256 == document.sha256,
        )
    )
    ordered = sorted(rows, key=lambda r: (r.status == "accepted", r.created_at))
    return {row.figure_key: row for row in ordered}


def _in_place(session: Session, document: Document) -> set[str]:
    """The figure readings the document's pages hold now."""
    placed: set[str] = set()
    for figures in session.scalars(
        select(DocumentPage.figures).where(DocumentPage.document_id == document.id)
    ):
        placed.update(f["id"] for f in figures or ())
    return placed


def seconds_per_figure(session: Session) -> float:
    recent = list(
        session.scalars(
            select(FigureReading.seconds)
            .order_by(FigureReading.created_at.desc())
            .limit(ESTIMATE_FROM)
        )
    )
    return statistics.median(recent) if recent else DEFAULT_SECONDS_PER_FIGURE


def overview(session: Session, document: Document) -> Overview:
    """The document's figures and how far their reading has got. Opens the
    file: a textbook of 450 pages takes a few seconds."""
    path = storage.document_path(document.environment_id, document.id)
    latest = _latest(session, document)
    placed = _in_place(session, document)
    accepted = {k: r for k, r in latest.items() if r.status == "accepted"}
    return Overview(
        figures=parsing.figures(path),
        read=sorted(k for k, r in accepted.items() if str(r.id) in placed),
        waiting=sorted(k for k, r in accepted.items() if str(r.id) not in placed),
        kept={k: r.reason or "" for k, r in latest.items() if r.status == "rejected"},
        seconds_per_figure=seconds_per_figure(session),
    )


def _waiting(session: Session, document: Document, first: int, last: int) -> list[str]:
    placed = _in_place(session, document)
    return [
        key
        for key, row in _latest(session, document).items()
        if first <= row.page_number <= last
        and row.status == "accepted"
        and str(row.id) not in placed
    ]


def to_read(
    session: Session, document: Document, llm: LLMProvider, first: int, last: int
) -> list[parsing.Figure]:
    """The figures on pages first to last not yet read with this model and
    prompt. Raises NothingToRead if there are none and nothing read before
    is waiting to be put in place."""
    path = storage.document_path(document.environment_id, document.id)
    wanted = [f for f in parsing.figures(path) if first <= f.page <= last]
    done = set(
        session.scalars(
            select(FigureReading.figure_key).where(
                FigureReading.document_id == document.id,
                FigureReading.sha256 == document.sha256,
                FigureReading.model == llm.model_name,
                FigureReading.prompt_version == PROMPT_ID,
            )
        )
    )
    figures = [f for f in wanted if f.key not in done]
    if not figures and not _waiting(session, document, first, last):
        raise NothingToRead(
            "The figures of these pages have been read already."
            if wanted
            else "These pages have no figures to read."
        )
    return figures


# --- reading one figure ---------------------------------------------------------


@dataclass(frozen=True)
class _Outcome:
    status: str
    reading: figure_reading.Reading | None
    reason: str | None
    attempts: int
    seconds: float


def own_text(path: Path, figure: parsing.Figure, image: bytes) -> str:
    """Everything the figure is known to show: the PDF's text inside it, its
    caption, and Tesseract's reading of its picture."""
    return "\n".join(
        [
            parsing.figure_text(path, figure),
            figure.caption or "",
            ocr.picture_text(image),
        ]
    )


def _read(llm: LLMProvider, path: Path, figure: parsing.Figure) -> _Outcome:
    """Read a figure, and if its reading disagrees with the figure's own
    text, once more. An LLMError is left to the job, which tries again."""
    image = parsing.figure_image(path, figure)
    own = own_text(path, figure, image)
    # A table's reading must give most of the numbers its PDF text sets.
    table = parsing.figure_text(path, figure) if figure.is_table else None
    prompt = prompting.render(*PROMPT)
    seconds, reason = 0.0, None
    for attempt, again in enumerate((False, True)):
        answer = llm.transcribe(prompt, image, again=again)
        seconds += answer.seconds
        try:
            reading = figure_reading.parse(answer.value, figure.caption)
        except figure_reading.Unusable as exc:
            reason = str(exc)
            continue
        reason = figure_reading.check(reading, own, table)
        if reason is None:
            return _Outcome("accepted", reading, None, attempt + 1, seconds)
    return _Outcome("rejected", None, reason, 2, seconds)


def _tally(
    session: Session, update_id: uuid.UUID | None, key: str, status: str, total: int
) -> None:
    """Record the figure on the update's figures step, so far."""
    if update_id is None:
        return
    update = session.get(MaterialUpdate, update_id, with_for_update=True)
    if update is None or update.status != "running":
        return
    steps = []
    for step in update.steps:
        if step["name"] == "figures":
            tally = step.get("result") or {"read": [], "kept": []}
            read, kept = set(tally["read"]), set(tally["kept"])
            (read if status == "accepted" else kept).add(key)
            kept -= read
            step = {
                **step,
                "state": "running",
                "detail": (
                    f"{len(read) + len(kept)} of {total}: {len(read)} read, "
                    f"{len(kept)} keep the PDF's own text."
                ),
                "result": {"read": sorted(read), "kept": sorted(kept)},
            }
        steps.append(step)
    update.steps = steps


def read_figure(
    session_factory: SessionFactory,
    document_id: uuid.UUID,
    figure: parsing.Figure,
    llm: LLMProvider,
    update_id: uuid.UUID | None = None,
    total: int = 1,
) -> str | None:
    """A job step: read one figure, unless this model has read it for this
    version of the file already. Returns accepted or rejected, or None if
    the document is gone or being read meanwhile."""
    with session_factory() as session:
        document = session.get(Document, document_id)
        if document is None or document.status != "ready":
            return None
        sha256 = document.sha256
        path = storage.document_path(document.environment_id, document.id)
        known = session.scalar(
            select(FigureReading.status).where(
                FigureReading.document_id == document_id,
                FigureReading.sha256 == sha256,
                FigureReading.figure_key == figure.key,
                FigureReading.model == llm.model_name,
                FigureReading.prompt_version == PROMPT_ID,
            )
        )
    status = known

    if status is None:
        try:
            outcome = _read(llm, path, figure)
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
                        if s["name"] == "figures"
                        else s
                        for s in update.steps
                    ]
                    session.commit()
            raise
        except parsing.ParseError:
            return None  # the file went away meanwhile
        status = outcome.status
        reading = outcome.reading
        with session_factory() as session:
            session.add(
                FigureReading(
                    document_id=document_id,
                    sha256=sha256,
                    page_number=figure.page,
                    figure_key=figure.key,
                    rect=list(figure.rect),
                    caption=figure.caption,
                    caption_rect=list(figure.caption_rect)
                    if figure.caption_rect
                    else None,
                    status=outcome.status,
                    kind=reading.kind if reading else None,
                    text=list(reading.text) if reading else None,
                    tables=(
                        [
                            {"title": t.title, "rows": [list(r) for r in t.rows]}
                            for t in reading.tables
                        ]
                        if reading
                        else None
                    ),
                    description=reading.description if reading else None,
                    reason=outcome.reason,
                    attempts=outcome.attempts,
                    model=llm.model_name,
                    prompt_version=PROMPT_ID,
                    seconds=outcome.seconds,
                )
            )
            try:
                session.commit()
            except IntegrityError:
                session.rollback()  # read at the same moment by another job
        logger.info(
            "Figure %s %s",
            figure.key,
            outcome.status,
            extra={"figure": figure.key, "reason": outcome.reason},
        )

    with session_factory() as session:
        _tally(session, update_id, figure.key, status, total)
        session.commit()
    return status


# --- putting the figures in place -----------------------------------------------


def apply(
    session_factory: SessionFactory, document_id: uuid.UUID, first: int, last: int
) -> dict | None:
    """The reading's last step: put the document back in the queue to be
    read if a figure read is not in place yet. Returns the figures from
    first to last read and kept, for the update; None if the document is
    gone."""
    with session_factory() as session:
        document = session.get(
            Document, document_id, with_for_update=True, populate_existing=True
        )
        if document is None:
            return None
        latest = _latest(session, document)
        in_range = {k: r for k, r in latest.items() if first <= r.page_number <= last}
        changed = _waiting(session, document, first, last)
        if changed and document.status == "ready":
            document.status = "uploaded"
            document.error = None
        session.commit()
        return {
            "read": sorted(k for k, r in in_range.items() if r.status == "accepted"),
            "kept": {
                k: r.reason
                for k, r in sorted(in_range.items())
                if r.status == "rejected"
            },
            "changed": len(changed),
        }


def _centre(box: tuple[float, float, float, float]) -> pymupdf.Point:
    return pymupdf.Point((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


def _signature(text: str) -> str:
    return "".join(c for c in text.lower() if c.isalnum())


def _place(page: parsing.ParsedPage, rows: list[FigureReading]) -> parsing.ParsedPage:
    """The page with each figure read in place of the blocks inside it and
    its caption, or failing those where its caption or its height puts it."""
    pieces: list[tuple[str, parsing.ParsedBlock]] = [
        (page.text[b.start : b.end], b) for b in page.blocks
    ]
    if not pieces and page.text.strip():
        pieces = [(page.text.strip(), parsing.ParsedBlock(0, 0, False))]
    for row in sorted(rows, key=lambda r: (r.rect[1], r.rect[0])):
        figure = as_figure(row)
        crop = pymupdf.Rect(figure.crop) + (-2, -2, 2, 2)
        reading = as_reading(row)
        caption_area = (
            pymupdf.Rect(figure.caption_rect) + (-2, -2, 2, 2)
            if figure.caption_rect
            else None
        )
        # The text inside the figure gives way to the reading only where the
        # reading repeats it: what the model left out stays in the page. The
        # caption always does, as the figure's passage begins with it.
        inside = [
            i
            for i, (text, b) in enumerate(pieces)
            if b.box is not None
            and b.figure is None
            and _centre(b.box) in crop
            and (
                (caption_area is not None and _centre(b.box) in caption_area)
                or figure_reading.repeats(reading, text)
            )
        ]
        within = [
            i
            for i, (_, b) in enumerate(pieces)
            if b.box is not None and b.figure is None and _centre(b.box) in crop
        ]
        caption = _signature(figure.caption or "")[:40]
        if within:
            at = within[0]
        elif caption and (
            found := [
                i
                for i, (text, b) in enumerate(pieces)
                if b.figure is None and _signature(text).startswith(caption)
            ]
        ):
            at, inside = found[0], found[:1]
        else:
            below = [
                i
                for i, (_, b) in enumerate(pieces)
                if b.box is not None and b.box[1] >= figure.rect[1]
            ]
            at = below[0] if below else len(pieces)
        text = figure_reading.passage(reading)
        if figure.caption:
            text = f"{' '.join(figure.caption.split())} {text}"
        kept = [p for i, p in enumerate(pieces) if i not in inside]
        at -= sum(1 for i in inside if i < at)
        kept.insert(at, (text, parsing.ParsedBlock(0, 0, False, figure=str(row.id))))
        pieces = kept

    text, blocks = "", []
    for piece, block in pieces:
        if text:
            text += parsing.PARAGRAPH_BREAK
        blocks.append(
            parsing.ParsedBlock(
                len(text),
                len(text) + len(piece),
                block.is_heading,
                block.box,
                block.figure,
            )
        )
        text += piece
    return parsing.ParsedPage(page.number, text, tuple(blocks), page.ocr)


def with_figures(
    session: Session, document: Document, parsed: parsing.ParsedDocument
) -> parsing.ParsedDocument:
    """The parsed document with each figure read, and accepted, in its page."""
    by_page: dict[int, list[FigureReading]] = {}
    for row in _latest(session, document).values():
        if row.status == "accepted":
            by_page.setdefault(row.page_number, []).append(row)
    if not by_page:
        return parsed
    pages = [
        _place(page, by_page[page.number]) if page.number in by_page else page
        for page in parsed.pages
    ]
    return parsing.ParsedDocument(pages=pages, repaired=parsed.repaired)


def page_figures(session: Session, pages: list[DocumentPage]) -> dict[int, list[dict]]:
    """The figures each page holds, with what was read in them, by page."""
    placed = {
        f["id"]: (page.page_number, f) for page in pages for f in page.figures or ()
    }
    if not placed:
        return {}
    rows = session.scalars(
        select(FigureReading).where(
            FigureReading.id.in_([uuid.UUID(i) for i in placed])
        )
    )
    found: dict[int, list[dict]] = {}
    for row in rows:
        number, where = placed[str(row.id)]
        reading = as_reading(row)
        found.setdefault(number, []).append(
            {
                "id": row.id,
                "start": where["start"],
                "end": where["end"],
                "caption": row.caption,
                "kind": reading.kind,
                "text": list(reading.text),
                "tables": [
                    {"title": t.title, "rows": [list(r) for r in t.rows]}
                    for t in reading.tables
                ],
                "description": reading.description,
            }
        )
    for figures in found.values():
        figures.sort(key=lambda f: f["start"])
    return found


# --- the figure's picture ---------------------------------------------------------


def image(session: Session, reading_id: uuid.UUID) -> bytes | None:
    """A figure's picture, with its caption, from the document's current
    file; None if there is no such reading or it was of another version."""
    row = session.get(FigureReading, reading_id)
    if row is None:
        return None
    document = session.get(Document, row.document_id)
    if document is None or document.sha256 != row.sha256:
        return None
    path = storage.document_path(document.environment_id, document.id)
    return parsing.figure_image(path, as_figure(row))
