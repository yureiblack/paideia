"""Today's study plan: which sessions, in which order, and for how long.

Purpose
-------
The plan is decided here, by fixed rules, never by the model (decision
record 16). Pure functions, no database and no model, so the rules can be
tested directly; the plan is worked out afresh whenever it is read.

Four kinds of session, each concept in at most one, in this order:

1. Strengthen: concepts that need attention (missed on their last answer,
   or mostly missed lately). Re-read their passages, then answer again:
   a miss is cheapest to fix while it is fresh.
2. Review: concepts due today. Spaced review only works when it is on time.
3. Learn: the next roadmap stage with concepts not yet practised. Read its
   passages, prepare practice if needed, practise. New learning builds on
   ground already reviewed.
4. Skim: a document added recently with none of its concepts practised.
   Its summary gives the overview before its stages come up.

At most GROUP concepts per Strengthen or Review session (more make further
sessions, in roadmap order), one Learn session and SKIMS Skim sessions.

Effort is estimated from reading at READING_WPM words a minute and from
answering ITEMS_PER_CONCEPT items per concept, at the learner's own median
time for each kind of item once they have OWN_PACE_AFTER timed answers of
it, otherwise at DEFAULT_SECONDS. A time budget, if given, takes sessions in
order while they fit; one that does not fit waits for "with more time", and
a smaller one after it may still fit.
"""

import math
import statistics
from collections.abc import Hashable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

READING_WPM = 200
ITEMS_PER_CONCEPT = 2
OWN_PACE_AFTER = 5
DEFAULT_SECONDS = {
    "true_false": 30.0,
    "flashcard": 30.0,
    "multiple_choice": 60.0,
    "short_answer": 90.0,
}
GROUP = 5
SKIMS = 2
RECENT = timedelta(days=7)


@dataclass(frozen=True)
class Concept:
    """A concept as the planner needs it. place is its place on the roadmap.
    review, attention, exposures and gap_days come from the learner's state
    (Phase 15); kinds are the kinds of its practised items, none when its
    practice is not prepared; passages are (passage id, word count)."""

    id: Hashable
    name: str
    place: int
    review: str | None  # new, due, scheduled; None without items
    attention: str | None
    exposures: int
    gap_days: int | None
    kinds: tuple[str, ...]
    passages: tuple[tuple[Hashable, int], ...]


@dataclass(frozen=True)
class Stage:
    number: int
    title: str
    concepts: tuple[Hashable, ...]  # in roadmap order


@dataclass(frozen=True)
class Document:
    id: Hashable
    filename: str
    added_at: datetime
    summary_words: int | None  # None without a summary
    concepts: tuple[Hashable, ...]


@dataclass(frozen=True)
class Session:
    kind: str  # strengthen, review, learn, skim
    title: str
    minutes: int
    rationale: str
    concepts: tuple[Hashable, ...]
    stage: int | None = None
    document: Hashable | None = None
    needs_preparing: bool = False


@dataclass(frozen=True)
class Plan:
    sessions: tuple[Session, ...]
    later: tuple[Session, ...] = field(default=())

    @property
    def minutes(self) -> int:
        return sum(s.minutes for s in self.sessions)


def pace(timed: dict[str, Sequence[float]]) -> dict[str, float]:
    """Seconds per answer, by kind of item: the learner's own median once
    they have OWN_PACE_AFTER timed answers of a kind, otherwise the
    default."""
    return {
        kind: statistics.median(timed[kind])
        if len(timed.get(kind, ())) >= OWN_PACE_AFTER
        else default
        for kind, default in DEFAULT_SECONDS.items()
    }


def _answering(concepts: Iterable[Concept], seconds: dict[str, float]) -> float:
    total = 0.0
    for concept in concepts:
        kinds = concept.kinds or tuple(DEFAULT_SECONDS)
        total += ITEMS_PER_CONCEPT * statistics.mean(seconds[k] for k in kinds)
    return total


def _reading(concepts: Iterable[Concept]) -> float:
    words = dict(p for c in concepts for p in c.passages)  # shared ones once
    return sum(words.values()) / READING_WPM * 60


def _minutes(seconds: float) -> int:
    return max(1, math.ceil(seconds / 60))


def _names(concepts: Sequence[Concept]) -> str:
    names = [c.name for c in concepts]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _concepts(n: int) -> str:
    return f"{n} concept" if n == 1 else f"{n} concepts"


def _groups(concepts: list[Concept]) -> list[list[Concept]]:
    return [concepts[i : i + GROUP] for i in range(0, len(concepts), GROUP)]


def _days(delta: timedelta) -> str:
    days = delta.days
    return "today" if days < 1 else "yesterday" if days == 1 else f"{days} days ago"


def build(
    concepts: Iterable[Concept],
    stages: Sequence[Stage],
    documents: Iterable[Document],
    seconds: dict[str, float],
    now: datetime,
    budget: int | None = None,
) -> Plan:
    """Today's plan. seconds is pace() of the learner's answers; budget, in
    minutes, is optional."""
    by_id = {c.id: c for c in concepts}
    ordered = sorted(by_id.values(), key=lambda c: (c.place, c.name))
    used: set[Hashable] = set()
    sessions: list[Session] = []

    weak = [c for c in ordered if c.attention and c.kinds]
    for group in _groups(weak):
        sessions.append(
            Session(
                kind="strengthen",
                title=f"Strengthen: {_names(group)}",
                minutes=_minutes(_reading(group) + _answering(group, seconds)),
                rationale=(
                    f"{_concepts(len(group))} missed on the last answer, or mostly "
                    "missed lately. Re-read the passages, then answer again while "
                    "the miss is fresh."
                ),
                concepts=tuple(c.id for c in group),
            )
        )
    used.update(c.id for c in weak)

    due = [c for c in ordered if c.review == "due" and c.id not in used]
    for group in _groups(due):
        gaps = sorted({c.gap_days for c in group if c.gap_days})
        span = (
            f"{gaps[0]} day" + ("s" if gaps[0] != 1 else "")
            if len(gaps) == 1
            else f"{gaps[0]} to {gaps[-1]} days"
        )
        sessions.append(
            Session(
                kind="review",
                title=f"Review: {_names(group)}",
                minutes=_minutes(_answering(group, seconds)),
                rationale=(
                    f"{_concepts(len(group))} due for review today. Reviewing on "
                    f"time lets each gap keep growing; it is now {span}."
                ),
                concepts=tuple(c.id for c in group),
            )
        )
    used.update(c.id for c in due)

    learn = None
    for stage in stages:
        fresh = [
            by_id[i]
            for i in stage.concepts
            if i in by_id and by_id[i].exposures == 0 and i not in used
        ]
        if fresh:
            learn = (stage, fresh)
            break
    if learn is not None:
        stage, fresh = learn
        unprepared = [c for c in fresh if not c.kinds]
        rationale = (
            f"Next on your roadmap: stage {stage.number}, with "
            f"{_concepts(len(fresh))} not practised yet. Read the passages, then "
            "practise."
        )
        if unprepared:
            rationale += (
                " Its practice items need preparing first; the local model writes "
                "them in the background."
            )
        sessions.append(
            Session(
                kind="learn",
                title=f"Learn: stage {stage.number}, {stage.title}",
                minutes=_minutes(_reading(fresh) + _answering(fresh, seconds)),
                rationale=rationale,
                concepts=tuple(c.id for c in fresh),
                stage=stage.number,
                needs_preparing=bool(unprepared),
            )
        )
        used.update(c.id for c in fresh)

    recent = [
        d
        for d in documents
        if d.summary_words
        and now - d.added_at <= RECENT
        and d.concepts
        and all(by_id[i].exposures == 0 for i in d.concepts if i in by_id)
        and not set(d.concepts) <= used
    ]
    recent.sort(key=lambda d: (d.added_at, str(d.id)), reverse=True)
    for document in recent[:SKIMS]:
        sessions.append(
            Session(
                kind="skim",
                title=f"Skim: {document.filename}",
                minutes=_minutes(document.summary_words / READING_WPM * 60),
                rationale=(
                    f"Added {_days(now - document.added_at)}, and none of its "
                    f"{_concepts(len(document.concepts))} practised yet. Its summary "
                    "gives the overview before its stages come up."
                ),
                concepts=tuple(document.concepts),
                document=document.id,
            )
        )

    if budget is None:
        return Plan(sessions=tuple(sessions))
    fitted, later, left = [], [], budget
    for session in sessions:
        if session.minutes <= left:
            fitted.append(session)
            left -= session.minutes
        else:
            later.append(session)
    return Plan(sessions=tuple(fitted), later=tuple(later))
