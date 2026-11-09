# 10. The environment's summary, kept up to date

Date: 2026-11-09
Status: accepted

## Context

Phase 10 is the first proactive behaviour. Each environment maintains a
master summary of all its current material, without being asked. When a
document is added or replaced, the summary has to:

- work out what changed;
- decide whether the summary is now stale;
- rebuild it from the current material;
- record which document versions contributed.

When nothing changed, nothing should be rebuilt. The page shows the summary,
when it was last updated, how many documents it is based on, and whether it
is ready or stale. The roadmap names the idea behind it: derived state. The
summary is never edited; it follows from the material.

Record 09 left the pieces in place: document summaries written automatically
and stored with their citations in full, the `generated_artifacts` table with
its key on (document, type, source version, model, prompt), and a process-wide
rule that the model writes one thing at a time.

## Decisions

### Built from the documents' summaries

The master summary reads each included document's current summary: its
overview and cited key points, about 500 tokens. Rereading every passage of
every document would mean hundreds of thousands of tokens for a semester's
lectures, and minutes of model time on every change.

Citations carry through. Every passage the document summaries cite is
numbered once across the environment, even when several key points cite it.
The answer schema allows only those numbers (record 08), and each is turned
back into the citation the document summary stored. A key point of the
master summary therefore opens the exact passage it rests on, in whichever
document it is.

### Stored like document summaries, with its own key

It is a row in `generated_artifacts` with type `environment_summary` and no
document. That needed migration 6. The table's unique key would not cover
such rows, because a unique constraint treats NULLs as distinct. So rows
without a document get their own key: a partial unique index over
(environment, type, source version, model, prompt). Alembic does not compare
check constraints, so widening the allowed types was written by hand. Undoing
the migration deletes environment summaries first, since the narrower
constraint would reject them.

Its `source_version` is the SHA-256 of the included documents' ids, each with
the id of the exact document summary used. It changes when a document is
added, deleted or left out, and when a document gets a new summary. The
summary also records what it was built from, as it was then: each document's
filename, file version and summary. "Based on 2 documents" and the Sources
list come from that record, which stays accurate in history after a document
is deleted.

### Derived state, refreshed by itself

The summary is checked after every document summary finishes, whether it was
written automatically or by Try again, and after every deletion. Each check
works out what the summary would be built from now. If a summary of exactly
that already exists, nothing is written. That covers reprocessing an
unchanged document, and also deleting the document added last: the material
is then exactly what an earlier summary was built from, so that summary
becomes current again with no model call.

It waits while any document in the environment is still being read or
summarized. Documents uploaded together therefore produce one rebuild once
they are all done, not one per document. It shares the one-at-a-time lock
with document summaries, and uses record 09's rules:

- claimed under a row lock;
- the model works outside any transaction;
- not written if the material changed while it waited;
- failures retried in the same row;
- an hour's abandonment allowed for.

### What is included

Only documents whose current summary is ready are included. Every other
document is listed with the reason:

- "It could not be read: …";
- "Its summary failed: …";
- "It has not been summarized yet." (documents read before Phase 09).

An environment with nothing summarized has no master summary.

### Large environments

When all the documents' notes fit one request, about 10,000 estimated tokens
or roughly twenty documents, they are summarized together. Otherwise groups
of documents that fit are summarized first, and the groups' notes are then
combined. Two levels cover hundreds of documents.

One new prompt, `environment_summary/v1`, does both levels. It is locked by
the prompt test like the others.

A trial with the real model found a flaw in its first wording. Asked to cover
the material "connecting its parts where they relate", the model added a
general conclusion of its own. One point said the three topics "interact to
balance task efficiency, memory usage, and data integrity", which the
reranker scored 0.03 against the passages it cited. The released wording asks
for links only where the notes themselves make them, and no conclusions of
the model's own. On one lecture and on three, every key point was then judged
supported by its cited passages, the weakest at 0.95.

### The API and the Summary tab

- `GET /api/environments/{id}/summary` reports a state:
  - `up_to_date`;
  - `updating`, when a summary of the current material is being written;
  - `waiting`, with how many documents are still on their way;
  - `stale`;
  - `failed`, with the reason;
  - `none`.

  It also returns the newest ready summary, the documents not included and
  the number of earlier summaries kept. While a new summary is on its way,
  the previous one stays visible, marked as from earlier material.
- `POST` brings the summary up to date, or tries again after a failure.
- `GET /api/environments/{id}/summaries` lists the history.

The environment's Summary tab, until now a placeholder, shows:

- the state, the last update and "Based on N documents";
- the overview;
- key points with chips naming the file and page of each cited passage,
  opening it in place;
- the sources with their file versions;
- the documents not included.

It checks every two seconds while the summary waits or is written. In the
browser, adding a second lecture took the tab from "Waiting for documents"
through "Updating…" to "Up to date" in 48 seconds.

## Testing

- **The service, with a stand-in model.**
  - The summary is built from the document summaries, numbered across
    documents, its citations identical to the stored ones.
  - A passage cited by two key points gets one number.
  - Reprocessing an unchanged document rebuilds nothing.
  - A new document rebuilds it and keeps the old one.
  - It waits for a document being read, then for one being summarized.
  - Documents that failed or were never summarized are left out with their
    reasons.
  - A deletion rebuilds it while the old one still names the deleted
    document.
  - With nothing summarized there is no summary.
  - Large environments are summarized in groups.
  - Nothing is written for material that changed while it waited.
  - A failure is retried in the same row, under the one-at-a-time lock.
  - The source version names the exact summaries used.
- **The API.**
  - Uploads keep the summary up to date.
  - Asking again writes nothing.
  - Deleting the last document added returns to the earlier summary with no
    model call, while deleting another rebuilds it.
  - A document summary written on request updates the environment.
  - The waiting and failed states are reported, and Try again recovers.
  - An empty environment has nothing to summarize, and unknown environments
    are 404s.
- **The real-model test** now also checks the environment summary built after
  the upload: plain text, every point cited and supported.
- **Deliberate breaks.** Eleven deliberate breaks are each caught by a test.
  One, numbering a passage again for every key point that cites it, survived
  until the test for shared passages was added.
- **Distinct times in tests.** Document order and summary history depend on
  creation times, which Postgres freezes for a test's whole transaction. The
  tests give documents distinct times, as record 02 says such tests must. The
  page shows the current summary whenever it is ready rather than whichever
  is newest, which is right regardless of timing.

## Consequences

- Each change to an environment's material costs one extra model run of
  about 20 to 30 seconds, after the document's own summary.
- Documents added together produce one rebuild, not one each, but only if
  their summaries are still being written when the others finish. Adding
  lectures minutes apart rebuilds after each.
- A small model can still pick the wrong passage within the right document
  for a cited point. In a trial, a point on thrashing cited the
  page-replacement page beside it. Every citation opens in place for a reader
  to check.
- The `stale` state appears only for material summarized before this phase;
  every later change triggers a rebuild by itself.
