"""The scores the benchmark reports, as plain functions of rankings.

Retrieval, for one question, given the passages a method returned, best
first. A question's answer has one part, or two for a question needing two
passages, and each part is answered by any one of its passages:

- recall at k: the share of the parts answered among the first k results.
  A question needing two passages that finds one of them scores 0.5.
- reciprocal rank: 1 divided by the position of the first relevant
  passage among the first k, or 0 if none is there. Its mean over the
  questions is MRR.
- hit at 1: whether the first result is relevant.

Generation, for a summary's key points and the passages each one cites:

- citation correctness: the share of citations whose passage supports the
  point citing it;
- groundedness: the share of key points supported by at least one of their
  citations;
- completeness: the share of a document's key facts the summary covers.

Latency is reported as percentiles of the measured times.
"""

import math
from collections import defaultdict
from collections.abc import Hashable, Iterable, Sequence


def recall_at(ranked: Sequence[Hashable], parts: Sequence[set], k: int) -> float:
    if not parts or not all(parts):
        raise ValueError("every part of a question needs a relevant passage")
    first = set(ranked[:k])
    return sum(1 for part in parts if part & first) / len(parts)


def reciprocal_rank(ranked: Sequence[Hashable], relevant: set, k: int = 10) -> float:
    for position, item in enumerate(ranked[:k], start=1):
        if item in relevant:
            return 1 / position
    return 0.0


def hit_at_1(ranked: Sequence[Hashable], relevant: set) -> float:
    return 1.0 if ranked and ranked[0] in relevant else 0.0


def percentile(values: Iterable[float], p: float) -> float:
    """The p-th percentile (0 to 100), interpolating between the two
    nearest measurements, as spreadsheets and NumPy do by default."""
    ordered = sorted(values)
    if not ordered:
        raise ValueError("no values")
    position = (len(ordered) - 1) * p / 100
    below, above = math.floor(position), math.ceil(position)
    if below == above:
        return ordered[below]
    weight = position - below
    return ordered[below] * (1 - weight) + ordered[above] * weight


def mean(values: Iterable[float]) -> float:
    values = list(values)
    if not values:
        raise ValueError("no values")
    return sum(values) / len(values)


def by_kind(rows: Iterable[dict], score: str) -> dict[str, float]:
    """The mean of one score over all rows and over each kind of question.
    Each row is one question's scores, with its kind."""
    groups: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        groups["all"].append(row[score])
        groups[row["kind"]].append(row[score])
    return {kind: mean(values) for kind, values in groups.items()}


def citation_correctness(points: Sequence[Sequence[bool]]) -> float:
    """points holds, for each key point, whether each of its citations
    supports it."""
    citations = [supported for point in points for supported in point]
    return mean(1.0 if s else 0.0 for s in citations)


def groundedness(points: Sequence[Sequence[bool]]) -> float:
    return mean(1.0 if any(point) else 0.0 for point in points)


def completeness(covered: Sequence[bool]) -> float:
    return mean(1.0 if c else 0.0 for c in covered)
