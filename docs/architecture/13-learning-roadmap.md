# 13. Learning roadmap

Date: 2026-11-10
Status: accepted

## Context

Phase 12 gave each environment a knowledge graph: concepts joined by
`PREREQUISITE_OF`, `PART_OF` and `RELATED_TO`, each relationship citing its
passages. Phase 13 turns it into an ordered learning path, in stages. The
roadmap's rules for this phase:

- prerequisites come before the concepts that depend on them, where the
  graph supports it;
- cycles are detected and handled explicitly;
- concepts with strong evidence are prioritized;
- every roadmap node shows its source documents.

The algorithm is deterministic: a DAG from the prerequisite edges, a
topological order, related concepts grouped into stages, source material
attached. The model only writes human-readable stage descriptions. It never
decides the ordering.

## What the prototype showed

Before any code, the suggested algorithm was run on the graph of three
lectures from Phase 12's trial: 35 concepts, 9 prerequisite edges, 8 part-of
and 37 related. No model was involved.

- **Prerequisites are too sparse to stage by.** 29 of the 35 concepts have
  no prerequisite at all. Stages by depth in the prerequisite DAG would put
  29 concepts in Stage 1.
- **Groups of related concepts make natural stages,** with one catch.
  Grouping concepts joined by any relationship gave recognisable topics. But
  one relationship across lectures, "Context Switch" related to "TLB", glued
  the scheduling lecture's threads to the memory lecture's paging.
- **Groups within each lecture work.** The rule: groups of concepts joined by
  any relationship, inside the document where each concept first appears.
  Ordered by the prerequisites between groups, then by reading order, this
  gave nine stages that read like a course outline:
  1. threads and context switches;
  2. round robin;
  3. the shortest-job family;
  4. critical sections and priority inversion;
  5. mutexes and race conditions;
  6. semaphores;
  7. deadlock;
  8. paging and the TLB;
  9. page replacement.

## Decisions

### The rules decide the structure

`app/roadmap.py` holds the rules as pure functions, with no database and no
model.

- **Cycles.** Prerequisites that loop, perhaps through several concepts,
  cannot all be honoured. Each loop is found as a strongly connected
  component, kept in one stage, in reading order, and reported, so the page
  can say "learn these together".
- **Stages.**
  - Concepts joined by any relationship within the document where each first
    appears form a group.
  - A relationship across documents orders groups but never merges them.
  - A concept with no relationship inside its document joins the group of
    its neighbour there in reading order: the one before it, else the one
    after.
  - A document with no relationships at all is one group.
- **Stage order.** Groups follow the prerequisites between them, then where
  their first concept is taught. Groups whose prerequisites loop are merged
  first.
- **Order within a stage.** Prerequisites come first. A whole comes before its
  parts, unless a prerequisite says otherwise. Then the concept with more
  evidence passages comes first, then reading order.
- **Size.** A stage of more than eight concepts is split, in order, into
  stages as even as possible.

Reading order means the order the documents were added, then each passage's
place in its document. Every tie ends in the concept's normalized name, so
the same material always gives the same roadmap, whatever order it arrives
in.

The structure is computed afresh whenever the roadmap is read. It is cheap,
and that way it always matches the concepts and the graph.

### The model only titles the stages

For each stage, the model writes:

- a title of at most six words;
- one sentence of at most thirty words, starting with a verb: "Learn how
  page tables and TLBs convert virtual addresses…".

It is given only the stages' concept names and definitions, by stage
number, and its answers are matched back by that number. It cannot add,
remove or reorder anything. The prompt, `roadmap_stages/v1`, is locked like
every released prompt.

The first wording gave good titles, but every description began "The
student learns…". The released one asks for a verb first.

A title is used only when:

- it has at most eight words, and its description at most 45;
- neither carries Markdown, a list bullet or a line break;
- it does not start with "Stage".

A stage without a usable title shows a plain one, such as "Deadlock and 6
more". The roadmap never waits for the model: while titles are being written,
or when the model fails, the stages and their order are shown regardless.

### Titles are remembered by stage

A stage's key is its concepts' normalized names and definitions, in order:
what the model sees. Titles are stored as a generated artifact,
`learning_roadmap`, keyed by the roadmap's stage keys, model and prompt.
Every title written before is looked up by its stage key. So adding a
lecture asks only about the stages it changed. Unchanged stages keep their
titles instead of being renamed on every change, and deleting a lecture
asks nothing.

Migration 9 only widens the generated-artifact types: the roadmap needs no
table of its own.

### Built after the graph

The background chain after an upload ends with:

1. update the graph;
2. update the roadmap's titles.

Deleting a document, retrying a document's concepts and rebuilding the graph
by hand also update the roadmap. While the graph is waiting, updating or out
of date, the roadmap waits, so its stages are not titled twice. A build whose
material changes while the model writes is marked failed quietly and stores
nothing, as for the graph.

## The API and the Roadmap tab

- **`GET /api/environments/{id}/roadmap`** gives:
  - the stages in order, each with its title, its description and whether
    the model wrote them;
  - the documents each stage draws on;
  - each stage's concepts in order, each with what it builds on, whether it
    is in a loop, its documents and its evidence citations;
  - the loops of prerequisites;
  - the state of the titles.
- **`POST /api/environments/{id}/roadmap`** writes the titles of the current
  stages, or tries again after a failure.

The Roadmap tab shows the stages in order. Each stage shows:

- its number, title and description;
- whether the local model wrote them;
- the documents it draws on;
- its concepts, each linking to the Knowledge map explorer, with its
  definition, what it builds on, and chips that open its passages.

Loops are named above the stages, to be learned together. The tab follows the
background work without a reload, like the other tabs, and works on a phone.

## Testing

- **The rules (pure), each with its own test:**
  - a prerequisite comes first even when taught later;
  - otherwise more evidence comes first, then reading order;
  - a whole comes before its parts unless a prerequisite says otherwise;
  - a link across documents never merges their stages;
  - stages follow prerequisites across documents, then where they start;
  - an isolated concept joins the stage before it, else after;
  - loops are reported and kept together, across documents too, without
    pulling in unrelated neighbours;
  - stages whose prerequisites loop are merged;
  - big stages are split evenly;
  - the same material always gives the same roadmap;
  - unknown and self links are ignored;
  - stage keys and plain titles.
- **The service, with scripted answers.**
  - The rules order the roadmap, and a model answering last stage first
    cannot reorder it.
  - A new lecture asks only for its new stages, and asking again asks
    nothing.
  - A failure shows plain titles, and asking again retries.
  - Unusable titles stay plain.
  - The roadmap waits for the graph.
  - Material changing mid-write stores nothing.
  - Loops are shown, and no concepts means no roadmap.
- **The API.**
  - The roadmap builds itself after uploads.
  - Its citations are identical to source previews.
  - Asking again asks nothing.
  - Deleting a document keeps the titles of the stages left.
  - A failure is retried on request.
  - An empty environment has no roadmap, and unknown ids are 404s.
- **Deliberate breaks.** Eighteen deliberate breaks are each caught. Four
  survived at first and showed gaps in the tests:
  - keeping a loop together across documents;
  - an isolated concept between two stages;
  - stages whose concepts interleave;
  - a loop with uneven evidence.
- **The real model.** The real-model test checks that:
  - every concept is on the roadmap exactly once;
  - prerequisites come first unless they loop;
  - every stage got a plain-text title.

  On the trial graph, all nine titles were usable, in 18 to 23 seconds.
- **In the browser, with the real model.**
  - The trial environment's roadmap was titled on "Update now" in 23
    seconds. Its titles included "Threads and context switching", "Detecting
    and avoiding deadlocks" and "Virtual memory translation basics".
  - A chip opened its passage, and a concept opened in the Knowledge map.
  - A fourth lecture, uploaded with the tab switched at once, was followed
    from waiting through updating to up to date without a reload: 10 stages.
    The six stages it did not change kept their titles.
  - Deleting that lecture brought back the nine stages and their titles at
    once, with no model call.
  - The page fit a phone's width in the dark theme, with no console errors.

## Consequences

- The roadmap is only as good as the graph. With few prerequisites, most of
  the order is the material's own: a lecturer's order, kept unless the graph
  says otherwise. That is the safer default.
- A concept merged across lectures stays in the stage of the lecture that
  taught it first, even when a later lecture says more about it.
- A doubtful relationship in the graph shows up in the roadmap. "Belady's
  Anomaly", marked part of "Page Replacement Policy", comes straight after
  it, before the policies it is a property of.
- A small lecture spanning several topics can yield a mixed stage: the
  fourth lecture's own concepts formed "Memory and CPU coordination".
- Remembered titles are per model and prompt. A new model or prompt version
  titles every stage again.
