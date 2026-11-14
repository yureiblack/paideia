# 19. Dashboard and product polish

Date: 2026-11-14
Status: accepted

## Context

By Phase 18 every capability was in place, but each tab had been built on
its own and it showed:

- The Overview tab held today's plan and the environment's dates, nothing
  more.
- Practice showed what was due, but no history and no picture of how each
  concept was going.
- Each tab handled loading and failure its own way. 12 of the 26
  components could not try again after a failed load, and some showed
  nothing at all when they failed.

The roadmap asks for the following, with nothing new for the language model to do:

- an environment dashboard with the master summary, a knowledge graph
  preview, roadmap progress, the current study plan, the review due count,
  recent material and processing activity;
- a material page with source documents, processing state, source pages and
  summaries;
- a practice page with due items, session history and concept performance;
- loading, empty, error and retry states throughout.

## Decisions

### The Overview tab is the dashboard

From top to bottom:

1. The numbers at a glance: concepts due for review today, concepts,
   documents, and how much of the roadmap is strong.
2. Today's plan (record 16).
3. Each roadmap stage's progress.
4. The opening of the environment's summary, with a link to the full one.
5. The knowledge map in a few lines.
6. Recent material.
7. How recent background work ended. Work in progress is followed live in
   the strip above the tabs (record 18).

It is one column on a phone and two columns below the plan on a wide
screen. The environment's dates are at the bottom.

The numbers were first planned below today's plan. In the browser, a plan of
five sessions pushed them 800 pixels down the page, so they moved to the
top.

### Built from what the tabs already fetch

Every section reads the same data as its own tab, through the same hooks,
so the two share one cached copy, and each section loads, fails and tries
again on its own.

One `/dashboard` endpoint was rejected. It would repeat logic the other
endpoints already hold, and one failure would blank the whole page. In the
browser, with every section's requests failing, each of the ten sections
showed its own message and Try again, and trying again in one left the
others as they were.

### The knowledge map preview is in words

The map itself is plain lists, not a drawing (record 12), so the preview is
too:

- how many concepts and relationships there are;
- where to start: concepts others build on that build on nothing
  themselves, those most built on first;
- the most connected concepts.

Each concept links into the map's explorer. A drawn mini-graph was rejected:
it needs a drawing library or a hand-made layout, and it cannot be read on a
phone.

### Roadmap progress reuses the "strong" rule

Each stage shows two counts and a bar:

- **Practised:** concepts answered at least once.
- **Strong:** concepts recalled on their last answer after a gap of four
  days or more.

"Strong" is the rule the Practice tab already used for "Recently strong"
(record 15). A new rule with a three-day gap was planned first. Reusing the
existing one means the dashboard and the Practice tab never disagree. The
practice overview now carries `strong` for each concept, set by the backend,
so the browser never repeats the rule.

### Session history comes from the answers

Nothing recorded a practice session, and none is recorded now. Answers less
than 30 minutes apart belong to the same session, and 30 minutes or more
starts another. `GET /api/environments/{id}/practice/history` returns the last
20 sessions, newest first. Each has:

- when it started and ended;
- its answers, and how many were recalled;
- its concepts, in the order first answered.

Answers to retired items still count; a concept's answers go when the
concept does, with its items.

A sessions table was rejected. It needs a migration and changes to the page,
and the answers given before it existed would belong to no session.

### The Practice tab

- **Due items:** the concepts due today, by name, each a link, with new
  ones marked.
- **Concept performance:** every practised concept, with its answers, how
  many were recalled and a bar of the share, the current gap and the next
  review. Weakest first: those needing attention, then the lowest share
  recalled.
- **Session history:** as above.

All three come from data the tab already had, apart from the history.

### Materials

Each document already showed its status, page count, a page reader and its
summary on request. It now also shows:

- the opening of its summary, without expanding it;
- while its background work runs, that job's step and progress. A job names
  the material update it carries out, and the update names its document.

### Loading, failure, nothing yet

Three shared components (`components/query-states.tsx`) are used by every
section that loads data:

- **Loading:** placeholder lines, announced to screen readers. They pulse
  only for people who have not asked for less motion.
- **Failure:** why, and Try again. A request that never reached the API
  says "Could not reach the API. Is the backend running?".
- **Nothing yet:** what that means and what to do next, such as Upload a PDF.

Queries still retry by themselves twice before a failure shows, as before.

### Titles, font and focus

- **Titles:** each browser tab names the page and the environment, such as
  "Practice · Operating Systems · Paideia". Setting the title from a hook
  lost a race with Next.js, which streams its own title after the page
  loads, so most tabs ended up as plain "Paideia". The site title now comes
  from the home page alone, and the environment's shell renders React's
  `<title>`, so each page has exactly one title.
- **Font:** the body used Arial, left over from the project template, while
  Geist was loaded and never used. It now uses Geist.
- **Focus:** keyboard focus shows a 2-pixel ring in the text colour of
  either theme, and none for mouse clicks. The rule sits in Tailwind's base
  layer: outside any layer it beat every utility, which kept the tabs from
  drawing their ring inside the row that scrolls sideways on a phone.

## Testing

- **Session history, against Postgres:**
  - 29 minutes 59 seconds apart is one session, 30 minutes is two;
  - newest first, and only the last 20;
  - only the environment's own answers;
  - retired items' answers stay, and a removed concept's answers go;
  - the `strong` flag;
  - the endpoint, and 404 for an unknown environment.
- **Deliberate breaks.** Ten deliberate breaks of the history's rules were
  all caught. Ordering the concepts by name was missed at first: with two
  concepts, the order they were first answered in happened to be reverse
  alphabetical. The test now uses three concepts, answered in an order
  neither alphabetical nor reversed.
- **In the browser, with real data** (4 documents, 41 concepts, 69
  relationships, 10 stages, 3 past sessions):
  - every tab at desktop width in the light theme, and at phone width (390
    pixels) in the dark theme, with nothing scrolling sideways;
  - each tab's title, after loading it and after moving to it from another
    tab, the home page's after leaving, and an unknown environment's;
  - the Practice tab and the dashboard with every request failing, then
    tried again;
  - a new, empty environment's empty states on every tab;
  - keyboard focus in both themes.

  The only console message was the expected 404 for the unknown
  environment.

## Consequences

- The dashboard makes seven requests: today's plan, practice, documents, the
  roadmap, the summary, the map and the jobs. Three of them (the plan,
  practice and the jobs) were made before this phase, and all are shared
  with the tabs. At this project's size that costs nothing noticeable.
- Session history is computed from all of an environment's answers on each
  request, as the learner state already is. If answers ever number in the
  hundreds of thousands, both would need a cache.
- The 30-minute gap is a convention, stated under the history: two sittings
  close together count as one session.
- Nothing new calls the language model.
