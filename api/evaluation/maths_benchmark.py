"""The maths benchmark: how well the app reads maths, checks what it read,
finds it again and offers practice on it (decision record 30).

Purpose
-------
Every number in docs/evaluation/maths-benchmark.md comes from a run of this
module, through scripts/evaluate_maths.py; none is typed by hand. A run:

1. typesets the ten lectures of docs/evaluation/maths/corpus/ with Tectonic
   and works out what each page truly says (evaluation/maths_corpus.py);
2. gives the check (app/transcription.py) each page's perfect reading: a
   page whose perfect reading is refused shows a quirk of the check;
3. plants one mistake at a time in those perfect readings, of every kind
   in evaluation/maths_planted.py, and counts the ones the check catches;
4. takes the model's readings of every page, whole and in halves, from
   docs/evaluation/maths/readings.json (asking the model only for pages it
   has not read, and only with --read), turns each into page text as the
   app does, checks it as the app does, and compares it with the truth
   formula by formula (evaluation/maths_compare.py); from the two attempts
   it works out what the app would have kept;
5. times each step the app takes;
6. reads the lectures into a database of its own three times, as the PDF's
   text layer has them, with the model's accepted readings in place, and
   with perfect readings in place, and asks each version the questions of
   docs/evaluation/maths/questions.json by the four methods of record 20;
7. with --practice, has the model extract the concepts of the lectures as
   read and choose computed exercises for them as the app does, and judges
   each choice against the exercise types each lecture teaches;
8. writes docs/evaluation/maths/results.json and rewrites only the tables
   between markers in docs/evaluation/maths-benchmark.md.

Nothing touches development or test data: the database is the development
database's name with _maths_eval appended, rebuilt by each run, and uploads
go to a temporary folder.
"""

import argparse
import asyncio
import hashlib
import json
import re
import statistics
import tempfile
import time
import uuid
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pymupdf
from sqlalchemy import URL, create_engine, make_url, select
from sqlalchemy.orm import sessionmaker

from app import parsing, storage, transcription
from app.config import settings
from app.embedding import Embedder, default_embedder
from app.llm import LLMProvider, default_provider
from app.models import Document, DocumentChunk, Environment, PageTranscription
from app.parsing import PageLayer, PyMuPDFParser
from app.reranking import Reranker, default_reranker
from app.schemas import EnvironmentCreate
from app.services import documents as document_service
from app.services import environments as environment_service
from app.services.search import RetrievalSizes
from evaluation import (
    benchmark,
    maths_compare,
    maths_corpus,
    maths_dataset,
    maths_planted,
    maths_readings,
    metrics,
    notation,
)
from evaluation.dataset import Passage

ROOT = maths_corpus.ROOT
RESULTS = ROOT / "docs" / "evaluation" / "maths" / "results.json"
REPORT = ROOT / "docs" / "evaluation" / "maths-benchmark.md"
EXERCISE_LABELS = ROOT / "docs" / "evaluation" / "maths" / "exercise-labels.json"

K = benchmark.K
VARIANTS = {
    "layer": "The PDF's text layer (maths not read)",
    "read": "The model's readings, where the check accepted them",
    "truth": "Perfect readings",
}
NO_LAYER = PageLayer("", "", ())

# --- the lectures, typeset ----------------------------------------------------------


@dataclass(frozen=True)
class Built:
    lecture: maths_corpus.Lecture
    typeset: maths_corpus.Typeset
    pdf: Path

    @property
    def pages(self) -> range:
        return range(1, self.typeset.page_count + 1)

    def truth(self, page: int) -> str:
        """What the page says, as the model is asked to write it."""
        return maths_corpus.page_truth(self.lecture, self.typeset, page)


def typeset_all(folder: Path) -> tuple[list[Built], dict]:
    built, seconds = [], {}
    for lecture in maths_corpus.lectures():
        start = time.perf_counter()
        typeset = maths_corpus.typeset(lecture)
        seconds[lecture.filename] = round(time.perf_counter() - start, 2)
        pdf = folder / lecture.filename
        pdf.write_bytes(typeset.pdf)
        built.append(Built(lecture, typeset, pdf))
    return built, seconds


def _one_line_displays(markdown: str) -> str:
    """The Markdown with each displayed formula on one line, so nothing in
    it is mistaken for a damaged command (decision record 30, the
    line-break fault)."""
    return "\n\n".join(
        " ".join(block.split("\n")) if block.startswith("$$") else block
        for block in markdown.split("\n\n")
    )


def stored_truth(markdown: str, layer: PageLayer = NO_LAYER) -> transcription.PageText:
    """A page's truth as the app would store a perfect reading of it."""
    return transcription.page_text(_one_line_displays(markdown), layer)


def corpus_stats(built: list[Built]) -> dict:
    kinds: Counter = Counter()
    formulas = 0
    for b in built:
        for page in b.pages:
            for f in maths_compare.stream(stored_truth(b.truth(page)).text).formulas:
                formulas += 1
                kinds.update(notation.kinds_in(f.latex))
    return {
        "lectures": len(built),
        "pages": sum(b.typeset.page_count for b in built),
        "formulas": formulas,
        "words": sum(len(b.lecture.source.split()) for b in built),
        "notation": {k.name: kinds[k.name] for k in notation.KINDS},
    }


# --- the check on perfect readings, and on planted mistakes --------------------------


def _verdict(
    markdown: str, layer: PageLayer
) -> tuple[transcription.PageText | None, str | None]:
    """The page text the app would store, and why the check refuses it."""
    try:
        page = transcription.page_text(markdown, layer)
    except transcription.Unusable as exc:
        return None, str(exc)
    return page, transcription.check(page, layer).reason


def truth_check(built: list[Built]) -> list[dict]:
    rows = []
    for b in built:
        for page in b.pages:
            _, reason = _verdict(b.truth(page), parsing.page_layer(b.pdf, page))
            rows.append({"lecture": b.lecture.filename, "page": page, "reason": reason})
    return rows


def planted(built: list[Built], passing: set[tuple[str, int]]) -> dict:
    kinds: dict[str, dict] = {
        k.name: {"label": k.label, "planted": 0, "caught": 0, "missed": []}
        for k in maths_planted.KINDS
    }
    for b in built:
        for page in b.pages:
            if (b.lecture.filename, page) not in passing:
                continue
            layer = parsing.page_layer(b.pdf, page)
            truth = b.truth(page)
            for kind in maths_planted.KINDS:
                seed = f"{b.lecture.filename}:{page}:{kind.name}"
                for mistake in maths_planted.plant(truth, kind, seed):
                    row = kinds[kind.name]
                    row["planted"] += 1
                    _, reason = _verdict(mistake.page_markdown, layer)
                    if reason:
                        row["caught"] += 1
                    elif len(row["missed"]) < 3:
                        row["missed"].append(
                            {
                                "lecture": b.lecture.filename,
                                "page": page,
                                "before": mistake.before.strip()[:160],
                                "after": mistake.after.strip()[:160],
                            }
                        )
    return {"pages": len(passing), "per_page": maths_planted.PER_PAGE, "kinds": kinds}


# --- the model's readings ------------------------------------------------------------


def _attempt(
    answers: list[maths_readings.Reading], truth_text: str, layer: PageLayer
) -> dict:
    """One attempt at a page, as the app would take it: its answers joined,
    made page text, checked; then compared with the truth."""
    joined = "\n\n".join(
        transcription.without_chatter(r.answer).strip() for r in answers
    )
    page, reason = _verdict(joined, layer)
    row: dict = {
        "seconds": round(sum(r.seconds for r in answers), 1),
        "usable": page is not None,
        "reason": reason,
        "accepted": page is not None and reason is None,
    }
    if page is None:
        return row
    found = maths_compare.compare(truth_text, page.text)
    row.update(
        {
            "formulas": len(found.formulas),
            "right": sum(f.right for f in found.formulas),
            "maths_tokens": found.maths_tokens,
            "maths_errors": found.maths_errors,
            "prose_words": found.prose_words,
            "prose_errors": found.prose_errors,
            "styling": found.styling,
            "results": [
                {
                    "latex": f.latex,
                    "right": f.right,
                    "kinds": notation.kinds_in(f.latex),
                    "changes": [
                        {
                            "kind": c.kind,
                            "page": " ".join(c.page),
                            "reading": " ".join(c.reading),
                        }
                        for c in f.changes
                    ],
                }
                for f in found.formulas
            ],
            "prose_changes": [
                {
                    "kind": c.kind,
                    "page": " ".join(c.page),
                    "reading": " ".join(c.reading),
                }
                for c in found.other_changes
            ][:10],
        }
    )
    return row


def score_page(
    parts: dict[str, maths_readings.Reading], truth_text: str, layer: PageLayer
) -> dict:
    """A page's two attempts, judged and compared, and what the app keeps:
    the whole reading if the check accepts it, else the halves if it
    accepts those, else the text layer."""
    whole = _attempt([parts["whole"]], truth_text, layer)
    halves = _attempt([parts["top"], parts["bottom"]], truth_text, layer)
    both = round(whole["seconds"] + halves["seconds"], 1)
    if whole["accepted"]:
        app = {"kept": "whole", "seconds": whole["seconds"]}
    elif halves["accepted"]:
        app = {"kept": "halves", "seconds": both}
    else:
        app = {"kept": "text layer", "seconds": both}
    return {"whole": whole, "halves": halves, "app": app}


def score_readings(
    built: list[Built], readings: list[maths_readings.Reading]
) -> list[dict]:
    by_part = {(r.lecture, r.page, r.part): r for r in readings}
    pages = []
    for b in built:
        for page in b.pages:
            name = b.lecture.filename
            found = {p: by_part.get((name, page, p)) for p in maths_readings.PARTS}
            parts = {p: r for p, r in found.items() if r is not None}
            if len(parts) < len(found):
                raise RuntimeError(
                    f"{name} page {page} has not been read; run with --read"
                )
            layer = parsing.page_layer(b.pdf, page)
            truth_text = stored_truth(b.truth(page)).text
            pages.append(
                {"lecture": name, "page": page, **score_page(parts, truth_text, layer)}
            )
    return pages


def _wrong(attempt: dict) -> bool:
    return attempt["right"] < attempt["formulas"]


def reading_summary(pages: list[dict]) -> dict:
    summary: dict = {}
    for name in ("whole", "halves"):
        attempts = [p[name] for p in pages]
        usable = [a for a in attempts if a["usable"]]
        summary[name] = {
            "attempts": len(attempts),
            "usable": len(usable),
            "formulas": sum(a["formulas"] for a in usable),
            "right": sum(a["right"] for a in usable),
            "pages_all_right": sum(not _wrong(a) for a in usable),
            "maths_tokens": sum(a["maths_tokens"] for a in usable),
            "maths_errors": sum(a["maths_errors"] for a in usable),
            "prose_words": sum(a["prose_words"] for a in usable),
            "prose_errors": sum(a["prose_errors"] for a in usable),
            "seconds": _spread([a["seconds"] for a in attempts]),
        }
    # What the app keeps: the first accepted attempt, else the text layer.
    kept = Counter(p["app"]["kept"] for p in pages)
    let_through = right_kept = formulas_kept = 0
    for p in pages:
        choice = p["app"]["kept"]
        if choice == "text layer":
            continue
        attempt = p["whole" if choice == "whole" else "halves"]
        formulas_kept += attempt["formulas"]
        right_kept += attempt["right"]
        let_through += _wrong(attempt)
    summary["app"] = {
        "pages": len(pages),
        "kept": dict(kept),
        "formulas_in_read_pages": formulas_kept,
        "right_in_read_pages": right_kept,
        "read_pages_with_a_wrong_formula": let_through,
        "seconds_per_page": _spread([p["app"]["seconds"] for p in pages]),
    }
    return summary


def check_on_readings(pages: list[dict]) -> dict:
    """How the check judged the model's real attempts: a reading is wrong
    when any formula in it is."""
    table: dict = {}
    for name in ("whole", "halves"):
        cells: Counter = Counter()
        for p in pages:
            a = p[name]
            if not a["usable"]:
                cells["unusable"] += 1
                continue
            wrong = "wrong" if _wrong(a) else "right"
            cells[f"{wrong}_{'accepted' if a['accepted'] else 'refused'}"] += 1
        table[name] = dict(cells)
    refusals: Counter = Counter()
    for p in pages:
        for name in ("whole", "halves"):
            a = p[name]
            if a["reason"] and a["usable"] and not _wrong(a):
                refusals[a["reason"].split(":")[0]] += 1
    table["right_refused_because"] = dict(refusals)
    return table


def notation_table(pages: list[dict]) -> dict:
    """For each kind of notation: how many of the page's formulas show it,
    and how many of those each attempt read right; and of the formulas the
    app keeps, how many are right."""
    rows: dict = {k.name: Counter() for k in notation.KINDS}
    for p in pages:
        for name in ("whole", "halves"):
            a = p[name]
            for f in a.get("results", []):
                for kind in f["kinds"]:
                    rows[kind][f"{name}_formulas"] += 1
                    rows[kind][f"{name}_right"] += f["right"]
        choice = p["app"]["kept"]
        if choice != "text layer":
            for f in p["whole" if choice == "whole" else "halves"].get("results", []):
                for kind in f["kinds"]:
                    rows[kind]["kept_formulas"] += 1
                    rows[kind]["kept_right"] += f["right"]
    return {k.name: {"label": k.label, **rows[k.name]} for k in notation.KINDS}


def change_kinds(pages: list[dict]) -> dict:
    found: Counter = Counter()
    for p in pages:
        for name in ("whole", "halves"):
            for f in p[name].get("results", []):
                for c in f["changes"]:
                    found[c["kind"]] += 1
    return dict(found)


def _spread(values: list[float]) -> dict:
    if not values:
        return {}
    return {
        "median": round(statistics.median(values), 1),
        "mean": round(statistics.fmean(values), 1),
        "p95": round(metrics.percentile(values, 95), 1),
        "total": round(sum(values), 1),
    }


# --- what each step of the app takes ------------------------------------------------


def timing(built: list[Built], pages: list[dict] | None) -> dict:
    parser = PyMuPDFParser()
    parse, find, image, layer, check = [], [], [], [], []
    for b in built:
        start = time.perf_counter()
        parser.parse(b.pdf)
        parse.append((time.perf_counter() - start) / b.typeset.page_count)
        start = time.perf_counter()
        parsing.maths_pages(b.pdf)
        find.append((time.perf_counter() - start) / b.typeset.page_count)
        for page in b.pages:
            start = time.perf_counter()
            parsing.page_image(b.pdf, page)
            image.append(time.perf_counter() - start)
            start = time.perf_counter()
            page_layer = parsing.page_layer(b.pdf, page)
            layer.append(time.perf_counter() - start)
            start = time.perf_counter()
            _verdict(b.truth(page), page_layer)
            check.append(time.perf_counter() - start)
    result = {
        "parse_ms_per_page": round(1000 * statistics.median(parse), 1),
        "find_maths_ms_per_page": round(1000 * statistics.median(find), 1),
        "page_image_ms": round(1000 * statistics.median(image), 1),
        "page_layer_ms": round(1000 * statistics.median(layer), 1),
        "check_ms": round(1000 * statistics.median(check), 1),
    }
    if pages:
        per_page = statistics.median(p["app"]["seconds"] for p in pages)
        result["model_seconds_per_page"] = round(per_page, 1)
        result["hours_for_400_pages"] = round(400 * per_page / 3600, 1)
    return result


# --- finding the maths again ----------------------------------------------------------


def eval_url() -> URL:
    url = make_url(settings.database_url)
    url = url.set(database=f"{url.database}_maths_eval")
    if not (url.database or "").endswith("_maths_eval"):
        raise RuntimeError(f"Refusing to run against {url.database!r}")
    return url


async def _bytes(data: bytes):
    yield data


def ingest(
    session_factory,
    embedder: Embedder,
    built: list[Built],
    variant: str,
    replacements: dict[tuple[str, int], transcription.PageText],
) -> tuple[uuid.UUID, dict]:
    """Upload and read every lecture into an environment of its own, then
    put the variant's page texts in place as an accepted reading would be,
    and read the lecture again, as the app does after a reading."""
    with session_factory() as session:
        environment_id = environment_service.create_environment(
            session,
            EnvironmentCreate(
                name=f"Maths benchmark: {variant}", description=VARIANTS[variant]
            ),
        ).id
    reread = []
    for b in built:
        staged = asyncio.run(
            storage.stage_upload(
                _bytes(b.typeset.pdf), max_bytes=settings.max_upload_bytes
            )
        )
        with session_factory() as session:
            environment = session.get(Environment, environment_id)
            document_id = document_service.create_document(
                session, environment, staged, b.lecture.filename
            ).id
        document_service.process_document(
            session_factory, document_id, PyMuPDFParser(), embedder
        )
        mine = {
            p: t for (name, p), t in replacements.items() if name == b.lecture.filename
        }
        if not mine:
            continue
        with session_factory() as session:
            document = session.get(Document, document_id)
            for page, text in mine.items():
                session.add(
                    PageTranscription(
                        document_id=document_id,
                        sha256=document.sha256,
                        page_number=page,
                        status="accepted",
                        content=text.text,
                        blocks=[[x.start, x.end, x.is_heading] for x in text.blocks],
                        reason=None,
                        attempts=1,
                        model=f"benchmark:{variant}",
                        prompt_version=maths_readings.PROMPT_ID,
                        seconds=0.0,
                    )
                )
            document.status = "uploaded"
            session.commit()
        start = time.perf_counter()
        document_service.process_document(
            session_factory, document_id, PyMuPDFParser(), embedder
        )
        reread.append(time.perf_counter() - start)
    with session_factory() as session:
        ready = session.scalars(
            select(Document).where(Document.environment_id == environment_id)
        ).all()
        if any(d.status != "ready" for d in ready):
            raise RuntimeError(f"{variant}: a lecture was not read")
    return environment_id, {"seconds_to_read_again": round(sum(reread), 2)}


def _passages(session_factory, environment_id) -> dict[str, tuple[uuid.UUID, Passage]]:
    with session_factory() as session:
        rows = session.execute(
            select(
                DocumentChunk.id,
                Document.filename,
                DocumentChunk.ordinal,
                DocumentChunk.content,
            )
            .join(Document)
            .where(Document.environment_id == environment_id)
        ).all()
    return {
        benchmark.label(filename, ordinal): (
            chunk_id,
            Passage(filename, ordinal, content),
        )
        for chunk_id, filename, ordinal, content in rows
    }


def retrieval(
    session_factory,
    environment_id,
    embedder: Embedder,
    reranker: Reranker,
    questions: list[maths_dataset.Question],
) -> tuple[dict, list[dict]]:
    stored = _passages(session_factory, environment_id)
    among = [p for _, p in stored.values()]
    by_id = {chunk_id: name for name, (chunk_id, _) in stored.items()}
    sizes = RetrievalSizes.from_settings(final_k=K)
    rows: list[dict] = []
    for q in questions:
        relevant: set[str] = set()
        for part in q.evidence:
            for e in part.quotes():
                for p in maths_dataset.holding(e.quote, e.document, among):
                    relevant.add(benchmark.label(p.document, p.ordinal))
        if not relevant:
            raise RuntimeError(f"{q.id}: its evidence is in no passage")
        rows.append(
            {
                "id": q.id,
                "kind": q.kind,
                "question": q.question,
                "evidence": sorted(relevant),
                "methods": {},
            }
        )
    for method in benchmark.METHODS:
        benchmark.search(
            method,
            session_factory,
            environment_id,
            "determinant of a matrix",
            embedder,
            reranker,
            sizes,
        )
        for q, row in zip(questions, rows, strict=True):
            ids = benchmark.search(
                method,
                session_factory,
                environment_id,
                q.question,
                embedder,
                reranker,
                sizes,
            )
            ranking = [by_id[i] for i in ids]
            relevant = set(row["evidence"])
            row["methods"][method] = {
                "recall@5": metrics.recall_at(ranking, [relevant], 5),
                "recall@10": metrics.recall_at(ranking, [relevant], 10),
                "rr": metrics.reciprocal_rank(ranking, relevant, K),
                "hit@1": metrics.hit_at_1(ranking, relevant),
                "top3": ranking[:3],
            }
    summary = {}
    for method, name in benchmark.METHODS.items():
        scores = [{"kind": r["kind"], **r["methods"][method]} for r in rows]
        summary[method] = {
            "name": name,
            **{
                s: metrics.by_kind(scores, s)
                for s in ("recall@5", "recall@10", "rr", "hit@1")
            },
        }
    return summary, rows


def latex_words(session_factory, environment_id) -> dict:
    """How often LaTeX's commands and environment names, which the keyword
    index keeps as words (record 24), occur in the stored passages."""
    with session_factory() as session:
        contents = session.scalars(
            select(DocumentChunk.content)
            .join(Document)
            .where(Document.environment_id == environment_id)
        ).all()
    commands: Counter = Counter()
    environments: Counter = Counter()
    for content in contents:
        environments.update(re.findall(r"\\begin\{([A-Za-z*]+)\}", content))
        commands.update(
            c
            for c in re.findall(r"\\([A-Za-z]+)", content)
            if c not in ("begin", "end")
        )
        if "\\begin{" in content:
            commands["begin"] += content.count("\\begin{")
    return {
        "passages": len(contents),
        "commands": dict(commands.most_common(12)),
        "environments": dict(environments.most_common(8)),
    }


# --- practice -----------------------------------------------------------------------


def practice(session_factory, environment_id, llm: LLMProvider) -> dict:
    """The app's concept extraction and exercise choice on the lectures as
    read, each choice judged against the exercise types the lecture of its
    passages teaches."""
    from app.models import Concept
    from app.services import concepts as concept_service
    from app.services import practice as practice_service
    from app.services import sources

    labels = json.loads(EXERCISE_LABELS.read_text(encoding="utf-8"))["lectures"]
    with session_factory() as session:
        documents = session.scalars(
            select(Document).where(Document.environment_id == environment_id)
        ).all()
        artifacts = [
            concept_service.request_extraction(session, d, llm)[0].id for d in documents
        ]
    start = time.perf_counter()
    for artifact_id in artifacts:
        concept_service.write_extraction(session_factory, artifact_id, llm)
    extraction_seconds = time.perf_counter() - start
    rows = []
    start = time.perf_counter()
    with session_factory() as session:
        concepts = session.scalars(
            select(Concept).where(Concept.environment_id == environment_id)
        ).all()
        evidence = practice_service.evidence(session, [c.id for c in concepts])
        filenames = {d.id: d.filename for d in documents}
        for concept in concepts:
            chunks = evidence.get(concept.id, [])
            passages = [
                practice_service._Passage(
                    n, c.id, c.document_id, sources.with_heading(c)
                )
                for n, c in enumerate(chunks, start=1)
            ]
            chosen, refused = practice_service._exercises(
                concept.name, concept.definition, passages, llm
            )
            lectures = sorted({filenames[c.document_id] for c in chunks})
            fitting = {kind for name in lectures for kind in labels.get(name, [])}
            rows.append(
                {
                    "concept": concept.name,
                    "lectures": lectures,
                    "offered": [kind for kind, _ in chosen],
                    "refused_by_words": refused,
                    "fit": [kind for kind, _ in chosen if kind in fitting],
                    "misfit": [kind for kind, _ in chosen if kind not in fitting],
                    "teachable": sorted(fitting),
                }
            )
    choosing_seconds = time.perf_counter() - start
    offered = [k for r in rows for k in r["offered"]]
    misfits = [k for r in rows for k in r["misfit"]]
    taught = {(name, kind) for name, kinds in labels.items() for kind in kinds}
    reached = {
        (name, kind) for r in rows for name in r["lectures"] for kind in r["fit"]
    }
    return {
        "model": llm.model_name,
        "concepts": len(rows),
        "concepts_with_an_exercise": sum(bool(r["offered"]) for r in rows),
        "exercises_offered": len(offered),
        "exercises_that_fit": len(offered) - len(misfits),
        "lecture_types_taught": len(taught),
        "lecture_types_offered": len(taught & reached),
        "seconds_extracting": round(extraction_seconds, 1),
        "seconds_choosing": round(choosing_seconds, 1),
        "rows": rows,
    }


# --- the run ----------------------------------------------------------------------------


def slimmed(results: dict) -> dict:
    """The results as written: each attempt keeps only the formulas it read
    wrong. Every count and table is made before, from all of them."""
    pages = [
        {
            **page,
            **{
                name: {
                    **page[name],
                    "results": [
                        f for f in page[name].get("results", []) if not f["right"]
                    ],
                }
                for name in ("whole", "halves")
            },
        }
        for page in results["reading"]["pages"]
    ]
    return {**results, "reading": {**results["reading"], "pages": pages}}


FINGERPRINTED = (
    "docs/evaluation/maths/corpus/*.md",
    "docs/evaluation/maths/questions.json",
    "docs/evaluation/maths/exercise-labels.json",
    "docs/evaluation/maths/readings.json",
    "api/app/**/*.py",
    "api/app/prompts/**/*.txt",
    "api/evaluation/**/*.py",
    "api/requirements.txt",
)


def fingerprint() -> str:
    digest = hashlib.sha256()
    paths = sorted({p for pattern in FINGERPRINTED for p in ROOT.glob(pattern)})
    for path in paths:
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def run_details(llm_name: str) -> dict:
    details = benchmark.run_details()
    details["fingerprint"] = fingerprint()
    details["reviewed"] = maths_dataset.reviewed()
    details["tectonic"] = maths_corpus.tectonic_version()
    details["model"] = llm_name
    details["prompt"] = maths_readings.PROMPT_ID
    details["pymupdf"] = pymupdf.VersionBind
    return details


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the maths benchmark.")
    parser.add_argument(
        "--read",
        action="store_true",
        help="ask the local model to read any page it has not read (about 40 s a part)",
    )
    parser.add_argument(
        "--practice",
        action="store_true",
        help="also extract concepts and choose exercises with the local model (about 20 minutes)",
    )
    parser.add_argument(
        "--no-retrieval", action="store_true", help="skip the search questions"
    )
    args = parser.parse_args(argv)

    questions = maths_dataset.load()
    problems = maths_dataset.problems(questions)
    if problems:
        print("The questions have problems; nothing was measured:")
        for problem in problems:
            print(" -", problem)
        return 1

    print(f"Inputs fingerprint {fingerprint()}")
    previous = (
        json.loads(RESULTS.read_text(encoding="utf-8")) if RESULTS.exists() else {}
    )
    llm = default_provider()
    with tempfile.TemporaryDirectory() as folder:
        settings.data_dir = Path(folder) / "data"
        print("Typesetting the lectures with Tectonic …")
        built, typeset_seconds = typeset_all(Path(folder))
        stats = corpus_stats(built)
        print(
            f"  {stats['lectures']} lectures, {stats['pages']} pages, {stats['formulas']} formulas"
        )

        print("Checking each page's perfect reading, and planting mistakes in it …")
        truth = truth_check(built)
        passing = {(r["lecture"], r["page"]) for r in truth if r["reason"] is None}
        planted_ = planted(built, passing)

        pdfs = {b.lecture.filename: b.pdf for b in built}
        if args.read:
            print("Reading the pages with the local model, where not read already …")
            readings = maths_readings.read_all(pdfs, llm)
        else:
            readings = maths_readings.load()
        print("Scoring the model's readings …")
        pages = score_readings(built, readings)

        results: dict = {
            "run": run_details(llm.model_name),
            "corpus": stats,
            "typesetting_seconds": typeset_seconds,
            "truth": {"pages": len(truth), "accepted": len(passing), "rows": truth},
            "planted": planted_,
            "reading": {
                "summary": reading_summary(pages),
                "check": check_on_readings(pages),
                "notation": notation_table(pages),
                "changes": change_kinds(pages),
                "pages": pages,
            },
            "timing": timing(built, pages),
            "retrieval": previous.get("retrieval"),
            "practice": previous.get("practice"),
        }

        if not args.no_retrieval or args.practice:
            url = eval_url()
            print(f"Rebuilding {url.database} and reading the lectures three ways …")
            benchmark.rebuild(url)
            engine = create_engine(url)
            session_factory = sessionmaker(engine, expire_on_commit=False)
            embedder, reranker = default_embedder(), default_reranker()
            texts: dict[str, dict] = {"layer": {}, "read": {}, "truth": {}}
            for b in built:
                for page in b.pages:
                    key = (b.lecture.filename, page)
                    layer = parsing.page_layer(b.pdf, page)
                    texts["truth"][key] = stored_truth(b.truth(page), layer)
            for p in pages:
                choice = p["app"]["kept"]
                if choice == "text layer":
                    continue
                parts = ("whole",) if choice == "whole" else ("top", "bottom")
                answers = [
                    r
                    for r in readings
                    if (r.lecture, r.page) == (p["lecture"], p["page"])
                    and r.part in parts
                ]
                answers.sort(key=lambda r: maths_readings.PARTS.index(r.part))
                b = next(x for x in built if x.lecture.filename == p["lecture"])
                joined = "\n\n".join(
                    transcription.without_chatter(r.answer).strip() for r in answers
                )
                texts["read"][(p["lecture"], p["page"])] = transcription.page_text(
                    joined, parsing.page_layer(b.pdf, p["page"])
                )
            environments, variant_stats = {}, {}
            for variant in VARIANTS:
                environments[variant], variant_stats[variant] = ingest(
                    session_factory, embedder, built, variant, texts[variant]
                )
            if not args.no_retrieval:
                retrieval_: dict = {"variants": {}, "questions": {}}
                for variant, name in VARIANTS.items():
                    print(f"  Asking {len(questions)} questions of: {name} …")
                    summary, rows = retrieval(
                        session_factory,
                        environments[variant],
                        embedder,
                        reranker,
                        questions,
                    )
                    retrieval_["variants"][variant] = {
                        "name": name,
                        "methods": summary,
                        "latex_words": latex_words(
                            session_factory, environments[variant]
                        ),
                        **variant_stats[variant],
                    }
                    retrieval_["questions"][variant] = rows
                results["retrieval"] = retrieval_
            if args.practice:
                print(
                    "Extracting concepts and choosing exercises with the local model …"
                )
                results["practice"] = practice(
                    session_factory, environments["read"], llm
                )
            engine.dispose()

    RESULTS.write_text(
        json.dumps(slimmed(results), indent=1, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {RESULTS.relative_to(ROOT)}")
    from evaluation import maths_report

    if REPORT.exists():
        REPORT.write_text(
            maths_report.update(REPORT.read_text(encoding="utf-8"), results),
            encoding="utf-8",
        )
        print(f"Updated the tables in {REPORT.relative_to(ROOT)}")
    print()
    print(maths_report.headline(results))
    return 0
