"""Gives the end-to-end tests a world of their own before the API starts:
their database dropped, created and migrated, their data folder and Redis
database emptied, and the three PDFs the journey uploads written to the folder
given. Emptying Redis forgets a worker that an earlier run left behind
without saying goodbye, which the API would otherwise still count.

    python -m tests.e2e.prepare <folder for the PDFs>

Refuses unless DATABASE_URL names a database ending in "_e2e", DATA_DIR is
not the real data folder and REDIS_URL is not development's Redis database,
so it can never empty any of those.
"""

import shutil
import sys
from pathlib import Path

import pymupdf
import redis
from alembic import command
from sqlalchemy import make_url

from app.config import REPO_ROOT, Settings, settings
from tests import pdfs
from tests.conftest import _recreate_database, alembic_config
from tests.e2e.model import (
    CHART_CAPTION,
    CHART_LABELS,
    EIGENVALUES_FORMULA,
    EIGENVALUES_PROSE,
)

WEEK_1 = pdfs.html_pdf(
    "<h2>Processes</h2><p>A process is a program in execution. The kernel gives "
    "each process its own address space, its open files and at least one thread "
    "of control, and keeps their state in a process control block.</p>",
    "<h2>Threads</h2><p>Threads of one process share its address space and open "
    "files, but each has its own stack and registers. Switching between threads "
    "of the same process is cheaper than switching processes, because no page "
    "tables change.</p>",
    "<h2>CPU Scheduling</h2><p>When several threads are ready, the scheduler "
    "decides which runs next. Round robin gives each one a fixed time quantum "
    "and then preempts it, moving it to the back of the ready queue.</p>",
)

WEEK_2 = pdfs.html_pdf(
    "<h2>Paging</h2><p>Paging divides physical memory into fixed-size frames and "
    "each address space into pages of the same size. A page table maps every "
    "page to its frame.</p>",
    "<h2>Page faults</h2><p>A page fault occurs when a page of a process is not "
    "resident in memory. The kernel loads the page from disk, updates the page "
    "table and restarts the instruction that faulted. Paging lets a process run "
    "with only some of its pages resident.</p>",
)


def _week_3() -> bytes:
    """A lecture whose one page sets a formula in a maths font."""
    document = pymupdf.open(
        stream=pdfs.html_pdf(f"<h2>Eigenvalues</h2><p>{EIGENVALUES_PROSE}</p>"),
        filetype="pdf",
    )
    document[0].insert_text((72, 400), EIGENVALUES_FORMULA, fontname="symb")
    data = document.tobytes()
    document.close()
    return data


WEEK_3 = _week_3()


def _week_4() -> bytes:
    """A lecture with a chart drawn under its prose, labelled and captioned,
    whose figures the journey reads (decision record 29)."""
    document = pymupdf.open(
        stream=pdfs.html_pdf(
            "<h2>Time slices</h2><p>Round robin gives each ready process the "
            "processor for one time slice in turn, then moves it to the back of "
            "the queue.</p>"
        ),
        filetype="pdf",
    )
    page = document[0]
    for n, label in enumerate(CHART_LABELS):
        bar = pymupdf.Rect(150 + n * 110, 330, 250 + n * 110, 420)
        page.draw_rect(bar, fill=(0.8, 0.8, 0.8))
        page.insert_text((bar.x0 + 40, bar.y0 + 50), label, fontsize=11)
    page.draw_line((140, 430), (480, 430))
    page.insert_text((150, 450), CHART_CAPTION, fontsize=9)
    data = document.tobytes()
    document.close()
    return data


def _board() -> bytes:
    """A photograph of a note on a board: a picture, read by OCR (record 29)."""
    source = pymupdf.open()
    page = source.new_page(width=500, height=200)
    page.insert_text((30, 110), BOARD_NOTE, fontsize=24)
    data = page.get_pixmap(dpi=150).tobytes("png")
    source.close()
    return data


WEEK_4 = _week_4()
BOARD_NOTE = "Quantum too short: too many switches"
BOARD = _board()

FILES = {
    "Week 1 processes.pdf": WEEK_1,
    "Week 2 memory.pdf": WEEK_2,
    "Week 3 eigenvalues.pdf": WEEK_3,
    "Week 4 scheduling.pdf": WEEK_4,
    "Board note.png": BOARD,
}


def main(pdf_folder: Path) -> None:
    url = make_url(settings.database_url)
    if not (url.database or "").endswith("_e2e"):
        sys.exit(f"Refusing to reset {url.database!r}: its name must end in _e2e.")
    if settings.data_dir.resolve() == (REPO_ROOT / "data").resolve():
        sys.exit("Refusing to empty the real data folder: set DATA_DIR.")
    if settings.redis_url == Settings.model_fields["redis_url"].default:
        sys.exit("Refusing to empty development's Redis database: set REDIS_URL.")

    _recreate_database(url)
    command.upgrade(alembic_config(url), "head")
    shutil.rmtree(settings.data_dir, ignore_errors=True)
    settings.data_dir.mkdir(parents=True)
    redis.Redis.from_url(settings.redis_url).flushdb()

    pdf_folder.mkdir(parents=True, exist_ok=True)
    for name, data in FILES.items():
        (pdf_folder / name).write_bytes(data)
    print(f"Prepared {url.database}, {settings.data_dir} and {len(FILES)} PDFs.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(Path(sys.argv[1]))
