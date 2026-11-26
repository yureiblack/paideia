"""Reading a document's figures with the vision model (decision records 29
and 31).

Purpose
-------
A figure's text layer is its tick labels and cells, out of order, and
nothing of what it draws. The local model can look at the figure and copy
what is written in it, its labels and its tables in rows, at about a quarter
of a minute a figure. Every figure is read as part of reading the document
(record 31): its reading job, one step per figure, comes after the first
reading of the text, so the text is there to read at once.

Each figure is read once and, if its reading disagrees with the figure's own
text (app/figure_reading.py), once more. A figure that still disagrees keeps
the PDF's text, and the update says why.

Readings are kept per version of the file. Reading the document puts every
figure in its page (with_figures): all the text inside it gathered in one
place, which the reader shows as the figure's picture, and an accepted
reading's passage in place of the text it repeats. That passage, the
caption and what is written in the figure, is read by summaries and
concepts like any other. The model's description of the figure is kept with
the reading but is in no passage: it could not be checked, and was wrong in
half the diagrams it was tried on.
"""

import json
import logging
import re
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
        placed.update(r for f in figures or () if (r := _reading_of(f)))
    return placed


def _reading_of(entry: dict) -> str | None:
    """The reading a page's figure holds; before record 31 a page listed
    only figures read, by "id"."""
    return entry.get("reading", entry.get("id"))


def _waiting(session: Session, document: Document) -> list[str]:
    """Figures read and accepted whose reading is not in place yet."""
    placed = _in_place(session, document)
    return [
        key
        for key, row in _latest(session, document).items()
        if row.status == "accepted" and str(row.id) not in placed
    ]


def not_read(
    session: Session,
    document: Document,
    llm: LLMProvider,
    figures: list[parsing.Figure],
) -> list[parsing.Figure]:
    """Of the figures found in the document's file, those not yet read with
    this model and prompt."""
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
    return [f for f in figures if f.key not in done]


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
        reason = figure_reading.check(reading, own)
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
    session_factory: SessionFactory, document_id: uuid.UUID, found: int = 0
) -> dict | None:
    """A step of reading the document again after its figures were read:
    put it back in the queue to be read if a figure read is not in place
    yet. Returns the figures read and kept, for the update, and how many of
    the found were not read at all, as when the reading was stopped; None
    if the document is gone."""
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
            "read": sorted(k for k, r in latest.items() if r.status == "accepted"),
            "kept": {
                k: r.reason for k, r in sorted(latest.items()) if r.status == "rejected"
            },
            "not_read": max(0, found - len(latest)),
            "changed": len(changed),
        }


def _centre(box: tuple[float, float, float, float]) -> pymupdf.Point:
    return pymupdf.Point((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


def _signature(text: str) -> str:
    return "".join(c for c in text.lower() if c.isalnum())


# A piece of a page: its text, its block, and the figure (key) it belongs to.
_Piece = tuple[str, parsing.ParsedBlock, str | None]

# LaTeX's markup, which says nothing a figure's own text could: \( and \)
# and commands, set apart; braces, sub- and superscript marks and dollar
# signs, taken out, so L_1 is L1 as the PDF sets it.
_LATEX_APART = re.compile(r"\\[()\[\]]|\\[A-Za-z]+")
_LATEX_OUT = re.compile(r"[{}_^$]")


def _without_latex(text: str) -> str:
    return _LATEX_OUT.sub("", _LATEX_APART.sub(" ", text))


def _says_only(text: str, own: str) -> bool | None:
    """Whether a paragraph of a page whose maths was read says only what the
    figure's own text says, word for word and number for number: a table's
    rows, a plot's labels. None for one with no word or number at all, such
    as a rule or a stray fence."""
    plain = _without_latex(text)
    words, numbers = figure_reading.words(plain), figure_reading.numbers(plain)
    if not words and not numbers:
        return None
    own_words, own_numbers = (
        set(figure_reading.words(own)),
        set(figure_reading.numbers(own)),
    )
    squashed = "".join(figure_reading.words(own))
    return all(w in own_words or w in squashed for w in words) and all(
        n in own_numbers for n in numbers
    )


def _gathered(pieces: list[_Piece], anchor: int, own: str) -> list[int]:
    """On a page whose maths was read, which keeps no places, a figure's
    paragraphs: the one at anchor, its caption's, and those on either side
    of it that say only what the figure's own text says, as the model wrote
    out a table's rows."""

    def free(i: int) -> bool:
        return (
            0 <= i < len(pieces)
            and pieces[i][2] is None
            and pieces[i][1].figure is None
        )

    taken = [anchor]
    for step in (1, -1):
        i, pending = anchor + step, []
        while free(i):
            verdict = _says_only(pieces[i][0], own)
            if verdict is False:
                break
            pending.append(i)
            if verdict:
                taken += pending
                pending = []
            i += step
    return sorted(taken)


def _place(
    page: parsing.ParsedPage,
    figures: list[tuple[parsing.Figure, FigureReading | None]],
    own: dict[str, str] | None = None,
) -> parsing.ParsedPage:
    """The page with each figure's text gathered in one place: the blocks
    inside it, or failing those its caption's paragraph and, given the
    figure's own text (own, by key), the paragraphs beside it that say only
    what that does. A figure read, and accepted, has its passage there in
    place of its caption and of the text it repeats; what the model left
    out stays in the page, beside it. A figure with no text at all is placed
    where its height puts it."""
    pieces: list[_Piece] = [(page.text[b.start : b.end], b, None) for b in page.blocks]
    if not pieces and page.text.strip():
        pieces = [(page.text.strip(), parsing.ParsedBlock(0, 0, False), None)]
    for figure, row in sorted(figures, key=lambda f: (f[0].rect[1], f[0].rect[0])):
        key = figure.key
        crop = pymupdf.Rect(figure.crop) + (-2, -2, 2, 2)
        free = [i for i, (_, b, owner) in enumerate(pieces) if owner is None]
        within = [
            i
            for i in free
            if (box := pieces[i][1].box) is not None
            and pieces[i][1].figure is None
            and _centre(box) in crop
        ]
        caption = _signature(figure.caption or "")[:40]
        by_caption = (
            [
                i
                for i in free
                if pieces[i][1].figure is None
                and _signature(pieces[i][0]).startswith(caption)
            ][:1]
            if caption and not within
            else []
        )
        known = (own or {}).get(key)
        if known and not within:
            if not by_caption and (label := _signature(name(figure))) != "afigure":
                # The model may set the caption out of its order, as
                # "Table 2.11. | L∞ distance matrix": its paragraph names
                # the figure and says only what the figure does.
                by_caption = [
                    i
                    for i in free
                    if pieces[i][1].figure is None
                    and label in _signature(pieces[i][0])
                    and _says_only(pieces[i][0], known)
                ][:1]
            mine = _gathered(pieces, by_caption[0], known) if by_caption else []
        else:
            mine = within or by_caption
        if mine:
            at = mine[0]
        else:
            below = [
                i
                for i in free
                if (box := pieces[i][1].box) is not None and box[1] >= figure.rect[1]
            ]
            at = below[0] if below else len(pieces)

        group: list[_Piece] = [(t, b, key) for t, b, _ in (pieces[i] for i in mine)]
        if row is not None:
            reading = as_reading(row)
            caption_area = (
                pymupdf.Rect(figure.caption_rect) + (-2, -2, 2, 2)
                if figure.caption_rect
                else None
            )
            # The text inside the figure gives way to the reading only where
            # the reading repeats it: what the model left out stays. The
            # caption always does, as the figure's passage begins with it.
            replaced = {
                i
                for i in mine
                if i in by_caption
                or (
                    caption_area is not None
                    and (box := pieces[i][1].box) is not None
                    and _centre(box) in caption_area
                )
                or figure_reading.repeats(reading, _without_latex(pieces[i][0]))
            }
            text = " ".join(
                part
                for part in (
                    " ".join((figure.caption or "").split()),
                    figure_reading.passage(reading),
                )
                if part
            )
            group = [
                (text, parsing.ParsedBlock(0, 0, False, figure=str(row.id)), key),
                *(
                    (t, b, key)
                    for i, (t, b, _) in enumerate(pieces)
                    if i in mine and i not in replaced
                ),
            ]
        if not group:
            group = [("", parsing.ParsedBlock(0, 0, False), key)]
        taken = set(mine)
        rest = [p for i, p in enumerate(pieces) if i not in taken]
        at -= sum(1 for i in taken if i < at)
        pieces = rest[:at] + group + rest[at:]

    text, blocks = "", []
    spans: dict[str, tuple[int, int]] = {}
    for piece, block, owner in pieces:
        if not piece:  # a figure with no text: its picture goes here
            if owner is not None:
                spans.setdefault(owner, (len(text), len(text)))
            continue
        if text:
            text += parsing.PARAGRAPH_BREAK
        start = len(text)
        text += piece
        blocks.append(
            parsing.ParsedBlock(
                start, len(text), block.is_heading, block.box, block.figure
            )
        )
        if owner is not None:
            spans[owner] = (spans[owner][0] if owner in spans else start, len(text))
    placed = []
    for figure, row in figures:
        if figure.key in spans:
            start, end = spans[figure.key]
            held = str(row.id) if row is not None else None
            placed.append(parsing.PlacedFigure(figure, start, end, held))
    placed.sort(key=lambda f: (f.start, f.end))
    return parsing.ParsedPage(page.number, text, tuple(blocks), page.ocr, tuple(placed))


def find(path: Path) -> list[parsing.Figure]:
    """The figures of a file, or none if they cannot be found: a fault in
    finding them never stops a document being read."""
    try:
        return parsing.figures(path)
    except parsing.ParseError:
        return []  # the parser reports an unreadable file
    except Exception:
        logger.exception("Could not find the figures of %s", path)
        return []


def with_figures(
    session: Session,
    document: Document,
    parsed: parsing.ParsedDocument,
    found: list[parsing.Figure] | None = None,
) -> parsing.ParsedDocument:
    """The parsed document with every figure in its page: each found in the
    file (found, else found here), and each read and accepted, its reading
    in place of the text it repeats."""
    path = storage.document_path(document.environment_id, document.id)
    if found is None:
        found = find(path)
    accepted = {
        key: row
        for key, row in _latest(session, document).items()
        if row.status == "accepted"
    }
    by_page: dict[int, dict[str, tuple[parsing.Figure, FigureReading | None]]] = {}
    for figure in found:
        by_page.setdefault(figure.page, {})[figure.key] = (
            figure,
            accepted.get(figure.key),
        )
    # A figure read that the finder no longer finds, as after a change to
    # the finder, stays where it was read.
    for key, row in accepted.items():
        by_page.setdefault(row.page_number, {}).setdefault(key, (as_figure(row), row))
    if not by_page:
        return parsed
    pages = [
        _place(
            page,
            list(by_page[page.number].values()),
            _own_texts(path, page, by_page[page.number].values()),
        )
        if page.number in by_page
        else page
        for page in parsed.pages
    ]
    return parsing.ParsedDocument(pages=pages, repaired=parsed.repaired)


def _own_texts(path: Path, page: parsing.ParsedPage, figures) -> dict[str, str]:
    """For a page whose maths was read, which keeps no places, each figure's
    own text, its labels, cells and caption, to find its paragraphs by."""
    if any(b.box is not None for b in page.blocks):
        return {}
    texts = {}
    for figure, _ in figures:
        try:
            inside = parsing.figure_text(path, figure)
        except parsing.ParseError:
            inside = ""
        texts[figure.key] = f"{inside}\n{figure.caption or ''}"
    return texts


def stored(placed: parsing.PlacedFigure) -> dict:
    """A figure in its page as the page's row keeps it (DocumentPage.figures)."""
    figure = placed.figure
    return {
        "key": figure.key,
        "rect": list(figure.rect),
        "caption": figure.caption,
        "caption_rect": list(figure.caption_rect) if figure.caption_rect else None,
        "reading": placed.reading,
        "start": placed.start,
        "end": placed.end,
    }


def page_figures(session: Session, pages: list[DocumentPage]) -> dict[int, list[dict]]:
    """The figures each page holds, by page: each one's key, where its text
    is in the page, and its caption. A page stored before record 31 lists
    only the figures read, by their reading."""
    found: dict[int, list[dict]] = {}
    old: dict[str, tuple[int, dict]] = {}
    for page in pages:
        for entry in page.figures or ():
            if "key" in entry:
                found.setdefault(page.page_number, []).append(
                    {
                        "key": entry["key"],
                        "start": entry["start"],
                        "end": entry["end"],
                        "caption": entry["caption"],
                    }
                )
            elif "id" in entry:
                old[entry["id"]] = (page.page_number, entry)
    if old:
        for row in session.scalars(
            select(FigureReading).where(
                FigureReading.id.in_([uuid.UUID(i) for i in old])
            )
        ):
            number, entry = old[str(row.id)]
            found.setdefault(number, []).append(
                {
                    "key": row.figure_key,
                    "start": entry["start"],
                    "end": entry["end"],
                    "caption": row.caption,
                }
            )
    for figures in found.values():
        figures.sort(key=lambda f: (f["start"], f["end"]))
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


def image_at(session: Session, document: Document, key: str) -> bytes | None:
    """The picture of the figure with this key in the document's current
    file, as its page holds it; None if the page holds no such figure."""
    number, _, _ = key.partition(":")
    if not number.isdigit():
        return None
    page = session.scalar(
        select(DocumentPage).where(
            DocumentPage.document_id == document.id,
            DocumentPage.page_number == int(number),
        )
    )
    figure = None
    for entry in (page.figures if page is not None else None) or ():
        if entry.get("key") == key:
            figure = parsing.Figure(
                page=int(number),
                rect=tuple(entry["rect"]),
                caption=entry["caption"],
                caption_rect=tuple(entry["caption_rect"])
                if entry["caption_rect"]
                else None,
            )
        elif _reading_of(entry):
            row = session.get(FigureReading, uuid.UUID(_reading_of(entry)))
            if row is not None and row.figure_key == key and "key" not in entry:
                figure = as_figure(row)
        if figure is not None:
            break
    if figure is None:
        return None
    path = storage.document_path(document.environment_id, document.id)
    return parsing.figure_image(path, figure)
