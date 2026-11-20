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
- Maths is the exception to plain text: formulas are stored as LaTeX, and
  one that would not render drops the item (decision record 24). Every
  rule about prose looks only at the prose, so the | of |A| or the * of A*
  inside a formula is not formatting, and the length limits count each
  formula as one character, with maths.FORMULA_CHARS for their LaTeX.
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

from app import maths

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
    """The text as a learner should read it: formulas in the stored form,
    citation marks and formulaic attributions removed, spacing tidied. None
    if its prose carries formatting or still mentions passages, if it is
    empty, if its prose is longer than limit or its formulas longer than
    maths.FORMULA_CHARS, or if a formula would not render."""
    text = maths.from_model(text)
    if maths.problem(text):
        return None
    text, restore = maths.prose(text)
    if _MARKUP.search(text):
        return None
    text = _ATTRIBUTION.sub("", _CITATION.sub("", text))
    text = re.sub(r"\s+", " ", text).strip()
    text = text[:1].upper() + text[1:]
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)
    if not text or _MENTION.search(text):
        return None
    text = restore(text)
    prose_chars, formula_chars = maths.sizes(text)
    if prose_chars > limit or formula_chars > maths.FORMULA_CHARS:
        return None
    return text


def formula_problem(*texts: str) -> str | None:
    """Why the item is dropped, if a formula in any of its texts would not
    render: named apart from other formatting, so it can be told apart in
    the reasons a generation records."""
    for text in texts:
        reason = maths.problem(maths.from_model(text))
        if reason:
            return f"a formula that would not render ({reason})"
    return None


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
    if reason := formula_problem(question, answer):
        return reason
    clean_question = tidy(question, QUESTION_CHARS)
    clean_answer = tidy(answer, ANSWER_CHARS)
    if not clean_question or not clean_answer:
        return "formatting, a mention of passages, or too long"
    content = {"question": clean_question, "answer": clean_answer}
    return Draft(
        "short_answer", content, tuple(sources), f"{clean_question} {clean_answer}"
    )


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
    if reason := formula_problem(question, explanation, *options):
        return reason
    clean_question = tidy(question, QUESTION_CHARS)
    clean_explanation = tidy(explanation, ANSWER_CHARS)
    tidied = [tidy(_NUMBERING.sub("", option), OPTION_CHARS) for option in options]
    cleaned = [option for option in tidied if option]
    if not clean_question or not clean_explanation or len(cleaned) != len(tidied):
        return "formatting, a mention of passages, or too long"
    if len(cleaned) != OPTIONS or not 1 <= correct <= OPTIONS:
        return "not four options with one correct"
    if len({option.casefold() for option in cleaned}) != OPTIONS:
        return "options repeat"
    order = list(range(OPTIONS))
    random.Random(seed).shuffle(order)
    content = {
        "question": clean_question,
        "options": [cleaned[i] for i in order],
        "correct": order.index(correct - 1),
        "explanation": clean_explanation,
    }
    claim = f"{clean_question} {cleaned[correct - 1]}"
    return Draft("multiple_choice", content, tuple(sources), claim)


def true_false(
    statement: str, truth: bool, explanation: str, sources: Sequence[int], wanted: bool
) -> Draft | str:
    if reason := formula_problem(statement, explanation):
        return reason
    clean_statement = tidy(statement, QUESTION_CHARS)
    clean_explanation = tidy(explanation, ANSWER_CHARS)
    if not clean_statement or not clean_explanation:
        return "formatting, a mention of passages, or too long"
    if truth != wanted:
        return "not the truth asked for"
    content = {
        "statement": clean_statement,
        "truth": truth,
        "explanation": clean_explanation,
    }
    return Draft("true_false", content, tuple(sources), clean_statement)


def flashcard(front: str, back: str, sources: Sequence[int]) -> Draft | str:
    if reason := formula_problem(front, back):
        return reason
    clean_front, clean_back = tidy(front, FRONT_CHARS), tidy(back, ANSWER_CHARS)
    if not clean_front or not clean_back:
        return "formatting, a mention of passages, or too long"
    content = {"front": clean_front, "back": clean_back}
    return Draft("flashcard", content, tuple(sources), f"{clean_front} {clean_back}")


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
