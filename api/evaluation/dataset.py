"""The benchmark's questions and key facts, and the checks they must pass.

Purpose
-------
Each question names the passages that answer it by quoting them exactly from
the corpus. A question has one part, or two for a question needing two
passages, and a part can also name alternative quotes: another passage that
answers that part just as well. Quoting, rather than naming chunk ids, keeps the labels valid
when the chunker changes: at run time each quote is found in whichever
passage now holds it. The checks here make sure every label means what it
says before any number is computed from it:

- every quote appears exactly once in the whole corpus, and inside exactly
  one passage of the document it names, as the app's own parser and chunker
  cut it;
- a question needing two passages names two different passages;
- a term question contains its term, and so does its evidence;
- a question in other words avoids the words listed for it, so it cannot be
  answered by matching them.

Key facts are what a summary of each document should cover. Each lists the
words that show it is covered: every group must be matched by at least one
of its alternatives. A word matches only where a word of the text begins
with it: "opt" matches "optimal" but not "adopt". Ending a word with a space,
as in "exec ", stops it matching longer words such as "execution".
"""

import json
import re
import tempfile
import uuid
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from app.chunking import chunk_document
from app.parsing import PyMuPDFParser
from evaluation import corpus

QUESTIONS = corpus.ROOT / "docs" / "evaluation" / "questions.json"
KEY_FACTS = corpus.ROOT / "docs" / "evaluation" / "key-facts.json"
KINDS = {"term": 25, "meaning": 30, "mixed": 10, "multi": 15}


@dataclass(frozen=True)
class Evidence:
    """One part of a question's answer: a quote, and any alternative quotes
    from other passages that answer the same part."""

    document: str
    quote: str
    also: tuple["Evidence", ...] = ()

    def quotes(self) -> tuple["Evidence", ...]:
        return (self, *self.also)


@dataclass(frozen=True)
class Question:
    id: str
    kind: str
    question: str
    evidence: tuple[Evidence, ...]
    term: str | None = None
    avoid: tuple[str, ...] = ()


@dataclass(frozen=True)
class KeyFact:
    id: str
    document: str
    fact: str
    # Every group must be matched; a group is matched by any one of its words.
    words: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class Passage:
    """One chunk as the app cuts it: its document, its place, its text."""

    document: str
    ordinal: int
    content: str


def load_questions(path: Path = QUESTIONS) -> list[Question]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        Question(
            id=q["id"],
            kind=q["kind"],
            question=q["question"],
            evidence=tuple(
                Evidence(
                    e["document"],
                    e["quote"],
                    tuple(
                        Evidence(a["document"], a["quote"]) for a in e.get("also", ())
                    ),
                )
                for e in q["evidence"]
            ),
            term=q.get("term"),
            avoid=tuple(q.get("avoid", ())),
        )
        for q in data["questions"]
    ]


def load_key_facts(path: Path = KEY_FACTS) -> list[KeyFact]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        KeyFact(
            id=f["id"],
            document=f["document"],
            fact=f["fact"],
            words=tuple(tuple(group) for group in f["words"]),
        )
        for f in data["facts"]
    ]


def reviewed(path: Path = QUESTIONS) -> str | None:
    """Who reviewed the labels and when, as recorded in the file."""
    return json.loads(path.read_text(encoding="utf-8")).get("reviewed")


def passages() -> list[Passage]:
    """The corpus cut into passages by the app's parser and chunker, without a
    database: the same passages the benchmark stores."""
    parser = PyMuPDFParser()
    found = []
    with tempfile.TemporaryDirectory() as folder:
        for source in corpus.documents():
            path = Path(folder) / source.filename
            path.write_bytes(corpus.to_pdf(source.text))
            parsed = parser.parse(path)
            for chunk in chunk_document(uuid.uuid4(), parsed):
                found.append(Passage(source.filename, chunk.ordinal, chunk.content))
    return found


def holding(quote: str, document: str, among: list[Passage]) -> list[Passage]:
    """The passages of the document whose text contains the quote, whatever
    the line breaks."""
    wanted = corpus.plain(quote).casefold()
    return [
        p
        for p in among
        if p.document == document and wanted in corpus.plain(p.content).casefold()
    ]


def problems(
    questions: list[Question],
    among: list[Passage],
    sources: list[corpus.SourceDocument] | None = None,
) -> list[str]:
    """Everything wrong with the questions' labels; empty when they hold."""
    sources = sources if sources is not None else corpus.documents()
    texts = {s.filename: corpus.plain(s.text).casefold() for s in sources}
    found: list[str] = []

    counts = Counter(q.kind for q in questions)
    if dict(counts) != KINDS:
        found.append(f"kinds are {dict(counts)}, expected {KINDS}")
    for id_, n in Counter(q.id for q in questions).items():
        if n > 1:
            found.append(f"{id_}: id used {n} times")

    for q in questions:
        wanted = 2 if q.kind == "multi" else 1
        if len(q.evidence) != wanted:
            found.append(
                f"{q.id}: {len(q.evidence)} evidence quotes, expected {wanted}"
            )
        resolved: list[Passage] = []  # every passage of every part
        primary: list[Passage] = []  # each part's own quote
        for part in q.evidence:
            for e in part.quotes():
                if e.document not in texts:
                    found.append(f"{q.id}: no document {e.document}")
                    continue
                quote = corpus.plain(e.quote).casefold()
                everywhere = sum(text.count(quote) for text in texts.values())
                if everywhere != 1:
                    found.append(
                        f"{q.id}: quote found {everywhere} times in the corpus"
                    )
                places = holding(e.quote, e.document, among)
                if len(places) != 1:
                    found.append(
                        f"{q.id}: quote inside {len(places)} passages of {e.document}"
                    )
                resolved.extend(places)
                if e is part:
                    primary.extend(places)
            alternatives = {
                (p.document, p.ordinal)
                for a in part.also
                for p in holding(a.quote, a.document, among)
            }
            if alternatives & {(p.document, p.ordinal) for p in primary[-1:]}:
                found.append(f"{q.id}: an alternative is the same passage")
        if q.kind == "multi" and len({(p.document, p.ordinal) for p in primary}) < 2:
            found.append(f"{q.id}: needs two different passages")
        if q.kind in ("term", "mixed"):
            term = (q.term or "").casefold()
            if not term or term not in q.question.casefold():
                found.append(f"{q.id}: the question does not contain its term")
            elif not any(term in corpus.plain(p.content).casefold() for p in resolved):
                found.append(f"{q.id}: the evidence does not contain the term")
        if q.kind == "meaning":
            if not q.avoid:
                found.append(f"{q.id}: no words to avoid")
            for word in q.avoid:
                if word.casefold() in q.question.casefold():
                    found.append(f"{q.id}: the question uses {word!r}")
    return found


def fact_problems(
    facts: list[KeyFact], sources: list[corpus.SourceDocument] | None = None
) -> list[str]:
    """Everything wrong with the key facts: each must belong to a document,
    and each of its word groups must occur in that document, or no summary
    could ever be credited with it."""
    sources = sources if sources is not None else corpus.documents()
    texts = {s.filename: corpus.plain(s.text).casefold() for s in sources}
    found: list[str] = []
    for id_, n in Counter(f.id for f in facts).items():
        if n > 1:
            found.append(f"{id_}: id used {n} times")
    for f in facts:
        if f.document not in texts:
            found.append(f"{f.id}: no document {f.document}")
            continue
        if not f.words:
            found.append(f"{f.id}: no words")
        for group in f.words:
            if not any(_has(texts[f.document], word) for word in group):
                found.append(f"{f.id}: none of {list(group)} is in {f.document}")
    per_document = Counter(f.document for f in facts)
    for source in sources:
        if per_document[source.filename] < 4:
            found.append(
                f"{source.filename}: {per_document[source.filename]} key facts"
            )
    return found


def _has(folded: str, word: str) -> bool:
    """Whether a word of the (casefolded) text begins with the word."""
    return re.search(r"(?<!\w)" + re.escape(word.casefold()), folded) is not None


def covers(text: str, fact: KeyFact) -> bool:
    """Whether a text covers the fact: every word group matched."""
    folded = corpus.plain(text).casefold()
    return all(any(_has(folded, word) for word in group) for group in fact.words)
