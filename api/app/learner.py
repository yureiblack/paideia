"""Learner state per concept, and when each concept comes back.

Purpose
-------
How a learner stands on a concept is worked out from their answers, never
stored apart from them (decision record 15): the answers to the concept's
practice items, replayed in the order given, through one function. The same
answers always give the same state, and the state can always be explained
by them. Pure functions, no database and no model, so the rules can be
tested directly.

The schedule, per concept:

- Review gaps are 1, 2, 4, 8, 16, then 32 days.
- Recalling the concept moves its gap one step up, at most once in a
  sitting: a recall within SITTING of the gap's last change does not move it
  again. Two right answers in one session count once.
- A miss puts the gap back to 1 day, and a recall in the same sitting after
  a miss does not undo it.
- The next review is the last answer's time plus the gap.

A concept with practice items but no answers is new, and due at once.
"""

import heapq
from collections.abc import Hashable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.practice import interleave

GAPS = (1, 2, 4, 8, 16, 32)  # days
SITTING = timedelta(hours=12)
RECENT = 6  # answers considered for "needs attention"
STRONG_GAP = 4  # days


@dataclass(frozen=True)
class Answer:
    at: datetime
    correct: bool


@dataclass(frozen=True)
class State:
    """A learner's standing on one concept. gap_days and next_review_at are
    None until the first answer. recent holds the last RECENT outcomes,
    oldest first."""

    exposures: int = 0
    recalled: int = 0
    failed: int = 0
    last_attempted_at: datetime | None = None
    last_recalled_at: datetime | None = None
    gap_days: int | None = None
    next_review_at: datetime | None = None
    recent: tuple[bool, ...] = ()
    step: int = -1
    changed_at: datetime | None = None

    @property
    def last_correct(self) -> bool | None:
        return self.recent[-1] if self.recent else None


def after(state: State, answer: Answer) -> State:
    """The state after one more answer."""
    step, changed_at = state.step, state.changed_at
    in_sitting = changed_at is not None and answer.at - changed_at < SITTING
    if not answer.correct:
        step, changed_at = 0, answer.at
    elif not in_sitting:
        step, changed_at = min(step + 1, len(GAPS) - 1), answer.at
    gap = GAPS[max(step, 0)]
    return State(
        exposures=state.exposures + 1,
        recalled=state.recalled + answer.correct,
        failed=state.failed + (not answer.correct),
        last_attempted_at=answer.at,
        last_recalled_at=answer.at if answer.correct else state.last_recalled_at,
        gap_days=gap,
        next_review_at=answer.at + timedelta(days=gap),
        recent=(*state.recent, answer.correct)[-RECENT:],
        step=max(step, 0),
        changed_at=changed_at,
    )


def replay(answers: Iterable[Answer]) -> State:
    """The state a concept's answers lead to, taken in the order given (the
    order they were made)."""
    state = State()
    for answer in answers:
        state = after(state, answer)
    return state


def review(state: State, until: datetime) -> str:
    """new (never answered), due (its next review comes by until) or
    scheduled. For concepts that have practice items."""
    if state.exposures == 0:
        return "new"
    return "due" if state.next_review_at <= until else "scheduled"


def attention(state: State) -> str | None:
    """Why the concept needs attention, or None: missed on its last answer,
    or fewer than half recalled of its recent answers."""
    if state.last_correct is False:
        return "Missed on its last answer."
    recalled = sum(state.recent)
    if len(state.recent) >= 2 and recalled * 2 < len(state.recent):
        return f"Recalled {recalled} of its last {len(state.recent)} answers."
    return None


def strong(state: State) -> bool:
    """Recalled on its last answer, with a gap of STRONG_GAP days or more."""
    return state.last_correct is True and (state.gap_days or 0) >= STRONG_GAP


@dataclass(frozen=True)
class Option:
    """A practice item that could go into a session. box is its own Leitner
    box from Phase 14: it only decides which of a concept's items come
    first."""

    id: Hashable
    concept: Hashable
    kind: str
    box: int
    last_answered_at: datetime | None


def session(
    due: Sequence[tuple[Hashable, State, int]],
    options: Sequence[Option],
    until: datetime,
    *,
    per_concept: int = 2,
    limit: int = 10,
) -> list[Option]:
    """A session from the concepts due by until: (concept, state, place on
    the roadmap) for every concept with practice items. Overdue concepts
    first, the longest overdue first, then new ones in roadmap order. Each
    gives up to per_concept items, those in the lowest box and answered
    longest ago first, of different kinds where it can. At most limit items,
    interleaved."""
    queue = []
    for concept, state, place in due:
        status = review(state, until)
        if status == "due":
            when = state.next_review_at.timestamp()
            heapq.heappush(queue, (0, when, place, str(concept), concept))
        elif status == "new":
            heapq.heappush(queue, (1, 0.0, place, str(concept), concept))

    def freshness(o: Option):
        answered = o.last_answered_at.timestamp() if o.last_answered_at else 0.0
        return (o.box, answered, str(o.id))

    by_concept: dict[Hashable, list[Option]] = {}
    for option in sorted(options, key=freshness):
        by_concept.setdefault(option.concept, []).append(option)
    chosen: list[Option] = []
    while queue and len(chosen) < limit:
        *_, concept = heapq.heappop(queue)
        room = min(per_concept, limit - len(chosen))
        available = by_concept.get(concept, [])
        picked: list[Option] = []
        for option in available:  # different kinds first
            if len(picked) < room and all(option.kind != p.kind for p in picked):
                picked.append(option)
        for option in available:  # then any, if a concept has few kinds
            if len(picked) < room and option not in picked:
                picked.append(option)
        chosen.extend(picked)
    return interleave(chosen, lambda o: o.concept)
