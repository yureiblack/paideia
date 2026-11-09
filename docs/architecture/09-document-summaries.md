# 09. Automatic document summaries

Date: 2026-11-09
Status: accepted

## Context

Record 08 added a language model and one narrow feature: a cited summary of
a document, written while the request waited and then forgotten. The
roadmap's Phase 09 makes summaries part of the material itself:

- a summary is written whenever a document becomes ready, and stored;
- it references the document and its version, and records the model and
  prompt version that wrote it;
- writing it is idempotent for a given document version;
- when a document changes, history is kept, never silently overwritten.

The roadmap suggests one generic table for everything the model will write:
`generated_artifacts`, with an id, the environment, an artifact type, a
source version, the content, metadata, the model name, the prompt version and
a creation time.

## Decisions

### One table for generated artifacts

`generated_artifacts` has the roadmap's columns plus four more:

- **document_id:** the document an artifact belongs to. Empty for Phase 10's
  environment-wide summary.
- **status:** `pending`, waiting its turn; `generating`; `ready`; or `failed`.
- **error:** why it failed.
- **updated_at:** when it last changed state.

Deleting a document or an environment deletes what was written from it, in
the database itself. `content` holds the finished summary as JSON, with every
citation stored in full, excerpt included, so a summary stays readable after
its passages have changed or gone. `metadata_json` records the number of
passages and sections, and the model's time.

The only index of its own is on `environment_id`. Lookups by document use the
unique key below, which starts with `document_id`.

### What a summary is written from: `source_version`

A summary's `source_version` is the SHA-256 of the document's file version
(record 07) followed by its chunk ids in reading order. Chunk ids are derived
from their text (record 04), so it changes exactly when the text a summary
reads changes: a reprocess with a better parser, for example. Reprocessing
an unchanged document leaves it, and the summary, as they were.

### Idempotent by construction

A unique index on (document, artifact type, source version, model, prompt
versions) means the database itself refuses to hold two summaries of the same
thing.

- **Asking again** finds the existing row and returns it. Writing it again
  would be pointless anyway: with temperature 0 and a fixed seed (record 08),
  the same text, model and prompt give the same summary word for word, as the
  browser check confirmed.
- **Two simultaneous requests** cannot both create the row. The loser of that
  race reads the winner's row.
- **A failed attempt** is tried again in its own row, so failures do not pile
  up.
- **A new model or prompt version** is a new key, so it writes a new summary.
  The earlier one stays.

The prompt versions are known before writing, because the number of sections
a document needs depends only on its text, so the key can be checked first.

### Written in the background, one at a time

When processing leaves a document ready, after an upload or a reprocess, a
second background task asks for its summary and writes it. FastAPI runs a
request's background tasks in order, so the summary starts once the document
has been read.

`write_summary` works in three steps, the pattern record 03 uses for
parsing:

1. Claim the row under a lock.
2. Ask the model, working on plain values outside any database transaction.
3. Store the result under the lock again.

A summary therefore always ends ready, or failed with its reason. If the
document's text, the prompts or the model changed while the summary waited,
it is not written and fails with "The document changed before this summary
was written"; a summary of the current text is asked for in its place.

A process-wide lock means one summary is written at a time. Ollama serves
one request at a time well on this machine. When many documents arrive
together, their summaries queue as pending instead of competing for the
model's 7.5 GB.

Documents read before this phase have no summary until one is asked for.
The Materials tab offers a "Summarize" button for them.

### Long documents

On request, record 08 capped a summary at 4 sections, about five minutes.
In the background no one waits, so a summary may take up to 20 sections.
That limit comes from the combining step: the 20 sections' notes, about 450
tokens each, must fit in the request that combines them. A longer document,
roughly beyond 300 dense pages, gets a failed summary with the reason.

### History is never overwritten

A summary whose key no longer matches the document stays in the table. That
happens when the document has new text, or there is a new model or prompt
version. `GET /api/documents/{id}/summaries` lists every summary, newest
first, with `current` marking the one for the document as it is now. The
current summary reports how many earlier ones are kept, and the Materials tab
shows that number.

### The API

- **`GET /api/documents/{id}/summary`:** the current summary with its status.
  404 if none has been asked for.
- **`POST /api/documents/{id}/summary`:** makes sure a summary exists.
  - It answers 200 if the summary is ready, and 202 if it is waiting or being
    written. It starts writing one that was missing or had failed.
  - 409 if the document has not been read yet, and 422 if it cannot be
    summarized at all, having no text or being too long.
- **`GET /api/documents/{id}/summaries`:** every summary, newest first.

This replaces record 08's POST, which wrote a summary while the request
waited.

The POST endpoint ends its own read transaction before the background task
starts. A request's session stays open until its background tasks have
finished. A read left open would sit idle on its connection for as long as
the summary takes, possibly minutes. In the tests, which share one
connection, it also undid the summary's own write. That is how it was found.

The language model dependency moved to `app/routers/deps.py`. The documents
router now asks for summaries, and the summaries router uses the documents
router's document lookup, so neither can import the other.

### Abandoned work

A summary still `generating` an hour after its last change was abandoned,
most likely by a server restart, and asking again starts it over. This is the
same rule as record 03's for documents left processing, with a longer limit,
because a long document takes many model calls.

### The Materials tab

Each ready document's summary button names its state: "Summarize" when it
has none, "Writing summary…", "Show summary" or "Summary failed".

- **While a summary waits or is written,** the page checks every two seconds.
  It also checks for a minute after a document becomes ready, while its
  summary is being asked for.
- **A failed summary** shows the reason and "Try again".
- **A ready one** shows the overview and key points with their page chips,
  as in record 08. Its footer gives the model, the date, the time taken, the
  prompt version, and how many earlier summaries are kept.

## Testing

- **The summary service, with a stand-in model.** The Phase 08 writing tests
  carry over: numbering, citations, sections, the combining step, and the
  answer schema. New tests check that:
  - asking twice writes once;
  - reprocessing unchanged text keeps the summary;
  - new text writes a new summary, and the old one stays readable after its
    passages are gone;
  - a new model writes a new summary;
  - a failure is retried in the same row;
  - abandoned work can be retried, and fresh work is left alone;
  - a document too long, or without text, fails with the reason and no model
    call;
  - a summary queued for text that has since changed is not written;
  - summaries are written one at a time, holding the lock;
  - deleting a document deletes its summaries.
- **The API.**
  - A document is summarized as soon as it is read, its citations identical
    to the source previews.
  - Asking again does not write again, and a failed summary is written again
    when asked.
  - A new model's summary becomes current while the old one stays in the
    history.
  - The 404, 409 and 422 responses each have their reason.
- **The real model.** A lecture uploaded with the real model is found
  summarized, plain, cited and grounded, with no further request. The test is
  skipped where Ollama is missing, including CI.
- **Deliberate breaks.** Twelve deliberate breaks of the new code are each
  caught. Among them: writing a new summary on every request, losing the
  stored excerpts, dropping the lock, and leaving the request's read open.
- **History order.** The suite first failed 7 runs in 10, in the two tests
  that check the history's order. Postgres's `now()`, the default for
  `created_at` here as in every table, is fixed for a whole transaction, and
  each test is one transaction, so two summaries written in one test tied.
  As Phase 02 recorded, tests that need distinct creation times set them;
  these two now date the earlier summary back a minute. After that, 10 runs
  in 10 passed. On the server each summary is created in its own request.
- **In the browser, with the real model:**
  - a lecture was summarized 19 seconds after upload with no click;
  - with Ollama stopped, the summary failed with the reason, and "Try again"
    wrote it once Ollama was back;
  - a document with no summary was summarized on request;
  - the page fit a phone's width.

## Consequences

- Every new document costs one model run soon after it is read: about 20
  seconds for a short lecture, longer for long ones, one at a time.
- If Ollama is not running when a document arrives, its summary fails with
  the reason and "Try again" in the interface. Nothing retries it by itself;
  Phase 18 brings a proper job queue.
- Changing the model or a prompt does not rewrite existing summaries by
  itself. A document gets a summary by the new model when one is next asked
  for, and keeps its earlier ones.
- `generated_artifacts` is ready for Phase 10's environment summary, which
  will use a null `document_id` and its own artifact type.
