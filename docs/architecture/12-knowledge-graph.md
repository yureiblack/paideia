# 12. Knowledge graph

Date: 2026-11-10
Status: accepted

## Context

Phase 11 gave each environment an inventory of concepts, each with the
passages that explain it. Phase 12 connects them. There are three kinds of
relationship:

- **`PREREQUISITE_OF`:** one concept must be understood before the other.
- **`PART_OF`:** one concept is a part, step or kind of the other.
- **`RELATED_TO`:** the two are closely related, without either of the
  above.

Every relationship needs evidence from the source documents. The roadmap's
rule is the one from Phase 11: the model proposes, and the backend validates
before anything is stored. The concepts must exist, there must be no
duplicates and no self-edges, and confidence must be in range. Traversal
must answer prerequisites, dependents and related concepts. The graph lives
in Postgres adjacency tables, not a graph database.

## What the prototypes showed

Before any code, three four-passage lectures (scheduling, synchronization,
memory) were run through the real model (ministral-3:8b) four ways.

1. **The model proposes freely.** Asked for "up to 20 relationships", it
   wrote mostly well-formed nonsense, with high confidence: "Thread part of
   Aging", "Race condition part of Banker's algorithm". One lecture had eight
   two-way contradictions. There were self-links and duplicates, one
   prerequisite in forty, and every confidence between 0.7 and 1.0.
   Validation can refuse malformed output; it cannot fix well-formed
   nonsense.
2. **The backend proposes the pairs.** Pairs of concepts sharing an evidence
   passage, each classified by the model with "no relationship" allowed.
   Every answer was sensible, with no contradictions, three times faster.
   But nearly all were "related", and pairs never crossed lectures.
3. **Pairs across lectures.** A passage that is evidence for one concept and
   names the other, with clearer definitions. Eight prerequisites, many
   right, but about a third of the directional answers were reversed: the
   model confused the abstract labels "A" and "B".
4. **Full sentences with the real names.** The model chose among statements
   such as "Deadlock must be understood before Deadlock avoidance". Direction
   errors fell to about 3 in 20. "Priority Inversion" before "Priority
   Inheritance", and "FIFO" part of "Page Replacement Policy", were now
   right. Each lecture took 26 to 66 seconds for 13 to 27 pairs.

The prototypes also showed that a new lecture creates new pairs in older
lectures' passages, because a passage that names "thread" pairs a new
concept with Thread. The graph is environment-wide, so a rebuild must not
ask the model again about everything.

## Decisions

### The backend finds the pairs, the model only classifies them

`app/graph.py` finds candidate pairs by fixed rules, with no database and no
model. Two concepts are a pair when one passage connects them: it is evidence
for one of them, and it is evidence for the other too or names it. Names are
matched word by word on simplified text: case folded, punctuation dropped,
each word made singular with the Phase 11 rules. So "threads" in a passage
finds the concept "Thread", and "mutexes-free" does not find "Mutex". Aliases
count as names; single letters do not.

The passages that produced a pair are its evidence. The model never invents
a pair, so it can never relate two concepts no passage connects. Pairs are
ordered best-supported first, and one build considers at most 400.

### Six sentences, with the real names

The prompt, `relationship/v1`, gives the passages, numbered, and for each pair
the two names, their definitions, and six statements:

1. *A* must be understood before *B*.
2. *B* must be understood before *A*.
3. *A* is a part, step or kind of *B*.
4. *B* is a part, step or kind of *A*.
5. *A* and *B* are closely related, but none of the above.
6. The passages do not show a relationship.

The model answers, for every pair, the number of one statement and a
confidence from 0 to 1. The schema allows only the pair numbers it was given,
statements 1 to 6, and confidences between 0 and 1, and asks for exactly one
answer per pair. Pairs are asked about in batches of up to 30, grouped by the
document holding most of their passages.

The per-pair block is a named part of the same prompt file (`=== pair`), read
with `prompting.part()`. It is locked by the same SHA-256 check as every
released prompt.

### Validation, and one relationship per pair

- **Pairs and numbers:** only the pairs given, by the schema.
- **Confidence:** in range, by the schema and a check in the table. Below 0.5
  counts as no relationship.
- **Self-edges:** impossible by construction, and refused by a table check
  as well.
- **One relationship per pair of concepts:** a unique index on the unordered
  pair (`least`, `greatest` of the two ids). A contradiction ("A before B"
  and "B before A") or a second kind for the same pair cannot be stored.
  `RELATED_TO` is stored once, not both ways.
- **Unknown decisions:** refused in code.

### Decisions are remembered

Each pair's decision is stored in `relationship_decisions`, keyed by:

- the pair's two normalized names;
- its passages' content hashes, which are text fingerprints, not chunk ids,
  so a reprocess with the same text keeps the decisions;
- the model and the prompt.

The same key means the same question, so the same answer. A rebuild asks the
model only about pairs it has no decision for. Adding a lecture classifies
its new pairs only, and deleting one asks nothing.

### Three tables

Migration 8 adds three tables and widens the generated-artifact types by
hand:

- **`relationship_decisions`:** that memory, including decisions of "no
  relationship".
- **`concept_relationships`:** the edges, with source, target, type and
  confidence. Table checks cover the type, the range and self-edges, plus the
  unique index above.
- **`relationship_evidence`:** the passages behind each edge. Deleted with
  the edge or with the passage.

### The graph is derived, and rebuilt in the background

The edges are always exactly what the current pairs' decisions stand for.
Each build deletes the environment's edges and writes them again from the
decisions, in the same transaction that stores the new decisions. An edge no
longer supported by any current pair disappears.

Each build is a generated artifact (`knowledge_graph`). Its source version is
the fingerprint of the current pairs' keys, so unchanged pairs never rebuild.
Builds take the one-at-a-time model lock, and the model is called outside
any transaction (record 09).

A build waits while documents are still being read or their concepts
extracted. If the concepts change while the model is deciding, because a
document was deleted for example, the build is marked failed quietly and
stores nothing, and the change's own rebuild takes over. Going back to
earlier pairs, for instance by deleting the lecture that changed them, finds
the earlier build and rewrites its edges from the remembered decisions.

The graph counts as up to date only when the stored edges are exactly those
the current pairs' decisions stand for. The browser check found why that
matters. A lecture uploaded a second time brought back pairs already
decided, so its build was found ready at once, a moment before its edges
were written back. The page saw "Up to date" with the old edges and stopped
checking. Now that moment reads as out of date, which the page keeps
checking (below).

The background chain after an upload is now:

1. read the document;
2. queue its concepts;
3. write its summary;
4. update the environment's summary;
5. extract its concepts;
6. update the graph.

Each step follows straight after the one it is built from. In the Phase 11
order, the environment's summary came after the concepts. During the
extraction it showed "Out of date", and the page stopped checking.

### Traversal in SQL

Prerequisites and dependents are found with recursive queries over
`concept_relationships`. Each walks the arrows backwards (what a concept
builds on) or forwards (what builds on it), and returns every concept
reachable with the fewest steps it takes. Each step carries the path walked
so far and never enters a concept already on it, so a cycle ends the walk.
A depth cap of 25 is a second guard. Related concepts are the direct
`RELATED_TO` neighbours, and parts the direct `PART_OF` ones, in both
directions.

## The API and the Knowledge map tab

- **`GET /api/environments/{id}/graph`** gives every concept and
  relationship, and where the build stands: up to date, updating, waiting,
  stale, failed or none. It also gives how many pairs were considered and
  how many the model was asked about.
- **`POST /api/environments/{id}/graph`** brings the graph up to date, or
  tries again after a failure.
- **`GET /api/concepts/{id}/neighbourhood`** gives:
  - the concept's prerequisites and dependents, each with its depth;
  - what it is part of, and its parts;
  - what it is related to;
  - for every direct relationship, its confidence and evidence citations.

The Knowledge map tab starts with the graph's state and counts. Picking a
concept from the inventory opens the explorer above it:

- "Builds on", all the way back, and "Leads to";
- what it is part of, its parts, and what it is related to;
- each entry a link to explore further, with chips that open the passages
  behind each direct relationship.

The picked concept is in the address (`?concept=`), so the browser's back
button retraces the way. It is plain lists, with no graph drawing, so it
reads the same on a phone. Each concept in the inventory shows how many
relationships it has.

The model's confidence is stored and returned by the API, but not shown. In
the trial it was 0.9 or 1.0 for every answer, so a percentage would claim a
certainty the model does not have.

Two changes make every page follow the background work without a reload:

- **Out of date is watched too.** The graph and the environment's summary
  are checked every two seconds while out of date, as well as while waiting
  or updating. Out of date is how each looks in the moment between what it
  is built from changing and its rebuild starting.
- **A document change refreshes everything derived from it.** Adding,
  reading again or deleting a document asks again for the environment's
  summary, concepts and graph, not only its document list. One of them may
  have been fetched just before the change arrived. The first browser check
  caught that: the Knowledge map, opened while an upload was still on its
  way, showed "Up to date" for eight minutes while the graph was rebuilt
  behind it.

## Testing

- **Pairs and decisions (pure).**
  - Word simplification and name forms.
  - Pairs from shared evidence, and from a passage naming another concept
    across documents; unconnected concepts are not a pair.
  - Ordering and the cap.
  - A pair's key changes with its passages' text and nothing else.
  - Every decision maps to one edge; "none" and low confidence map to none.
- **The service, with scripted decisions.**
  - The model is asked about exactly the pairs the backend found, as
    statements with the real names.
  - Building again asks nothing.
  - A new lecture asks only about its new pairs.
  - Deleting a lecture removes its relationships and asks nothing.
  - Going back to earlier pairs brings back their edges.
  - Low confidence is remembered and draws no edge.
  - A failed model call fails the build, and asking again retries it.
  - The graph waits for documents on their way.
  - Concepts changing before or during a build store nothing.
  - The tables refuse a second relationship for a pair, self-edges and
    confidences out of range.
  - Traversal is transitive with the fewest steps, and a cycle ends the walk
    even without the depth cap.
- **The API.**
  - The graph builds itself after an upload.
  - Neighbourhood citations are identical to source previews.
  - Asking again asks nothing.
  - A second document adds to the graph, and deleting it takes it away.
  - A failed build is retried on request.
  - Retrying a document's concepts rebuilds the graph.
  - An empty environment has no graph, and unknown ids are 404s.
- **Deliberate breaks.** Sixteen deliberate breaks are each caught, from
  forgetting decisions and dropping the cycle guard to swapping parts and
  wholes, and calling a graph up to date before its edges are back.
- **The real model.** The real-model test checks that the uploaded lecture's
  graph is built, that every pair was decided, and that every relationship
  cites passages. With the released prompt, the three prototype lectures,
  uploaded one after another, gave:
  - 13 pairs, then 34 and 61, the model asked about 13, then 21 and 27: only
    the new pairs each time, in 30 to 60 seconds of model time per build;
  - 54 relationships: 9 prerequisites, 8 part-of and 37 related;
  - no reversed directions. "Deadlock" before "Deadlock avoidance", "Shortest
    Job First" before "Shortest Remaining Time First", "Banker's algorithm"
    part of "Deadlock avoidance", "Time Quantum" part of "Round Robin
    Scheduling". The doubtful one: "Belady's Anomaly" part of "Page
    Replacement Policy", where it is a property of one policy.
- **In the browser, with the real model.**
  - The graph's state and counts showed above the inventory, and each
    concept showed how many relationships it has.
  - "Deadlock avoidance" built on "Deadlock" and "Safe state", with
    "Banker's algorithm" as a part. Following "Deadlock" opened its own
    neighbourhood, and the back button returned.
  - A chip opened its passage in its page.
  - A fourth lecture uploaded in the browser, the tab switched at once. The
    Summary tab went from waiting through updating to up to date by itself,
    then the Knowledge map from waiting through updating to up to date with
    84 relationships, without a reload.
  - Deleting that lecture in the browser brought back the 54 without asking
    the model.
  - The page fit a phone's width in the dark theme, and there were no console
    errors.

## Consequences

- Every change to an environment's concepts costs one more model run, for
  the new pairs only: about 30 to 50 seconds for a lecture's 13 to 21 new
  pairs.
- The graph is only as good as the model's direction judgements. About one
  in seven directional answers was reversed in the prototype, none in the
  trial of the released prompt. Every relationship shows its passages, so a
  wrong one can be checked against them.
- The model's confidence does not discriminate: nearly every answer is 0.9
  or 1.0, so the 0.5 threshold rarely matters. "No relationship" is what
  keeps weak pairs out.
- Most relationships are "related": 37 of 54 in the trial. Prerequisites,
  which the roadmap (Phase 13) needs most, are a sixth of the graph.
- Pairs come only from passages that connect two concepts. Relationships the
  material never states in one passage are not found. That is the price of
  never letting the model invent a pair.
- Remembered decisions are kept per model and prompt. A new model or prompt
  version asks again about every pair.
