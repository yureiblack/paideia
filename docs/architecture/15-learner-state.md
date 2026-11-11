# 15. Learner state and spaced review

Date: 2026-11-11
Status: accepted

## Context

Phase 14 added practice items, answers and a per-item review schedule
(Leitner boxes). Phase 15 makes the system react to the learner's actual
performance, per concept. The roadmap asks for each concept:

- an exposure count;
- successful and failed recall counts;
- when it was last attempted, and last recalled;
- the current review interval and the next review date.

It also asks for:

- a simple, explainable scheduling function that is deterministic and
  unit-testable;
- a correct answer to increase the interval, and a failed one to reduce or
  reset it;
- no language model for dates or intervals;
- a page showing what is due today, what needs attention and what is
  recently strong.

This phase involves no model, so there was nothing to prototype.

## Decisions

### Worked out from the answers, never stored apart from them

A concept's learner state is derived. Its answers, to all its practice
items including retired ones, are replayed in the order they were made
through one pure function (`app/learner.py`). The same answers always give
the same state. The state can always be explained by the answers, and there
is no second copy to drift from them, nothing to backfill and no migration.

A `concept_state` table updated on every answer was rejected: it is a
second copy of the truth.

The cost is replaying an environment's answers on each read: a few hundred
rows, cheap.

### The schedule

- **Gaps:** reviews are 1, 2, 4, 8, 16, then 32 days apart.
- **A recall** moves the concept's gap one step up, at most once a sitting:
  a recall within 12 hours of the gap's last change does not move it again.
  Two right answers in one session count once, though every answer is still
  counted.
- **A miss** puts the gap back to 1 day, and a recall in the same sitting
  after a miss does not undo it.
- **The next review** is the last answer's time plus the gap.
- **New concepts:** a concept with practice items but no answers is new, and
  due at once.

For example: right on Monday, so it is due Tuesday. Right on Tuesday, due
Thursday. Right on Thursday, due the following Monday. Missed then, due the
next day.

"At most once a day" became "at most once a sitting", 12 hours. The server
does not know the learner's calendar day, and a rolling window needs no time
zone. It matches the intent: one session counts once.

### Due today is the learner's own today

The page sends the end of its own day, with its time zone. A concept is due
today when its next review comes by then. A value without a time zone is
refused, so "today" is never guessed.

### Sessions from due concepts

A session is built from the concepts due today, not from item dates:

- overdue concepts first, the longest overdue first;
- then new concepts, in roadmap order;
- two items from each concept, of different kinds where it has them, those
  in the lowest box and answered longest ago first;
- at most ten items, interleaved.

Each item's Phase 14 box still moves with every answer. It now only decides
which of a concept's items come first. Practising one stage is unchanged.

An answer's result now gives when its concept comes back, `due_at` and
`gap_days`. The item's own box is still returned as `box`.

### Needs attention and recently strong

- **Needs attention:** the concept was missed on its last answer, or fewer
  than half of its last six answers were recalled (with at least two
  answers).
- **Recently strong:** recalled on its last answer, with a gap of four days
  or more. The longest gaps come first, at most five.

Each is shown with its reason: "Missed on its last answer", "Recalled 2 of
its last 5 answers", "Recalled; next review in 8 days".

## The API and the pages

`GET /api/environments/{id}/practice?until=…` gains each concept's learner
state:

- whether it is new, due or scheduled;
- its answer, recall and miss counts;
- when it was last attempted and last recalled;
- its gap and next review;
- why it needs attention, if it does.

It also gains how many concepts are due today and how many are new, the
next later review, and both lists. Item-level due counts gave way to these.
The session takes `until` as well.

On the Practice tab:

- **Plain words first:** a short explanation of the schedule.
- **Due today:** "Due today: N concepts" (and how many are new), with Start
  practice.
- **The two lists:** Needs attention and Recently strong, each concept
  linking to the Knowledge map.
- **Then the stages.**

The Knowledge map explorer and every Roadmap concept show its state in a
line: "Answered 4 times, recalled 3 · next review 12 Nov 2026", plus the
attention note when there is one.

## Testing

- **The schedule (pure), each rule with its own test:**
  - new concepts are due at once;
  - each recall moves one step;
  - recalls in one sitting count once, and a new sitting moves again;
  - a miss brings the concept back the next day and wins its sitting;
  - the gap stops at 32 days;
  - the same answers always give the same state;
  - due by a given time;
  - needs attention, counting only the last six answers;
  - recently strong;
  - sessions: overdue before new, roadmap order, two items of different
    kinds, lowest box first, bounded and interleaved.
- **The service:**
  - due sessions take two items from each due concept, and a concept
    answered today waits until tomorrow;
  - stage sessions take all items;
  - the overview gives each concept's state, the counts and the lists;
  - a concept recalled over three days becomes recently strong, with gaps
    of 1, 2 and 4 days;
  - item boxes still move.
- **The API:** "due today" follows the learner's end of day, and a time
  without a time zone is refused. The Phase 14 tests were updated to the
  concept-level schedule.
- **Deliberate breaks.** Fifteen deliberate breaks, from ignoring the
  sitting rule to replaying answers out of order, were all caught the first
  time.
- **Flakiness.** One test gave two answers the same instant, so their order
  fell to random ids: it failed in 5 of 10 runs. Real answers never share an
  instant. The test now spaces them a minute apart, and passes in 10 of 10
  runs.
- **A bug found by the API tests.** A concept with items but no answers had
  no state yet, so the recently-strong list failed for it.
- **In the browser, with the real model.**
  - Stage 2 was prepared in 70 seconds, and the page showed three new
    concepts due today.
  - The session gave two items per concept, alternating, and each answer
    said when its concept comes back.
  - Needs attention then listed the three concepts missed on purpose, with
    their reasons.
  - The Roadmap and Knowledge map showed each concept's line.
  - The page fit a phone's width in the dark theme, with no console errors.

## Consequences

- The schedule is deliberately simple and explainable, not tuned to the
  learner. It does not weigh answer kinds or response times; those are
  recorded for later.
- Self-marked answers count like graded ones. The stakes are only when a
  concept comes back.
- Replaying every answer on each read is cheap at this scale. A cache could
  be added later without changing the rules, since the replay defines the
  state.
- Phase 16 (study plans) can build on "due today", the review dates and the
  attention list.
