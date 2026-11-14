# 17. Incremental updates

Date: 2026-11-14
Status: accepted

## Context

The roadmap calls this one of the most important phases: make "add another
PDF" genuinely intelligent. When a document or a new version is added, the
app should:

1. hash the source;
2. detect exact duplicates;
3. extract pages;
4. chunk deterministically;
5. reuse unchanged chunk embeddings by content hash;
6. embed only new chunks;
7. update affected concepts;
8. update affected relationships;
9. mark dependent generated artifacts stale;
10. regenerate only affected artifacts.

It should never rebuild the whole environment blindly. An explicit update
record lets the page show progress, and a report of new concepts, changed
relationships, what was updated and what was left unchanged.

## What already existed

Most of the list was built in earlier phases:

| Steps | State before this phase |
|---|---|
| 1–4 | Done (records 03, 04): a SHA-256 per file, identical files refused per environment, pages, and deterministic chunks whose ids come from the document and the text. |
| 5–6 | Only within one document: a reprocess kept a passage's row and embedding. A revised lecture uploaded as a new document, or the same passage in another document, was embedded again. |
| 7 | Done: only the new document is read for concepts, and they merge by name. |
| 8 | Done: the graph asks the model only about new pairs (record 12). |
| 9 | Done: every derived result is keyed by what it was built from. |
| 10 | Done for the graph, roadmap titles and practice. The environment's summary is rebuilt from the document summaries, one model call. |

Missing were embedding reuse across documents, document versions, and the
update record with its report.

## Decisions

### Embeddings reused by text

Before a passage is embedded, any stored passage with the same text, embedded
by the same model, in any document, gives its vector. The same text always
gives the same vector, so nothing about other material is revealed. Only
passages without a match are embedded. `document_chunks.content_hash` gained
an index for the lookup.

### Document versions

"Upload a new version" replaces a document's file and fingerprint but keeps
the document: its id, name and place in the reading order.

- A passage's id comes from its document and its text, so every passage the
  new version shares with the old keeps its row, embedding and concept
  evidence.
- The document's summary and concepts are written for the new text. Earlier
  summaries are kept.
- The graph asks only about new pairs, and the roadmap titles only changed
  stages.

A version identical to the current file is refused, as is one identical to
another document in the environment, or a version uploaded while the
document is being read. Reusing summary and concept work section by section
was rejected: most lectures are one section, and it would be a deep change.

### Practice follows the passages it cites

Phase 14 retired a concept's items whenever its passages changed in any way.
The browser check showed what that meant: adding Week 5, which merely
*mentions* Round Robin and SJF, gave those concepts new passages, so their
practice was retired. The roadmap's own example says "Unchanged: existing
practice items".

The rule now: an item is practised while every passage it cites is still
there, unchanged. Each item records how many it cites; a changed passage has
a new id, so the old one is deleted with its source row. New passages for a
concept leave its items alone. A concept whose items lost a passage is
outdated, and preparing it again writes new items and retires the old ones
with their attempts.

### Decisions outlive their concepts

A second browser check deleted Week 5 and added it again, and found a Phase
12 bug: the map came back with 57 relationships instead of 72, and nothing
was asked of the model.

- **Lost decisions:** the graph's remembered decisions were deleted along
  with their concepts.
- **A build that looked complete:** the earlier build for those same pairs
  was found ready, and its edges were rebuilt from what was still remembered,
  silently leaving out the rest.

Two changes fix it:

- **Decisions outlive their concepts.** A decision belongs to its key: the
  concepts' names and the passages' text. Its links to concept rows are now
  set to null when a concept goes, instead of deleting the decision.
  Migration 11 changes the foreign keys.
- **A build is only ready if every current pair has a decision.** A build
  found again with decisions missing is written again, asking only about
  those pairs.

### An update record for every change

Every upload, new version, reprocess and deletion creates a row in
`material_updates` (migration 11). Each row holds:

- the change's kind, document and filename;
- its status: running, done or failed;
- its steps;
- a report.

Each background step is run through `updates.run_step`, which marks it
running, calls the same function the chain always called, then records its
state and what it did in plain words. For example:

- "3 passages: 1 new, 2 kept, 1 removed. 1 embedded, 0 found already
  embedded by their text";
- "The model was asked about 6 new pairs; 76 were remembered";
- "Back to the map of these concepts built earlier; nothing new asked".

A failed step is recorded with its reason. Steps that could not run are
skipped, and the update is marked failed.

### The report: before and after

When an update starts, it takes a snapshot of:

- the concepts and relationships;
- each document's summary;
- the *current* environment summary, graph and roadmap titles, the ones for
  the material as it is, not the newest written;
- which concepts have practice.

When it ends, it compares a second snapshot. The report gives:

- concepts and relationships, new and removed;
- passages new, kept and removed, and embeddings computed and reused;
- for each result, updated or unchanged;
- practice items to prepare again, and those kept.

Comparing current results matters when a deletion returns the material to
what it was: the results written then become current again. The first
version compared the newest results and called them "Unchanged". It now
says "Back to the summary written earlier for these documents". A build
written again during the update (asking only for missing pairs) is told
apart from one simply found again.

## The API and the Materials tab

- **`POST /api/documents/{id}/versions`:** a new version, as the raw PDF body.
- **`GET /api/environments/{id}/updates`:** the environment's updates,
  newest first.
- **`GET /api/updates/{id}`:** one update.

The Materials tab shows the latest update at the top. Its steps tick off
live, every second and a half while it runs, each with what it did. When it
is done, "What changed" follows: concepts and relationships, then Updated and
Unchanged. Earlier updates sit below, each opening to its own report. Every
document has "Upload a new version".

## Testing

- **Embedding reuse:** a revised copy in another environment embeds only its
  edited passage, with the very same vectors for the rest; a reprocess
  reports passages new, kept and removed.
- **Update records, through the API:**
  - an added document records each step and what changed;
  - a second document reports only its own changes, and that the first's
    summary was kept;
  - a new version keeps the document and its unchanged passage, embeds one
    passage, and makes only Round Robin's practice outdated;
  - identical versions are refused;
  - a deletion records what went, and that its results went back to earlier
    ones;
  - a failed read marks the update failed and skips what follows.
- **The report rules:** relationships changing with the same build behind
  them; nothing changed means everything unchanged.
- **Practice:**
  - new passages keep a concept's items;
  - a changed cited passage retires them, keeping their attempts;
  - an item citing two passages is retired when either changes.
- **The graph:**
  - a document deleted and added again finds every decision and asks
    nothing;
  - a ready build missing decisions asks only for those.
- **Deliberate breaks.** Eighteen deliberate breaks, across reuse, versions,
  reports, practice and the graph. Two needed a second look:
  - one survived until a direct test of the report rule was added;
  - one looked caught but had broken the code itself, and was run again
    properly.
- **In the browser, with the real model**, on the trial environment, three
  times:
  - adding Week 5: steps live, then 5 new concepts and their relationships,
    "Other documents' summaries: 3 kept", "Practice items: those of 9
    concepts kept";
  - a new version: 2 passages kept, 1 new, 1 removed, 1 embedded, "+ Log
    Replay, + Metadata Journaling, − Log";
  - the same file again: refused;
  - deleting it: everything "back to" the earlier results;
  - adding it again: "nothing new asked", the map whole;
  - the page fit a phone's width.

  The console showed only the summary not yet written (a 404 by design) and
  the deliberately refused version (409).

## Consequences

- A new version's own summary and concepts are always written again, even
  when most of the text is unchanged, about a minute for a short lecture.
  Everything shared with other documents is reused.
- The environment's summary is rebuilt whenever a document's summary
  changes; it is one model call.
- Update records grow with every change. They are small, and an environment's
  deletion takes them with it.
- Decisions about pairs now outlive their concepts, so the decision table
  only grows. It is keyed per environment and goes with the environment.
