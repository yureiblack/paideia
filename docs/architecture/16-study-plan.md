# 16. Automatic study plan

Date: 2026-11-12
Status: accepted

## Context

By Phase 15 each environment knows:

- its roadmap of stages;
- each concept's learner state: due today, needing attention, or recently
  strong;
- its documents and when they were added.

Phase 16 turns that into a plan for the day. The roadmap asks for a
deterministic planning service:

- **Inputs:** due review items, weak concepts, roadmap position, newly
  added material, and an optional daily time budget.
- **Output:** ordered study sessions, each with a rationale, estimated
  effort and source concepts.

The model may turn the plan into friendly text, but the scheduling and order
must stay deterministic. A dashboard widget shows today's recommended plan.

## Decisions

### A pure planner, worked out afresh

`app/planner.py` holds the rules as pure functions, with no database and no
model. `app/services/planner.py` gathers their inputs from what is already
stored:

- each concept's learner state and practice items;
- the roadmap;
- the documents, with their dates and summaries;
- the evidence passages' lengths;
- the learner's own answer times.

Nothing is stored: the plan is worked out whenever it is read.

### Four kinds of session, in this order

Each concept appears in at most one session.

1. **Strengthen:** concepts that need attention, that is missed on their
   last answer or mostly missed lately. Re-read their passages, then answer
   again: a miss is cheapest to fix while it is fresh.
2. **Review:** concepts due today, in the learner's own day. Spaced review
   only works when it is on time.
3. **Learn:** the next roadmap stage with concepts not yet practised. Read
   the passages, prepare practice if it is not written yet, then practise.
   New learning builds on ground already reviewed.
4. **Skim:** a document added in the last seven days with none of its
   concepts practised. Its summary gives the overview before its stages come
   up.

Sizes and limits:

- Strengthen and Review sessions hold at most five concepts. More make
  further sessions, in roadmap order.
- There is one Learn session, and at most two Skims, newest first.
- A weak concept whose items were retired when its material changed is not
  strengthened: there is nothing to answer until it is prepared again.
- A document whose concepts all fall in the Learn session is not skimmed as
  well.

### Effort, explainably

- **Reading** is counted at 200 words a minute, over the session's passages,
  each passage once even when concepts share it.
- **Answering** is two items per concept. Each kind of item is timed at the
  learner's own median once they have five timed answers of that kind (Phase
  14 records the seconds). Until then the defaults apply: 30 s for
  true/false and flashcards, 60 s for multiple choice, 90 s for short
  answers. A concept without prepared items is timed at the mean of all
  kinds.
- **Rounding:** whole minutes, rounded up, at least one.
- **By kind:**
  - Strengthen and Learn are reading plus answering;
  - Review is answering only;
  - Skim is reading the summary.

### An optional budget

Given a budget in minutes, the planner takes sessions in order while they
fit. A session that does not fit goes to "With more time", and a smaller one
after it may still fit. Without a budget, the whole plan is shown.

### Rationale from templates, not the model

Each session explains itself in one or two sentences built from its
numbers:

- "3 concepts missed on the last answer, or mostly missed lately…";
- "2 concepts due for review today… it is now 1 day";
- "Next on your roadmap: stage 3, with 4 concepts not practised yet… Its
  practice items need preparing first";
- "Added 2 days ago, and none of its 12 concepts practised yet…".

The roadmap allows the model to write friendly text. Templates say the same
thing instantly, on every view, and cannot drift from the numbers, so no
model is involved.

## The API and the pages

**`GET /api/environments/{id}/plan?until=…&minutes=…`** gives the sessions in
order. Each has its kind, title, estimated minutes, rationale and concepts,
and the roadmap stage or document it opens. With a budget, the sessions
that did not fit come in `later`. `until`, the end of the learner's day,
must carry a time zone.

**On the Overview tab, "Today's plan" shows:**

- the number of sessions and the total minutes, with a note that times are
  estimates;
- each session numbered, with its minutes, title, rationale and concepts,
  each concept linking to the Knowledge map;
- an action for each session:
  - Strengthen and Review: **Start** opens a practice session for exactly
    those concepts;
  - Learn: **Read on the roadmap** opens its stage, and **Prepare practice**
    or **Practise**;
  - Skim: opens the materials with the document's summary;
- a time budget picker (no limit, 15, 30, 45, 60 or 90 minutes), remembered
  in this browser;
- "With more time" for what does not fit.

While practice is being prepared from the plan, the plan follows the
preparation and updates when it is done.

**On the dashboard,** each environment's card shows "Today: N sessions · M
min".

## Testing

- **The planner (pure):**
  - weak, then due, then the next stage, then recent material;
  - effort that reads each shared passage once and counts two answers per
    concept;
  - the learner's own pace once known;
  - no concept twice;
  - big groups split in roadmap order;
  - the next stage is the first with concepts not yet practised;
  - only recent, untouched documents with a summary are skimmed, newest
    first;
  - a budget taking sessions in order while they fit;
  - the same inputs in any order give the same plan;
  - an empty plan;
  - weak concepts without items are not strengthened.
- **Through the API, with a stand-in model:**
  - real uploads, practice and answers give Strengthen, Review, Learn
    (needing preparation) and Skim in order;
  - a budget moves what does not fit;
  - six quick answers of each kind turn a six-minute review into one
    minute;
  - bad budgets, times without a time zone and unknown environments are
    refused.
- **Deliberate breaks.** Fourteen deliberate breaks. Three survived at first
  and showed gaps in the tests: reading shared passages twice, a weak concept
  without items, and documents older than a week. They are all caught now.
- **In the browser, on the trial environment, with the real model:**
  - the dashboard card read "Today: 5 sessions · 22 min";
  - the Overview listed:
    1. Strengthen, 6 min;
    2. Review, 4 min;
    3. Learn stage 3, 8 min, needing preparation;
    4. two Skims;
  - a 15-minute budget moved Learn to "With more time", and the choice
    survived a reload;
  - Start on Strengthen opened a session for exactly those concepts;
  - Prepare practice on Learn finished in 92 seconds, and the session then
    offered Practise;
  - the page fit a phone's width in the dark theme, with no console errors.

  The automated answers were near instant, so after them the plan estimated
  about a minute per session from that "pace". A person's real answer times
  give real estimates.

## Consequences

- The plan is as good as its inputs. Missed concepts come first even when a
  review is more urgent by date. That is a deliberate, explainable priority,
  not an optimisation.
- Effort estimates are rough: a reading speed and answer times. They are
  stated as estimates on the page.
- Phases 17 and 18 (incremental updates, background processing) can make
  the inputs fresher without changing these rules.
