"""Candidate pairs of concepts, and what a decision about one means.

Purpose
-------
The knowledge graph's pairs are found here, by fixed rules, never by the
model (decision record 12). The model only classifies the pairs it is given.
Pure functions, no database and no model, so the rules can be tested
directly.

A pair is two concepts that one passage connects: a passage that is evidence
for one concept and is also evidence for the other, or names it. Names are
matched word by word on a simplified text (case folded, punctuation dropped,
each word made singular), so "threads" in a passage finds the concept
"Thread". This finds pairs across documents too: a passage in the
synchronization lecture that names "thread" pairs Mutex with Thread from the
scheduling lecture.
"""

import hashlib
import re
import uuid
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from app.concepts import singular, split_name, tidy

# The six choices the model has for a pair, in the order the prompt lists
# them, and what each means for the graph. "a" and "b" are the pair's two
# concepts in normalized-name order.
DECISIONS = (
    "a_before_b",
    "b_before_a",
    "a_part_of_b",
    "b_part_of_a",
    "related",
    "none",
)

# Below this the model's confidence counts as "no relationship".
MIN_CONFIDENCE = 0.5

# The most pairs one build considers, the best-supported first. Bounds the
# model's work for very large environments.
MAX_PAIRS = 400


@dataclass(frozen=True)
class ConceptInfo:
    id: uuid.UUID
    name: str
    normalized_name: str
    definition: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class Passage:
    id: uuid.UUID
    document_id: uuid.UUID
    ordinal: int
    text: str
    content_hash: str


@dataclass(frozen=True)
class Pair:
    """Two concepts and the passages connecting them. a sorts before b by
    normalized name, so a pair is the same pair whichever way it was found."""

    a: ConceptInfo
    b: ConceptInfo
    passages: tuple[Passage, ...]  # in document and reading order

    @property
    def document_id(self) -> uuid.UUID:
        """The document holding most of its passages, which it is asked about
        with. Ties go to the earliest passage's document."""
        counts = Counter(p.document_id for p in self.passages)
        best = max(counts.values())
        return next(
            p.document_id for p in self.passages if counts[p.document_id] == best
        )

    @property
    def key(self) -> str:
        """The pair as the model saw it: both names and its passages' text.
        The same key means the same question, so the same answer."""
        hashes = sorted(p.content_hash for p in self.passages)
        text = "\n".join([self.a.normalized_name, self.b.normalized_name, *hashes])
        return hashlib.sha256(text.encode()).hexdigest()


_WORD = re.compile(r"[^\W_]+(?:'[^\W_]+)?")


def words(text: str) -> str:
    """Text simplified for matching names: case folded, hyphens and other
    punctuation dropped, every word made singular, with spaces round the
    ends so a name matches whole words only."""
    found = _WORD.findall(tidy(text).casefold())
    return " " + " ".join(singular(w) for w in found) + " "


def name_forms(concept: ConceptInfo) -> set[str]:
    """Every way a passage may name the concept: its name without bracketed
    parts, and each alias, simplified as passages are. Forms of a single
    letter are left out."""
    bare, _ = split_name(concept.name)
    forms = {words(bare), *(words(alias) for alias in concept.aliases)}
    return {f for f in forms if len(f.strip()) > 1}


def find_pairs(
    concepts: Iterable[ConceptInfo],
    evidence: dict[uuid.UUID, set[uuid.UUID]],
    passages: dict[uuid.UUID, Passage],
) -> list[Pair]:
    """Every pair of concepts some passage connects, best-supported first, at
    most MAX_PAIRS. evidence maps a concept id to its evidence passages."""
    concepts = sorted(concepts, key=lambda c: c.normalized_name)
    forms = {c.id: name_forms(c) for c in concepts}
    simplified = {pid: words(p.text) for pid, p in passages.items()}
    found: dict[tuple[uuid.UUID, uuid.UUID], set[uuid.UUID]] = defaultdict(set)
    for b in concepts:
        for passage_id in evidence.get(b.id, ()):
            text = simplified[passage_id]
            for a in concepts:
                if a.id == b.id:
                    continue
                if passage_id in evidence.get(a.id, ()) or any(
                    form in text for form in forms[a.id]
                ):
                    first, second = sorted((a, b), key=lambda c: c.normalized_name)
                    found[(first.id, second.id)].add(passage_id)
    by_id = {c.id: c for c in concepts}
    pairs = [
        Pair(
            a=by_id[a],
            b=by_id[b],
            passages=tuple(
                sorted(
                    (passages[p] for p in ids),
                    key=lambda p: (str(p.document_id), p.ordinal),
                )
            ),
        )
        for (a, b), ids in found.items()
    ]
    pairs.sort(
        key=lambda p: (-len(p.passages), p.a.normalized_name, p.b.normalized_name)
    )
    return pairs[:MAX_PAIRS]


@dataclass(frozen=True)
class Edge:
    source: uuid.UUID
    target: uuid.UUID
    relationship_type: str  # PREREQUISITE_OF, PART_OF or RELATED_TO
    confidence: float


def edge_for(pair: Pair, decision: str, confidence: float) -> Edge | None:
    """The edge a decision about a pair stands for, or None: "none", or a
    confidence below MIN_CONFIDENCE, means no relationship."""
    if decision not in DECISIONS:
        raise ValueError(f"unknown decision {decision!r}")
    if decision == "none" or not MIN_CONFIDENCE <= confidence <= 1:
        return None
    a, b = pair.a.id, pair.b.id
    source, target, kind = {
        "a_before_b": (a, b, "PREREQUISITE_OF"),
        "b_before_a": (b, a, "PREREQUISITE_OF"),
        "a_part_of_b": (a, b, "PART_OF"),
        "b_part_of_a": (b, a, "PART_OF"),
        "related": (a, b, "RELATED_TO"),
    }[decision]
    return Edge(
        source=source, target=target, relationship_type=kind, confidence=confidence
    )
