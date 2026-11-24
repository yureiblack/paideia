"""The model's readings of the maths lectures' pages, kept so the benchmark
can be scored again without the model.

Purpose
-------
Reading a page takes the local model half a minute or more, and at
temperature 0 the same image always gets the same answer. So every answer is
kept in docs/evaluation/maths/readings.json with what produced it: the
lecture, the page, which part of the page (whole, or its top or bottom half),
the SHA-256 of the image the model saw, the model and the prompt version. A
run asks the model only for an image it has no answer for; changing the
check, the comparison or the report never needs the model again.

Each page is read both ways the app reads it (app/services/maths_reading.py):
whole, and in two halves, each seen larger. The app asks for the halves only
when the whole page fails its check; the benchmark reads every page both
ways, so that both attempts can be measured on every page, and works out
from them what the app would have done.
"""

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

import pymupdf

from app import parsing, prompting
from app.llm import LLMProvider
from evaluation import maths_corpus

READINGS = maths_corpus.ROOT / "docs" / "evaluation" / "maths" / "readings.json"
PROMPT = ("page_transcription", "v1")  # as app/services/maths_reading.py asks
PROMPT_ID = "/".join(PROMPT)
PARTS = ("whole", "top", "bottom")


@dataclass(frozen=True)
class Reading:
    lecture: str  # its filename, such as 04-limits-derivatives-integrals.pdf
    page: int
    part: str  # whole, top or bottom
    image: str  # SHA-256 of the PNG the model saw
    model: str
    prompt: str
    seconds: float
    answer: str


def image(pdf: Path, page: int, part: str) -> bytes:
    """The PNG the app shows the model for this part of the page."""
    return parsing.page_image(pdf, page, None if part == "whole" else part)


def load(path: Path = READINGS) -> list[Reading]:
    if not path.exists():
        return []
    return [Reading(**r) for r in json.loads(path.read_text(encoding="utf-8"))]


def save(readings: list[Reading], path: Path = READINGS) -> None:
    ordered = sorted(
        readings, key=lambda r: (r.lecture, r.page, PARTS.index(r.part), r.model)
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([asdict(r) for r in ordered], indent=1, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def read_all(
    pdfs: dict[str, Path],
    llm: LLMProvider,
    path: Path = READINGS,
    progress: Callable[[str], None] = print,
    only: dict[str, list[int]] | None = None,
) -> list[Reading]:
    """Every part of every page of the given PDFs (or of the pages named in
    only), read by the model, from the kept readings where the same image
    was read by the same model with the same prompt. New readings are saved
    as they come, so a run that is stopped loses at most one page."""
    kept = load(path)
    known = {(r.image, r.model, r.prompt): r for r in kept}
    prompt = prompting.render(*PROMPT)
    wanted: list[Reading] = []
    for lecture, pdf in sorted(pdfs.items()):
        with pymupdf.open(pdf) as document:
            pages = document.page_count
        for page in (only or {}).get(lecture) or range(1, pages + 1):
            for part in PARTS:
                png = image(pdf, page, part)
                digest = hashlib.sha256(png).hexdigest()
                found = known.get((digest, llm.model_name, PROMPT_ID))
                if found is None or (found.lecture, found.page, found.part) != (
                    lecture,
                    page,
                    part,
                ):
                    if found is None:
                        started = time.perf_counter()
                        answer = llm.transcribe(prompt, png)
                        progress(
                            f"{lecture} page {page} {part}: "
                            f"{answer.seconds:.1f} s ({time.perf_counter() - started:.1f} s with waiting)"
                        )
                        found = Reading(
                            lecture,
                            page,
                            part,
                            digest,
                            llm.model_name,
                            PROMPT_ID,
                            round(answer.seconds, 1),
                            answer.value,
                        )
                    else:
                        found = Reading(
                            lecture,
                            page,
                            part,
                            digest,
                            found.model,
                            found.prompt,
                            found.seconds,
                            found.answer,
                        )
                    known[(digest, llm.model_name, PROMPT_ID)] = found
                    kept = [
                        r
                        for r in kept
                        if (r.lecture, r.page, r.part, r.model, r.prompt)
                        != (lecture, page, part, llm.model_name, PROMPT_ID)
                    ] + [found]
                    save(kept, path)
                wanted.append(found)
    return wanted
