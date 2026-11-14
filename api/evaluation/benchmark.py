"""The benchmark: retrieval and generation, measured on the corpus.

Purpose
-------
Every number in docs/evaluation/ comes from a run of this module, through
scripts/evaluate_retrieval.py; none is typed by hand. A run:

1. rebuilds its own database, the development database's name with _eval
   appended, from the migrations, and keeps uploads in a temporary folder,
   so neither development nor test data is touched;
2. uploads the ten corpus documents as PDFs and reads them with the app's
   own parser, chunker and embedding model, exactly as an upload would;
3. finds each question's evidence among the stored passages by its quotes;
4. asks every question through each method, ROUNDS times, and scores the
   first run's ranking (the rankings do not change between rounds) while
   timing all of them; steps 1 to 4 are repeated BUILDS times, because a
   fresh build can break ties between passages differently;
5. with --generation, has the local language model write each document's
   summary as the app does, and judges it: the reranker scores each key
   point against each passage it cites, and a summary covers a key fact when
   it contains the fact's words;
6. writes docs/evaluation/results.json and rewrites only the tables between
   markers in docs/evaluation/retrieval-benchmark.md.

The four methods, each returning its best K passages:

- semantic: vector search alone;
- lexical: keyword search alone;
- hybrid: both searches, merged by Reciprocal Rank Fusion, as the app does
  before reranking;
- hybrid_rerank: the app's search, with the reranker reading the best
  merged passages.

Hybrid and hybrid_rerank use the app's own settings for how many passages
each stage considers.
"""

import argparse
import asyncio
import hashlib
import json
import platform
import random
import subprocess
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import URL, create_engine, func, make_url, select, text
from sqlalchemy.orm import sessionmaker

from app import storage
from app.config import settings
from app.embedding import Embedder, default_embedder
from app.llm import default_provider
from app.models import Document, DocumentChunk, Environment, GeneratedArtifact
from app.parsing import PyMuPDFParser
from app.reranking import Reranker, default_reranker
from app.schemas import EnvironmentCreate
from app.services import documents as document_service
from app.services import environments as environment_service
from app.services import summaries as summary_service
from app.services.practice import MIN_SUPPORT
from app.services.search import (
    RetrievalSizes,
    hybrid_search,
    keyword_search,
    reciprocal_rank_fusion,
    semantic_search,
)
from evaluation import corpus, dataset, metrics, report

API_DIR = Path(__file__).resolve().parents[1]
RESULTS = corpus.ROOT / "docs" / "evaluation" / "results.json"
REPORT = corpus.ROOT / "docs" / "evaluation" / "retrieval-benchmark.md"
JUDGE_REVIEW = corpus.ROOT / "docs" / "evaluation" / "judge-review.json"

K = 10  # results each method returns; Recall@10 and MRR@10 read all of them
ROUNDS = 3  # each question is asked this many times per method, for timing
# The corpus is read into a fresh database this many times: passages that tie
# are ordered by ids that are new for every upload (see combine).
BUILDS = 3
# Asked once per method before timing, so loading the models and warming the
# database's caches is not counted against the first question.
WARM_UP = "How does an operating system share the processor between programs?"
CALIBRATION = 30  # key point and citation pairs set aside for review
SEED = 2026  # the calibration sample is drawn the same way every run

METHODS = {
    "semantic": "A. Semantic",
    "lexical": "B. Lexical",
    "hybrid": "C. Hybrid (fused)",
    "hybrid_rerank": "D. Hybrid + reranker (the app)",
}


# --- the database --------------------------------------------------------------


def eval_url() -> URL:
    url = make_url(settings.database_url)
    url = url.set(database=f"{url.database}_eval")
    if not (url.database or "").endswith("_eval"):
        raise RuntimeError(f"Refusing to run against {url.database!r}")
    return url


def rebuild(url: URL) -> None:
    """Drop the benchmark's database if it exists, create it empty, and build
    it from the migrations alone."""
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(
            text(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)')
        )
        connection.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()
    config = Config(str(API_DIR / "alembic.ini"))
    config.attributes["database_url"] = url.render_as_string(hide_password=False)
    command.upgrade(config, "head")


# --- ingestion -----------------------------------------------------------------


async def _bytes(data: bytes):
    yield data


def ingest(session_factory, parser, embedder: Embedder) -> tuple[uuid.UUID, dict]:
    """Upload and read every corpus document; return the environment and what
    was stored."""
    with session_factory() as session:
        environment = environment_service.create_environment(
            session,
            EnvironmentCreate(
                name="Operating systems (benchmark)",
                description="The evaluation corpus, docs/evaluation/corpus/.",
            ),
        )
        environment_id = environment.id
    reading = []
    for source in corpus.documents():
        data = corpus.to_pdf(source.text)
        staged = asyncio.run(
            storage.stage_upload(_bytes(data), max_bytes=settings.max_upload_bytes)
        )
        with session_factory() as session:
            environment = session.get(Environment, environment_id)
            document = document_service.create_document(
                session, environment, staged, source.filename
            )
            document_id = document.id
        start = time.perf_counter()
        document_service.process_document(
            session_factory, document_id, parser, embedder
        )
        reading.append(time.perf_counter() - start)
        with session_factory() as session:
            document = session.get(Document, document_id)
            if document.status != "ready":
                raise RuntimeError(f"{source.filename} was not read: {document.error}")
    with session_factory() as session:
        documents = session.scalars(
            select(Document).where(Document.environment_id == environment_id)
        ).all()
        passages = session.scalar(
            select(func.count(DocumentChunk.id))
            .join(Document)
            .where(Document.environment_id == environment_id)
        )
        stats = {
            "documents": len(documents),
            "pages": sum(d.page_count or 0 for d in documents),
            "passages": passages,
            "words": sum(len(s.text.split()) for s in corpus.documents()),
            "seconds_to_read_and_embed": round(sum(reading), 2),
        }
    return environment_id, stats


def stored_passages(
    session_factory, environment_id
) -> dict[str, tuple[uuid.UUID, dataset.Passage]]:
    """Every stored passage, by a readable label such as 03#4 (document 03,
    passage 4)."""
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
        label(filename, ordinal): (
            chunk_id,
            dataset.Passage(filename, ordinal, content),
        )
        for chunk_id, filename, ordinal, content in rows
    }


def label(filename: str, ordinal: int) -> str:
    return f"{filename[:2]}#{ordinal}"


def evidence_of(question: dataset.Question, stored) -> list[list[str]]:
    """For each part of the question's answer, the labels of the passages
    holding its quotes. Fails if a quote is not in exactly one stored
    passage: a label that does not resolve must stop the run, not score as
    a miss."""
    passages = [p for _, p in stored.values()]
    parts = []
    for part in question.evidence:
        found = []
        for evidence in part.quotes():
            places = dataset.holding(evidence.quote, evidence.document, passages)
            if len(places) != 1:
                raise RuntimeError(f"{question.id}: quote in {len(places)} passages")
            found.append(label(places[0].document, places[0].ordinal))
        parts.append(found)
    return parts


# --- retrieval -------------------------------------------------------------------


def search(
    method: str, session_factory, environment_id, query, embedder, reranker, sizes
) -> list[uuid.UUID]:
    """One method's best K passages for the query, best first."""
    with session_factory() as session:
        if method == "semantic":
            ids = [
                h.chunk.id
                for h in semantic_search(session, environment_id, query, embedder, K)
            ]
        elif method == "lexical":
            ids = [
                h.chunk.id for h in keyword_search(session, environment_id, query, K)
            ]
        elif method == "hybrid":
            lexical = keyword_search(
                session, environment_id, query, sizes.top_k_lexical
            )
            dense = semantic_search(
                session, environment_id, query, embedder, sizes.top_k_dense
            )
            fused = reciprocal_rank_fusion(
                [[h.chunk.id for h in lexical], [h.chunk.id for h in dense]]
            )
            ids = [chunk_id for chunk_id, _ in fused[:K]]
        elif method == "hybrid_rerank":
            result = hybrid_search(
                session, environment_id, query, embedder, reranker, sizes
            )
            ids = [c.chunk.id for c in result.results]
        else:
            raise ValueError(method)
        session.rollback()
    return ids


def retrieval(
    session_factory, environment_id, embedder: Embedder, reranker: Reranker
) -> tuple[dict, list[dict]]:
    questions = dataset.load_questions()
    stored = stored_passages(session_factory, environment_id)
    by_id = {chunk_id: name for name, (chunk_id, _) in stored.items()}
    sizes = RetrievalSizes.from_settings(final_k=K)
    rows = [
        {
            "id": q.id,
            "kind": q.kind,
            "question": q.question,
            "evidence": evidence_of(q, stored),
            "methods": {},
        }
        for q in questions
    ]
    for method in METHODS:
        search(
            method, session_factory, environment_id, WARM_UP, embedder, reranker, sizes
        )
        for q, row in zip(questions, rows, strict=True):
            times, ranking = [], None
            for _ in range(ROUNDS):
                start = time.perf_counter()
                ids = search(
                    method,
                    session_factory,
                    environment_id,
                    q.question,
                    embedder,
                    reranker,
                    sizes,
                )
                times.append(time.perf_counter() - start)
                ranking = ranking if ranking is not None else [by_id[i] for i in ids]
            parts = [set(part) for part in row["evidence"]]
            relevant = set().union(*parts)
            row["methods"][method] = {
                "recall@5": metrics.recall_at(ranking, parts, 5),
                "recall@10": metrics.recall_at(ranking, parts, 10),
                "rr": metrics.reciprocal_rank(ranking, relevant, K),
                "hit@1": metrics.hit_at_1(ranking, relevant),
                "ranks": {
                    e: (ranking.index(e) + 1 if e in ranking else None)
                    for e in sorted(relevant)
                },
                "top5": ranking[:5],
                "ms": round(1000 * metrics.percentile(times, 50), 2),
            }
    summary = {}
    for method, name in METHODS.items():
        scores = [{"kind": r["kind"], **r["methods"][method]} for r in rows]
        times = [s["ms"] for s in scores]
        summary[method] = {
            "name": name,
            **{
                score: metrics.by_kind(scores, score)
                for score in ("recall@5", "recall@10", "rr", "hit@1")
            },
            "latency_ms": {
                "p50": round(metrics.percentile(times, 50), 1),
                "p95": round(metrics.percentile(times, 95), 1),
                "mean": round(metrics.mean(times), 1),
            },
        }
    return summary, rows


# --- generation ------------------------------------------------------------------


def generation(session_factory, environment_id, reranker: Reranker) -> dict:
    """Each document's summary, written by the local model as the app writes
    it, and judged."""
    llm = default_provider()
    facts = dataset.load_key_facts()
    stored = stored_passages(session_factory, environment_id)
    content_of = {chunk_id: p.content for chunk_id, p in stored.values()}
    name_of = {chunk_id: name for name, (chunk_id, _) in stored.items()}
    with session_factory() as session:
        documents = [
            (d.id, d.filename)
            for d in session.scalars(
                select(Document)
                .where(Document.environment_id == environment_id)
                .order_by(Document.filename)
            )
        ]
    results = []
    for document_id, filename in documents:
        with session_factory() as session:
            document = session.get(Document, document_id)
            artifact, write_now = summary_service.request_summary(
                session, document, llm
            )
            artifact_id = artifact.id
        start = time.perf_counter()
        if write_now:
            summary_service.write_summary(session_factory, artifact_id, llm)
        seconds = time.perf_counter() - start
        with session_factory() as session:
            artifact = session.get(GeneratedArtifact, artifact_id)
            status, error, content = (
                artifact.status,
                artifact.error,
                artifact.content or {},
            )
        entry = {"document": filename, "status": status, "seconds": round(seconds, 1)}
        if status != "ready":
            entry["error"] = error
            results.append(entry)
            continue
        points = []
        for kp in content.get("key_points", []):
            cited = [uuid.UUID(c["chunk_id"]) for c in kp["citations"]]
            scores = (
                reranker.score(kp["text"], [content_of[c] for c in cited])
                if cited
                else []
            )
            points.append(
                {
                    "text": kp["text"],
                    "citations": [
                        {
                            "passage": name_of[c],
                            "score": round(s, 3),
                            "supported": s >= MIN_SUPPORT,
                        }
                        for c, s in zip(cited, scores, strict=True)
                    ],
                }
            )
        whole = " ".join([content.get("overview") or "", *(p["text"] for p in points)])
        own = [f for f in facts if f.document == filename]
        entry.update(
            {
                "overview": content.get("overview"),
                "key_points": points,
                "facts": {f.id: dataset.covers(whole, f) for f in own},
            }
        )
        results.append(entry)
    return {
        "documents": results,
        "scores": generation_scores(results),
        "llm": llm.model_name,
    }


def generation_scores(documents: list[dict]) -> dict:
    written = [d for d in documents if d["status"] == "ready"]
    judged = [
        [c["supported"] for c in p["citations"]]
        for d in written
        for p in d["key_points"]
    ]
    cited = [j for j in judged if j]
    return {
        "summaries": len(documents),
        "written": len(written),
        "key_points": len(judged),
        "key_points_without_citations": len(judged) - len(cited),
        "citations": sum(len(j) for j in judged),
        "citation_correctness": metrics.citation_correctness(cited) if cited else None,
        # A key point that cites nothing is not grounded.
        "groundedness": metrics.groundedness(judged) if judged else None,
        "completeness": (
            metrics.completeness([c for d in written for c in d["facts"].values()])
            if written
            else None
        ),
        "seconds_per_summary": {
            "p50": round(metrics.percentile([d["seconds"] for d in documents], 50), 1),
            "max": round(max(d["seconds"] for d in documents), 1),
        },
    }


def rescore(generation_: dict) -> dict:
    """Stored summaries scored again against the current key facts. The
    summaries are not written again, and the citations keep the judge's
    scores from the run that wrote them."""
    facts = dataset.load_key_facts()
    for d in generation_["documents"]:
        if d["status"] != "ready":
            continue
        whole = " ".join(
            [d.get("overview") or "", *(p["text"] for p in d["key_points"])]
        )
        d["facts"] = {
            f.id: dataset.covers(whole, f) for f in facts if f.document == d["document"]
        }
    generation_["scores"] = generation_scores(generation_["documents"])
    return generation_


def calibration_sample(documents: list[dict], stored: dict) -> list[dict]:
    """Key point and citation pairs for a person to judge, half the judge
    said were supported and half it said were not, as far as there are
    enough of each, drawn the same way every run."""
    pairs = [
        {
            "document": d["document"],
            "point": p["text"],
            "passage": c["passage"],
            "passage_text": stored[c["passage"]][1].content,
            "score": c["score"],
            "judge_supported": c["supported"],
        }
        for d in documents
        if d["status"] == "ready"
        for p in d["key_points"]
        for c in p["citations"]
    ]
    rng = random.Random(SEED)
    supported = [p for p in pairs if p["judge_supported"]]
    unsupported = [p for p in pairs if not p["judge_supported"]]
    half = CALIBRATION // 2
    take_unsupported = min(half, len(unsupported))
    take_supported = min(CALIBRATION - take_unsupported, len(supported))
    sample = rng.sample(unsupported, take_unsupported) + rng.sample(
        supported, take_supported
    )
    rng.shuffle(sample)
    return [{"id": f"j{n:02d}", **pair} for n, pair in enumerate(sample, start=1)]


def judge_agreement(
    sample: list[dict], scores: dict, path: Path = JUDGE_REVIEW
) -> dict | None:
    """How often the judge agreed with the review of the sample, once there
    is a review of this very sample, and the share of all citations the
    review would likely have called supported.

    The sample over-represents the citations the judge rejected, so its
    agreement is not the judge's accuracy over all citations. The estimate
    corrects for that: within each of the judge's two verdicts, the share
    the review called supported, weighted by how many of all citations the
    judge gave that verdict."""
    if not path.exists():
        return None
    review = json.loads(path.read_text(encoding="utf-8"))
    verdicts = {(r["point"], r["passage"]): r["supported"] for r in review["pairs"]}
    matched = [p for p in sample if (p["point"], p["passage"]) in verdicts]
    if len(matched) != len(sample):
        return {
            "reviewed_by": review.get("reviewed_by"),
            "matched": len(matched),
            "of": len(sample),
        }
    agree = [
        p["judge_supported"] == verdicts[(p["point"], p["passage"])] for p in matched
    ]
    said_yes = [p for p in matched if p["judge_supported"]]
    said_no = [p for p in matched if not p["judge_supported"]]

    def review_yes(pairs: list[dict]) -> float | None:
        if not pairs:
            return None
        return metrics.mean(
            1.0 if verdicts[(p["point"], p["passage"])] else 0.0 for p in pairs
        )

    judge_share = scores.get("citation_correctness")
    yes_rate, no_rate = review_yes(said_yes), review_yes(said_no)
    estimate = (
        judge_share * yes_rate + (1 - judge_share) * no_rate
        if None not in (judge_share, yes_rate, no_rate)
        else None
    )
    return {
        "judge_said_supported": len(said_yes),
        "judge_said_unsupported": len(said_no),
        "review_supported_when_judge_said_supported": yes_rate,
        "review_supported_when_judge_said_unsupported": no_rate,
        "estimated_citation_correctness": estimate,
        "reviewed_by": review.get("reviewed_by"),
        "pairs": len(matched),
        "agreement": metrics.mean(1.0 if a else 0.0 for a in agree),
        "judge_too_lenient": sum(
            p["judge_supported"] and not verdicts[(p["point"], p["passage"])]
            for p in matched
        ),
        "judge_too_strict": sum(
            not p["judge_supported"] and verdicts[(p["point"], p["passage"])]
            for p in matched
        ),
    }


# --- the run, and its record -------------------------------------------------------


# The files whose contents decide the results: the dataset, the app, the
# benchmark and the pinned dependencies. Their fingerprint tells whether a
# rerun used the same inputs.
FINGERPRINTED = (
    "docs/evaluation/corpus/*.md",
    "docs/evaluation/questions.json",
    "docs/evaluation/key-facts.json",
    "api/app/**/*.py",
    "api/evaluation/**/*.py",
    "api/requirements.txt",
)


def fingerprint() -> str:
    digest = hashlib.sha256()
    paths = sorted({p for pattern in FINGERPRINTED for p in corpus.ROOT.glob(pattern)})
    for path in paths:
        digest.update(path.relative_to(corpus.ROOT).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def run_details() -> dict:
    def git(*args) -> str:
        return subprocess.run(
            ["git", *args], cwd=corpus.ROOT, capture_output=True, text=True, check=False
        ).stdout.strip()

    try:
        memory = int(
            subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True,
                text=True,
                check=False,
            ).stdout
        )
        memory_gb = round(memory / 1024**3)
    except ValueError:
        memory_gb = None
    try:
        chip = (
            subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True,
                text=True,
                check=False,
            ).stdout.strip()
            or platform.processor()
        )
    except OSError:
        chip = platform.processor()
    return {
        "date": datetime.now(UTC).isoformat(timespec="seconds"),
        "commit": git("rev-parse", "--short", "HEAD"),
        "fingerprint": fingerprint(),
        "uncommitted_changes": bool(git("status", "--porcelain")),
        "machine": {
            "system": platform.platform(),
            "processor": chip,
            "memory_gb": memory_gb,
            "python": platform.python_version(),
        },
        "embedding_model": settings.embedding_model,
        "rerank_model": settings.rerank_model,
        "reviewed": dataset.reviewed(),
    }


def combine(builds: list[tuple[dict, list[dict]]]) -> tuple[dict, list[dict]]:
    """The builds' scores together. Passages that tie are ordered by their
    ids, and ids are new for every upload, so a tie can fall either way in a
    fresh build, as it can in the app. Each score is the mean over the
    builds, with the lowest and highest build's overall score beside it;
    latency is taken over every build's questions. The questions keep the
    first build's rankings, and each method's reciprocal rank in every
    build."""
    combined = {}
    for method, name in METHODS.items():
        entry: dict = {"name": name}
        for score in ("recall@5", "recall@10", "rr", "hit@1"):
            per_build = [summary[method][score] for summary, _ in builds]
            entry[score] = {
                kind: metrics.mean(b[kind] for b in per_build) for kind in per_build[0]
            }
            overall = [b["all"] for b in per_build]
            entry[f"{score} range"] = [min(overall), max(overall)]
        times = [r["methods"][method]["ms"] for _, rows in builds for r in rows]
        entry["latency_ms"] = {
            "p50": round(metrics.percentile(times, 50), 1),
            "p95": round(metrics.percentile(times, 95), 1),
            "mean": round(metrics.mean(times), 1),
        }
        combined[method] = entry
    rows = builds[0][1]
    for i, row in enumerate(rows):
        for method in METHODS:
            row["methods"][method]["rr_by_build"] = [
                b[1][i]["methods"][method]["rr"] for b in builds
            ]
    return combined, rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the retrieval and generation benchmark."
    )
    parser.add_argument(
        "--generation",
        action="store_true",
        help="also have the local model write and judge each document's summary (about five more minutes)",
    )
    args = parser.parse_args(argv)

    problems = dataset.problems(dataset.load_questions(), dataset.passages())
    problems += dataset.fact_problems(dataset.load_key_facts())
    if problems:
        print("The dataset has problems; nothing was measured:")
        for problem in problems:
            print(" -", problem)
        return 1

    print(f"Inputs fingerprint {fingerprint()}")
    url = eval_url()
    embedder, reranker = default_embedder(), default_reranker()
    previous = (
        json.loads(RESULTS.read_text(encoding="utf-8")) if RESULTS.exists() else {}
    )
    questions = len(dataset.load_questions())
    builds = []
    engine = None

    with tempfile.TemporaryDirectory() as folder:
        settings.data_dir = Path(folder)
        for n in range(1, BUILDS + 1):
            if engine is not None:
                engine.dispose()
            print(
                f"Build {n} of {BUILDS}: rebuilding {url.database} and reading the corpus …"
            )
            rebuild(url)
            engine = create_engine(url)
            session_factory = sessionmaker(engine, expire_on_commit=False)
            environment_id, stats = ingest(session_factory, PyMuPDFParser(), embedder)
            print(
                f"  {stats['documents']} documents, {stats['pages']} pages, "
                f"{stats['passages']} passages; asking {questions} questions "
                f"{ROUNDS} times each by {len(METHODS)} methods …"
            )
            builds.append(
                retrieval(session_factory, environment_id, embedder, reranker)
            )
        summary, rows = combine(builds)
        results = {
            "retrieval": {
                "run": run_details(),
                "corpus": stats,
                "sizes": vars(RetrievalSizes.from_settings(final_k=K)),
                "k": K,
                "rounds": ROUNDS,
                "builds": BUILDS,
                "methods": summary,
                "questions": rows,
            },
            "generation": previous.get("generation"),
        }
        if args.generation:
            print("Writing and judging each document's summary with the local model …")
            written = generation(session_factory, environment_id, reranker)
            stored = stored_passages(session_factory, environment_id)
            sample = calibration_sample(written["documents"], stored)
            results["generation"] = {
                "run": run_details(),
                "support_threshold": MIN_SUPPORT,
                **written,
                "calibration": sample,
                "judge_agreement": judge_agreement(sample, written["scores"]),
            }
        elif results["generation"]:
            # Kept from the run that wrote it, whose run details say when;
            # only scored again, against the current key facts and review.
            generation_ = rescore(results["generation"])
            generation_["judge_agreement"] = judge_agreement(
                generation_["calibration"], generation_["scores"]
            )
    engine.dispose()

    RESULTS.write_text(
        json.dumps(results, indent=2, default=str) + "\n", encoding="utf-8"
    )
    print(f"Wrote {RESULTS.relative_to(corpus.ROOT)}")
    if REPORT.exists():
        REPORT.write_text(
            report.update(REPORT.read_text(encoding="utf-8"), results), encoding="utf-8"
        )
        print(f"Updated the tables in {REPORT.relative_to(corpus.ROOT)}")
    print()
    print(report.retrieval_table(results))
    return 0
