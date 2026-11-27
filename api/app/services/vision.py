"""What the vision model reads when a document is read (decision record 31).

Purpose
-------
Reading a document reads its maths (record 26) and its figures (record 29)
too, never as a separate request. Its chain of jobs is:

1. reading the text layer, so the document can be read and searched at
   once;
2. reading, with the vision model, each page that sets maths in maths fonts
   and each figure, not read before for this version of the file, model
   and prompt: one step each (app/services/jobs.py, vision_steps);
3. reading the document again with what was read in place;
4. everything made from it: its summary, concepts, the map, the roadmap.

Steps 2 and 3 are left out when there is nothing to read. Cancelling step 2
skips the rest of it; steps 3 and 4 go on with what it read.

What there is to read is found when the reading is asked for, from the
file, so the job knows its steps: 2.4 seconds for a 77-page chapter, 12 for
an 873-page textbook.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app import parsing
from app.llm import LLMProvider
from app.models import Document
from app.services import figures as figure_service
from app.services import maths_reading

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Found:
    """What a file holds for the vision model: its pages that set maths, and
    its figures."""

    maths_pages: list[int]
    figures: list[parsing.Figure]


@dataclass(frozen=True)
class ToRead:
    """Of what was found, what is still to read with this model and prompt."""

    found: Found
    pages: list[int]
    figures: list[parsing.Figure]

    def __bool__(self) -> bool:
        return bool(self.pages or self.figures)

    @property
    def what(self) -> str:
        """ "maths and figures", "maths" or "figures": what is to be read."""
        if self.pages and self.figures:
            return "maths and figures"
        return "maths" if self.pages else "figures"


def find(path: Path) -> Found:
    """What the file holds for the vision model. A file that cannot be read
    holds nothing, as reading its text will say; a fault in finding never
    stops a document being read."""
    try:
        pages = sorted(parsing.maths_pages(path))
    except parsing.ParseError:
        pages = []
    except Exception:
        logger.exception("Could not find the maths pages of %s", path)
        pages = []
    return Found(pages, figure_service.find(path))


def to_read(
    session: Session, document: Document, llm: LLMProvider, found: Found
) -> ToRead:
    """What is still to read of what was found in the document's file."""
    return ToRead(
        found,
        maths_reading.not_read(session, document, llm, found.maths_pages),
        figure_service.not_read(session, document, llm, found.figures),
    )
