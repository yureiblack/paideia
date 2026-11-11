"""Practice items: what makes one usable, and when it comes back.

Purpose
-------
The model writes practice items from a concept's passages; these rules
decide which of them a learner ever sees, and everything after (decision
record 14). Pure functions, no database and no model, so the rules can be
tested directly.

- An item's text must be plain, within bounds, and must not talk about "the
  passages" or carry citation marks: the learner sees a question, not the
  machinery behind it. Bracketed citations and formulaic attributions
  ("according to the passages", "passage 1 states that") are removed; any
  other mention of passages drops the item.
- Multiple-choice options must differ, lose any numbering the model gave
  them, and are shuffled with a fixed seed, so the right answer's position
  gives nothing away and is the same every time.
- A true/false statement must be true or false as asked: the backend, not
  the model, decides which.
- Difficulty comes from the kind of item, as effort: recognising a true
  statement or recalling a flashcard's back is easier than picking among
  close options, and that is easier than recalling an answer unprompted.
- Review follows Leitner boxes: a correct answer moves an item up a box and
  further away, a wrong one back to the first box.
- A session mixes concepts (interleaving): concepts take turns filling it,
  and the same concept never comes twice in a row when that can be avoided.
"""

import random
import re
from collections.abc import Callable, Hashable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TypeVar

KINDS = ("short_answer", "multiple_choice", "true_false", "flashcard")

# Effort, from recognising to recalling unprompted. Not a measured difficulty.
DIFFICULTY = {"true_false": 1, "flashcard": 1, "multiple_choice": 2, "short_answer": 3}

# Days until an item comes back, by box. A new item is in box 0, due at once.
INTERVALS = (1, 2, 4, 8, 16)

SESSION_SIZE = 10
OPTIONS = 4

# Lengths of what the learner reads, in characters.
QUESTION_CHARS = 300
ANSWER_CHARS = 300
OPTION_CHARS = 150
FRONT_CHARS = 150

# "(passage [1])", "[2]", "(passages 1 and 3)", "(see passage 2)".
_CITATION = re.compile(
    r"\s*[(\[]\s*(?:see\s+)?(?:passages?\s*)?\[?\d+\]?"
    r"(?:\s*(?:,|and|&)\s*\[?\d+\]?)*\s*[)\]]",
    re.IGNORECASE,
)
# Formulaic attributions, removed where that leaves the sentence whole:
# "..., according to the passages", "as mentioned in passage 1",
# "the passage states that ...".
_ATTRIBUTION = re.compile(
    r",?\s*(?:according to|as (?:mentioned|stated|explained|described|noted) in)"
    r" (?:the )?passages?(?:\s*\[?\d+\]?)?"
    r"|\b(?:the )?passages?(?:\s*\[?\d+\]?)?\s+(?:also\s+|explicitly\s+|clearly\s+)?"
    r"(?:states?|says?|explains?|notes?|mentions?) that\s+",
    re.IGNORECASE,
)
_MENTION = re.compile(r"\bpassages?\b", re.IGNORECASE)
_MARKUP = re.compile(r"[*#`|\n]")
_NUMBERING = re.compile(r"^\s*(?:\(?[A-Da-d1-4][.):]|[A-Da-d1-4]\s+-)\s+")


def tidy(text: str, limit: int) -> str | None:
    """The text as a learner should read it: citation marks and formulaic
    attributions removed, spacing tidied. None if it carries formatting,
    still mentions passages, is empty or is longer than limit."""
    if _MARKUP.search(text):
        return None
    text = _ATTRIBUTION.sub("", _CITATION.sub("", text))
    text = re.sub(r"\s+", " ", text).strip()
    text = text[:1].upper() + text[1:]
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)
    if not text or len(text) > limit or _MENTION.search(text):
        return None
    return text


@dataclass(frozen=True)
class Draft:
    """An item that passed every check but the last: whether its passages
    support it. claim is the text that check scores against them."""

    kind: str
    content: dict
    sources: tuple[int, ...]
    claim: str

    @property
    def difficulty(self) -> int:
        return DIFFICULTY[self.kind]


def short_answer(question: str, answer: str, sources: Sequence[int]) -> Draft | str:
    question, answer = tidy(question, QUESTION_CHARS), tidy(answer, ANSWER_CHARS)
    if not question or not answer:
        return "formatting, a mention of passages, or too long"
    content = {"question": question, "answer": answer}
    return Draft("short_answer", content, tuple(sources), f"{question} {answer}")


def multiple_choice(
    question: str,
    options: Sequence[str],
    correct: int,
    explanation: str,
    sources: Sequence[int],
    seed: str,
) -> Draft | str:
    """correct counts from 1, as the model gives it. Stored options are
    shuffled with seed, and correct becomes their index from 0."""
    question = tidy(question, QUESTION_CHARS)
    explanation = tidy(explanation, ANSWER_CHARS)
    cleaned = [tidy(_NUMBERING.sub("", option), OPTION_CHARS) for option in options]
    if not question or not explanation or not all(cleaned):
        return "formatting, a mention of passages, or too long"
    if len(cleaned) != OPTIONS or not 1 <= correct <= OPTIONS:
        return "not four options with one correct"
    if len({option.casefold() for option in cleaned}) != OPTIONS:
        return "options repeat"
    order = list(range(OPTIONS))
    random.Random(seed).shuffle(order)
    content = {
        "question": question,
        "options": [cleaned[i] for i in order],
        "correct": order.index(correct - 1),
        "explanation": explanation,
    }
    return Draft(
        "multiple_choice", content, tuple(sources), f"{question} {cleaned[correct - 1]}"
    )


def true_false(
    statement: str, truth: bool, explanation: str, sources: Sequence[int], wanted: bool
) -> Draft | str:
    statement = tidy(statement, QUESTION_CHARS)
    explanation = tidy(explanation, ANSWER_CHARS)
    if not statement or not explanation:
        return "formatting, a mention of passages, or too long"
    if truth != wanted:
        return "not the truth asked for"
    content = {"statement": statement, "truth": truth, "explanation": explanation}
    return Draft("true_false", content, tuple(sources), statement)


def flashcard(front: str, back: str, sources: Sequence[int]) -> Draft | str:
    front, back = tidy(front, FRONT_CHARS), tidy(back, ANSWER_CHARS)
    if not front or not back:
        return "formatting, a mention of passages, or too long"
    return Draft(
        "flashcard", {"front": front, "back": back}, tuple(sources), f"{front} {back}"
    )


def wanted_truth(key: str) -> bool:
    """Whether a concept's true/false statement should be true: decided by
    its key, so about half are false, and the same concept always gets the
    same."""
    return int(key[:8], 16) % 2 == 0


def schedule(box: int, correct: bool, answered_at: datetime) -> tuple[int, datetime]:
    """The box an item moves to after an answer, and when it is due again."""
    box = min(box + 1, len(INTERVALS)) if correct else 1
    return box, answered_at + timedelta(days=INTERVALS[box - 1])


T = TypeVar("T")


def interleave(items: Sequence[T], concept_of: Callable[[T], Hashable]) -> list[T]:
    """The items reordered so the same concept never comes twice in a row
    when that can be avoided: each turn takes the next item of the concept
    with the most left, other than the last one, ties going to the concept
    that came first. Within a concept, the order is kept."""
    queues: dict[Hashable, list[T]] = {}
    for item in items:
        queues.setdefault(concept_of(item), []).append(item)
    first = {concept: n for n, concept in enumerate(queues)}
    result, last = [], None
    while queues:
        choices = [c for c in queues if c != last] or list(queues)
        concept = max(choices, key=lambda c: (len(queues[c]), -first[c]))
        result.append(queues[concept].pop(0))
        last = concept
        if not queues[concept]:
            del queues[concept]
    return result


@dataclass(frozen=True)
class Candidate:
    """An item that could go into a session. place is its concept's place on
    the roadmap."""

    id: Hashable
    concept: Hashable
    due_at: datetime
    place: int
    difficulty: int


def pick(
    candidates: Sequence[Candidate],
    now: datetime,
    *,
    due_only: bool = True,
    limit: int = SESSION_SIZE,
) -> list[Candidate]:
    """A session of at most limit items. Within each concept, the item due
    longest ago comes first, then easier ones; concepts take turns, the one
    whose first item is most overdue (then earliest on the roadmap) first, so
    one concept with many items cannot fill a session. The chosen items are
    then interleaved. With due_only false (practising one stage), items not
    yet due follow the due ones."""

    def priority(c: Candidate):
        return (c.due_at > now, c.due_at, c.place, c.difficulty, str(c.id))

    queues: dict[Hashable, list[Candidate]] = {}
    for c in sorted(
        (c for c in candidates if not due_only or c.due_at <= now), key=priority
    ):
        queues.setdefault(c.concept, []).append(c)
    chosen: list[Candidate] = []
    while len(chosen) < limit and any(queues.values()):
        for queue in queues.values():
            if queue and len(chosen) < limit:
                chosen.append(queue.pop(0))
    chosen.sort(key=priority)
    return interleave(chosen, lambda c: c.concept)
