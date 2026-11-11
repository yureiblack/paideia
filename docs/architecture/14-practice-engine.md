# 14. Practice engine

Date: 2026-11-11
Status: accepted

## Context

Phases 11 to 13 gave each environment its concepts, a knowledge graph and a
learning roadmap. Phase 14 makes the environment active: practice items
generated from the source material, answers recorded, and items scheduled
for review.

The roadmap names the techniques to support:

- retrieval practice;
- spaced, distributed review;
- interleaving, where appropriate;
- low-stakes self-testing.

It also names what to avoid: matching "learning styles", which is not
supported by evidence, and any claim of certainty or "perfect learning".

The phase's requirements:

- four kinds of item: short answer, multiple choice, true/false and
  flashcard;
- items generated from source evidence;
- every item keeps its concept, source references, difficulty and
  generation metadata;
- answers submitted and attempts recorded;
- a simple, deterministic review scheduler.

Per-concept learner state is Phase 15.

## What the prototype showed

Before any code, the model (ministral-3:8b) wrote one item of each kind for
five concepts, from each concept's evidence passages.

- **The items themselves were good.** All 20 were answerable from their
  passage. The search reranker scored every answer's support at 0.91 to
  1.00. Some multiple-choice distractors were well chosen: "Priority
  scheduling" as the one non-condition for deadlock.
- **The text talked about its sources.** "(Passage [1])", "according to the
  passages", even a quoted "first sentence of the passage". That is
  meaningless to a student answering without the passages.
- **Options came numbered**, and the correct one was always second or third.
- **Four of five true/false statements were true.**
- **A flashcard's back hit the length limit** and was cut off mid-quote.
- **One question was off its concept:** asked for "Belady's Anomaly", it
  asked about the optimal policy.
- **Each concept took 19 to 27 seconds,** about 13 minutes for 35 concepts.

## Decisions

### Four items per concept, from its own passages

Preparing practice for a concept asks the model for one item of each kind.
It gets:

- the concept's name and definition;
- its evidence passages, numbered.

Each item must cite the passages its answer comes from. The schema allows
only the numbers given (record 08). The backend decides whether the
true/false statement must be true or false, from the concept's fingerprint,
so about half are false and a concept always gets the same. The prompt is
`practice_items/v1`, locked like every released prompt.

### The backend checks every item

`app/practice.py` holds the checks as pure functions. Before anything is
stored:

- **Text** must be plain and within bounds, and must not mention passages.
  Bracketed citations are removed, and so are formulaic attributions where
  the sentence stays whole: "according to the passages", "as mentioned in
  passage 1", "the passage states that". Any other mention drops the item.
- **Multiple choice:**
  - the four options must differ, once any numbering the model added is
    stripped;
  - the backend shuffles them with a fixed seed per item, so the right
    answer's position gives nothing away and is the same every time.
- **True/false statements** must be true or false as asked.
- **Grounding:** the search reranker must score the item's answer against
  the passages it cites at 0.5 or more. For true/false, it scores the
  statement: the reranker checks that the item is about what its passage
  says, not whether it is true.

Items failing a check are dropped, and the reason is recorded. A generation
where every item fails is marked failed, with the reasons.

The schema's string limits are half as long again as the checks' limits.
An overlong answer is then refused whole, rather than cut off mid-sentence
as the prototype's flashcard was.

### The prompt, revised before release

The first wording asked plainly not to mention or cite the passages. The
model did anyway, mostly in explanations: "passage 1 explicitly states that…".
Only 11 of 20 items were kept.

The released prompt adds one concrete wrong and right example: "FIFO
suffers from Belady's anomaly", not "Passage 1 states that FIFO suffers from
Belady's anomaly". With it, 18 of 20 items were kept. With the repair of
formulaic attributions as well, 31 of 32 items were kept across eight
concepts, about 19 seconds per concept.

### Difficulty by kind, as effort

Difficulty comes from the kind of item, not from the model:

- **1:** true/false and flashcards, which mean recognising a statement or
  recalling with a cue;
- **2:** multiple choice, picking among close options;
- **3:** short answer, recalling unprompted.

It describes effort, not a measured difficulty. Phase 12 showed that the
model's own judgements, such as its confidence, do not discriminate.

### Generation metadata, and items that follow their material

Every item records:

- its concept, kind, content and key, and difficulty;
- the passages it cites, which are deleted with their chunks;
- the model and prompt;
- its support score and the generation it came from.

A concept's evidence key fingerprints what the model saw: the concept's
normalized name, its definition and its passages' content. An item is
practised only while its key is the concept's current one, which is checked
live. When the material changes, its items stop being practised and the
concept shows as outdated. Preparing it again writes new items and retires
the old ones. They are kept with their attempts, and answering one is
refused.

Each generation is a generated artifact (`practice_set`) keyed by the
evidence key, model and prompt, so the same passages are never written for
twice. Generation happens on request, not by itself: "Prepare practice" for
a stage or a concept. It runs in the background, one concept at a time,
under the one-at-a-time model lock.

### Grading: the key or the learner, never the model

- **Multiple choice and true/false** are checked against the stored key. The
  key is never sent to the page before answering.
- **Short answers and flashcards** are marked by the learner: they write or
  think of an answer, reveal the stored one, and mark "I knew it" or "Not
  yet". Their answer travels with the item for the page to reveal.

Model grading was rejected: it is slow, unreliable, and the model must not
decide outcomes.

Every answer is recorded as an attempt with:

- what was answered;
- whether it was right;
- whether the key or the learner graded it;
- when, and how many seconds it took.

### Review by Leitner boxes

Each item has a box and a due time, in `review_schedule`.

- A new item is in box 0, due at once.
- A correct answer moves it up a box: it comes back after 1, 2, 4, 8, then
  16 days, and stays at 16.
- A wrong answer sends it back to box 1, due the next day.

The scheduler is a pure function with no model involved, unit-tested.
Phase 15 adds per-concept learner state on top.

### Sessions: due items, concepts taking turns

A session holds at most 10 items. Within each concept, the item due longest
ago comes first, then the easier ones. Concepts take turns filling the
session, the most overdue first, then the earliest on the roadmap. The
chosen items are then interleaved: the same concept never comes twice in a
row when that can be avoided.

The first version took the ten most overdue items. One concept with many
items could then fill a session, which its test caught.

Practising a stage takes that stage's items, due ones first, then the rest.

## The API and the pages

- **`GET /api/environments/{id}/practice`:** what is due, how many items are
  practised, when the next is due, and each concept's state.
- **`POST /api/environments/{id}/practice`** and
  **`POST /api/concepts/{id}/practice`:** prepare items in the background.
- **`GET /api/environments/{id}/practice/session`:** a session of due items,
  or with `concept_id` repeated, a stage's.
- **`POST /api/learning-items/{id}/attempts`:** answer an item. The result
  says whether it was right, gives the answer and why, the passages it comes
  from, and when the item comes back.

The Practice tab says what this is, in plain words: study support built on
well-studied techniques, with nothing a grade. It shows what is due, with
Start practice, then every roadmap stage with Prepare practice, progress
while items are written, and Practise this stage.

A session shows one item at a time. After each answer comes:

- whether it was right;
- the answer and why;
- the source chips;
- when the item comes back.

Each Roadmap stage card shows its practice state too, and links to that
stage's session.

## Testing

- **The rules (pure):**
  - citation marks and attributions removed;
  - mentions of passages, formatting and overlong text refused;
  - option numbering stripped;
  - the same shuffle every time, with the right answer moving between items;
  - options distinct, four, one correct;
  - truth as asked, about half asked to be false;
  - difficulty by kind;
  - the Leitner boxes;
  - interleaving, and sessions taking concepts in turns.
- **The service, with scripted answers:**
  - four checked items written from a concept's passages, with sources,
    metadata and schedules;
  - preparing again writes nothing;
  - failing items dropped and counted;
  - unsupported items never stored;
  - a failure recorded and retried;
  - changed material retires items and keeps their attempts;
  - grading by key and by learner;
  - review moving up the boxes;
  - sessions of due items interleaved, and stage sessions;
  - the overview's counts.
- **The API:**
  - items prepared in the background;
  - sessions hiding the key of graded kinds;
  - answers graded, with citations identical to source previews;
  - stage sessions;
  - a wrong kind of answer, an unknown item, an empty request and a replaced
    item all refused.
- **Deliberate breaks.** Eighteen deliberate breaks, from not shuffling to
  sending the key, were all caught the first time.
- **The real model.** The real-model test prepares practice for the first
  roadmap concept. It checks that at least two items are kept and that none
  mentions passages or carries formatting.
- **In the browser, with the real model:**
  - Stage 1 (Thread, Context Switch) was prepared in 48 seconds: the page
    followed along to "8 practice items, 8 due now";
  - the session alternated between the two concepts, answered every kind of
    item, and showed the right answer, the explanation, the sources and when
    each item comes back;
  - afterwards nothing was due until the next day;
  - the Roadmap stage card showed the stage's items and opened its session;
  - the session fit a phone's width in the dark theme, with no console
    errors.

## Consequences

- Preparing practice costs about 20 seconds of model time per concept, so it
  is done stage by stage, on request.
- The checks keep only what the material supports. The price is the odd good
  item dropped for mentioning "the passage" in an unusual way.
- The correct multiple-choice option is often the longest and most detailed:
  a known giveaway of generated questions that no rule here removes.
- Two concepts explained by the same passage can get near-identical
  questions. Thread and Context Switch both asked how switching threads
  differs from switching processes.
- Self-marked items depend on the learner's honesty with themselves. That is
  intended: the stakes are only when an item comes back.
