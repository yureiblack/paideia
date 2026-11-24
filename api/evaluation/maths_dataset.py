"""The maths benchmark's search questions, and the checks they must pass.

Purpose
-------
The questions are written like those of the retrieval benchmark (record 20,
evaluation/dataset.py), and in the same file format: each names the passage
that answers it by a quote. Here a quote is always prose, never maths,
because the same question is asked of the lectures three times: as the
PDF's text layer reads them, as the model's readings replace their pages,
and as a perfect reading would. Prose reads the same in all three, so the
quote finds its passage in each.

A model's reading may still change a word of the prose. So at run time a
quote is found in a passage exactly if it can be, and otherwise in the one
passage of its lecture that holds most of its words in order (holding()).
"""

import difflib
import json
import re
from collections import Counter
from pathlib import Path

from evaluation import corpus, maths_corpus
from evaluation.dataset import Evidence, Passage, Question, load_questions

QUESTIONS = maths_corpus.ROOT / "docs" / "evaluation" / "maths" / "questions.json"
KINDS = {"term": 10, "meaning": 10, "formula": 20, "notation": 8}
# A quote is found in a passage, inexactly, when the passage holds at least
# this share of its words in order.
MIN_SHARE = 0.8

__all__ = [
    "QUESTIONS",
    "Evidence",
    "Passage",
    "Question",
    "holding",
    "load",
    "problems",
]


def load(path: Path = QUESTIONS) -> list[Question]:
    return load_questions(path)


def reviewed(path: Path = QUESTIONS) -> str | None:
    return json.loads(path.read_text(encoding="utf-8")).get("reviewed")


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", corpus.plain(text).casefold())


def holding(quote: str, document: str, among: list[Passage]) -> list[Passage]:
    """The passage of the document that holds the quote: exactly, or failing
    that, the one holding the largest share of its words in order, if that
    share is at least MIN_SHARE."""
    mine = [p for p in among if p.document == document]
    wanted = corpus.plain(quote).casefold()
    exact = [p for p in mine if wanted in corpus.plain(p.content).casefold()]
    if exact:
        return exact
    words = _words(quote)
    best, share = None, 0.0
    for p in mine:
        matcher = difflib.SequenceMatcher(
            None, words, _words(p.content), autojunk=False
        )
        found = sum(block.size for block in matcher.get_matching_blocks()) / max(
            1, len(words)
        )
        if found > share:
            best, share = p, found
    return [best] if best is not None and share >= MIN_SHARE else []


def problems(
    questions: list[Question], lectures: list[maths_corpus.Lecture] | None = None
) -> list[str]:
    """Everything wrong with the questions; empty when they hold. Checked
    against the lectures' source, so no typesetting is needed."""
    lectures = lectures if lectures is not None else maths_corpus.lectures()
    texts = {lec.filename: corpus.plain(lec.source).casefold() for lec in lectures}
    found: list[str] = []
    counts = Counter(q.kind for q in questions)
    if dict(counts) != KINDS:
        found.append(f"kinds are {dict(counts)}, expected {KINDS}")
    for id_, n in Counter(q.id for q in questions).items():
        if n > 1:
            found.append(f"{id_}: id used {n} times")
    for q in questions:
        if len(q.evidence) != 1:
            found.append(f"{q.id}: {len(q.evidence)} evidence parts, expected 1")
        for part in q.evidence:
            for e in part.quotes():
                if e.document not in texts:
                    found.append(f"{q.id}: no lecture {e.document}")
                    continue
                if "$" in e.quote or "\\" in e.quote:
                    found.append(f"{q.id}: the quote holds maths")
                quote = corpus.plain(e.quote).casefold()
                everywhere = sum(text.count(quote) for text in texts.values())
                if everywhere != 1:
                    found.append(
                        f"{q.id}: quote found {everywhere} times in the lectures"
                    )
        if q.kind == "term":
            term = (q.term or "").casefold()
            if not term or term not in q.question.casefold():
                found.append(f"{q.id}: the question does not contain its term")
            elif not any(
                term in corpus.plain(b.markdown).casefold()
                for lec in lectures
                if lec.filename == q.evidence[0].document
                for b in lec.blocks
                if corpus.plain(q.evidence[0].quote).casefold()
                in corpus.plain(b.markdown).casefold()
            ):
                found.append(f"{q.id}: the evidence does not contain the term")
        if q.kind == "meaning":
            if not q.avoid:
                found.append(f"{q.id}: no words to avoid")
            for word in q.avoid:
                if word.casefold() in q.question.casefold():
                    found.append(f"{q.id}: the question uses {word!r}")
    return found
