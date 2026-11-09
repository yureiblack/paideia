# 11. Concept extraction

Date: 2026-11-09
Status: accepted

## Context

The knowledge graph (Phase 12) and the learning roadmap (Phase 13) both need
a structured inventory of what the material teaches. Phase 11 turns each
document version into that inventory. The model returns, for every concept,
a name, a short definition, aliases and the source chunks; names are
normalized deterministically after extraction; concepts, document links and
evidence are stored. No graph edges yet.

The roadmap's rule for this phase: the model proposes concepts, and the
backend validates and persists them. Raw model output must never directly
define database relationships, and malformed output must not be able to
corrupt the database.

## What the prototype showed

Before any code, three five-passage lectures were run through the real
model (ministral-3:8b), with the answer's shape enforced:

- **Good concepts.** Each lecture gave twelve, the maximum allowed: relevant
  and well defined, each citing a valid passage, in 35 to 43 seconds per
  lecture. Examples: Belady's Anomaly, Working-Set Model, Banker's Algorithm,
  Priority Inheritance.
- **Unreliable aliases.**
  - Some were empty strings.
  - Some were descriptions rather than names: "disk busy all the time",
    "dividing physical memory into frames", "evicting a victim page".
  - Some were wrong: "valid bit" given as another name for demand paging.
- **Untidy names.** Names carried abbreviations in brackets ("Shortest Job
  First (SJF)", "Mutex (Mutual Exclusion)") and curly apostrophes, and the
  same concept was named in the plural in one place and the singular in
  another.

Those findings decided most of what follows.

## Decisions

### Extraction works like summaries

A document's passages are numbered and given to the model section by
section, with the same sections as summaries. For each section the model
proposes at most 12 concepts. Each has:

- a name, of at most 80 characters;
- a one-sentence definition, of at most 300;
- up to 5 aliases;
- the numbers of 1 to 4 passages that explain it.

The schema bounds every list and string, and allows only the passage numbers
the section was given (record 08). The prompt, `concept_extraction/v1`, asks
for aliases that are "other names the passages use for the same concept,
such as an abbreviation, never a description".

Each extraction is stored as a generated artifact of type
`concept_extraction`, keyed by document text, model and prompt as summaries
are (record 09). The same text never extracts twice, new text extracts anew,
and earlier extractions are kept. Extraction runs in the background after the
document's summary and shares the one-at-a-time model lock. A document of
five passages takes about 40 seconds.

The extraction is queued the moment a document has been read, and written
after the summary. The first browser check found why that matters. Without
the queue step, a document spent the twenty seconds of its summary with no
extraction at all. The page read that as nothing coming and stopped checking,
so the concepts never appeared until a reload. Queued, the extraction shows
as waiting from the start.

### Names are normalized by fixed rules

`app/concepts.py` turns a name into its identity in the same way every time:

- Unicode normalization (NFKC), which also folds ligatures such as "ﬁ";
- case folded;
- typographic quotes and dashes made plain, so "Belady’s" and "Belady's"
  match;
- bracketed parts removed and kept as aliases: "Shortest Job First (SJF)" is
  "shortest job first", with the alias "SJF";
- hyphens, underscores and slashes read as spaces;
- other punctuation dropped, apostrophes kept for "Banker's algorithm";
- leading articles dropped;
- the last word made singular by conservative rules: -sses to -ss, -ies to
  -y, and a final -s dropped except after s, u or i and in words of three
  letters or fewer. So "processes" becomes "process", "policies" "policy" and
  "threads" "thread", while "address", "status", "analysis" and "bus" stay as
  they are. The rules would rather leave a word alone than mangle it.

The tests hold a table of these cases, drawn from the prototype's names.

### Identity is the normalized name; aliases never merge

Within an environment, a concept is its normalized name, so "Threads" in one
lecture and "Thread" in another are one concept. Aliases are stored and
shown, but never used to merge concepts: the prototype showed them too often
wrong to decide identity. "Mutex" listing "lock" as an alias stays a
different concept from "Lock".

### Validation before anything is stored

Each proposal is checked before it is kept. A proposal is dropped when:

- its name is nothing once brackets are removed;
- it has no letters;
- it is too long;
- its definition is empty;
- none of its passages is one the model was given.

Proposals with the same normalized name are merged: the first name and
definition are kept, and passages and aliases combined.

Aliases are cleaned. An alias is dropped when it is:

- empty;
- the concept's own name;
- a repeat of another alias;
- longer than four words;
- or contains a joining word such as "of", "a", "the", "into" or "for",
  which marks a description.

All four descriptions from the prototype are dropped by that rule. The price
is the odd real alias such as "principle of locality", which is harmless
because aliases are only shown.

A reply that breaks the schema is refused whole. The real provider retries
it and then fails; the extraction is marked failed with the reason, and the
concept tables are untouched. Every extraction records how many concepts
were proposed, how many kept and how many dropped.

### Three tables, written only by the backend

Migration 7 adds three tables, and widens the generated-artifact types by
hand, as migration 6 did.

- **`concepts`:** one row per normalized name per environment, with the name,
  definition and aliases shown.
- **`document_concepts`:** how each document presents a concept, in its own
  name, definition and aliases.
- **`concept_evidence`:** the passages that explain a concept. Deleted with
  its chunk, so evidence always points at text that exists. It has an index
  on `chunk_id` of its own, because every reprocess deletes chunks and each
  deletion cascades here.

### Derived from the extractions

When a document's extraction is ready, the same transaction that stores it
replaces that document's links:

1. Its old links and evidence go.
2. Concepts are found or created by normalized name, so their ids stay stable
   for the knowledge graph.
3. Its new links and evidence are written.
4. Every concept in the environment is brought in line. A concept no document
   mentions any more is deleted, and the rest show the name, definition and
   aliases of the document with the most evidence for them, then the
   earliest.

Deleting a document does the same clean-up.

## The API and the Knowledge map tab

- **`GET /api/environments/{id}/concepts`** returns every concept, by name,
  with its documents and evidence citations, the same objects search
  returns. It also gives each document's extraction state: the document's own
  status, the extraction's status, and the proposed and kept counts.
- **`GET` and `POST /api/documents/{id}/concepts`** give one document's
  extraction and concepts, and ask for them again.

The Knowledge map tab lists the concepts, with a filter by name or alias.
Each shows its definition, other names, the documents it appears in, and
chips that open its passages. Documents still being read, waiting, or failed
are listed above, with Try again for failures. The map itself comes next.

## Testing

- **Name rules and validation.** A table of name cases drawn from the
  prototype; the singular rules; bracketed abbreviations; the prototype's
  descriptions refused and real alternative names kept; untrustworthy
  proposals dropped and counted; same-name proposals merged; aliases never
  merging concepts.
- **The service, with scripted model answers.**
  - Proposals become concepts with their passages as evidence.
  - Untrustworthy proposals never reach the tables, and a reply breaking the
    schema fails with nothing written.
  - Concepts merge across documents and keep their ids.
  - The best-evidenced wording wins.
  - Extracting twice writes once, and new text replaces a document's concepts
    while the old extraction is kept.
  - Deleting a document keeps shared concepts and removes its own.
  - Long documents are read in sections and merged.
  - A document without text fails with its reason.
  - Extraction holds the lock, and the schema bounds every list and string.
- **The API.** Concepts are extracted once a document is read, with citations
  identical to source previews. Asking again extracts nothing. A failure is
  retried on request. Deletion removes the concepts only that document
  mentioned. A document still being read can't be asked for concepts, and
  unknown ids are 404s.
- **Queuing.** A queued extraction shows as waiting with no model call, and is
  extracted afterwards.
- **In the browser, with the real model:**
  - after an upload, the Knowledge map tab went from "Being read" through
    "Waiting to be extracted" and "Extracting concepts…" to 12 concepts in 61
    seconds;
  - the filter narrowed them, and a chip opened its passage in its page;
  - with Ollama stopped, a second lecture's extraction failed with the reason,
    and Try again, once Ollama was back, brought the total to 23 concepts from
    2 documents;
  - the page fit a phone's width.
- **The real model.** The real-model test checks that an uploaded lecture's
  concepts are extracted, each with a definition and evidence, and that no
  two share a normalized name. With the released prompt, two overlapping
  lectures merged "Paging" and "Page Table" across both. The only aliases
  were "FIFO", "LRU" and "TLB".
- **Deliberate breaks.** Thirteen deliberate breaks are each caught, from not
  folding plurals to storing unvalidated proposals.

## Consequences

- Every document read now costs one more model run, about 40 seconds for a
  short lecture, after its summary.
- The model tends to propose as many concepts as allowed, so a section yields
  up to 12. Phase 12's graph will show which of them matter.
- The singular rules are deliberately simple: they would leave "indexes" as
  "indexe". Names the rules treat differently from a reader will show up as
  separate concepts, not merged ones; that is the safer way to be wrong.
