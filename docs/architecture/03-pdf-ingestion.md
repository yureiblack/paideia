# 03. PDF ingestion

Date: 2026-11-02
Status: accepted

## Context

Phase 03 turns uploaded PDFs into page-aware source records. Everything later
builds on this text: chunking, search, summaries and citations. Page numbers
must survive, so a later summary can point to the page it came from. Parsing has
to be testable on its own, without embeddings or a language model.

Before any code was written, the PDF library was prototyped against every kind
of input the phase had to handle. Several decisions below come from what that
prototype found.

## Decisions

### Original files on disk, extracted text in Postgres

The PDF itself is stored at `data/uploads/<environment id>/<document id>.pdf`.
The database holds its metadata, a SHA-256 fingerprint, its status and the text
of each page. Keeping binaries out of Postgres keeps backups and queries small.

Files are named by document id, never by the name they were uploaded with, so a
filename can never become a path. A new upload is first written to `data/tmp/`
and then moved into place with a rename on the same disk, which is atomic: a
document's file is either completely there or absent.

### Uploads travel as the raw request body

A conventional form upload was rejected because FastAPI writes a form-uploaded
file to disk in full before any application code runs. A 50 MB limit could only
be checked after an oversized file had already been received.

Instead the request body is the PDF itself, with the filename in the query
string, and the backend reads it in chunks. Browsers declare a file's size
before sending it, so an oversized file is refused before any of it is sent; a
client that hides the size is stopped as soon as the limit is passed. Both were
verified against a running server with an 80 MB upload. A file counts as a PDF
when its `%PDF-` signature appears in the first kilobyte, as the PDF standard
allows, and is checked again by the parser.

### Parsing runs in a background task

The upload answers at once with status `uploaded`. A background task then claims
the document, moves it to `processing`, and finishes at `ready` with its pages or
`failed` with a reason. The frontend polls until every document has settled.

The task opens its own database session from an injectable factory, because the
request's session is closed by the time the task runs. Tests inject sessions on
the test connection, so background work is rolled back with everything else.

A document stuck in `processing` after a server restart can be reprocessed once
it has been there for ten minutes. If storing the parsed text fails, the
document is marked `failed` in a new transaction rather than left in
`processing`. A dedicated job queue arrives in a later phase; this is the
simplest design that keeps every status truthful until then.

### Duplicates are caught within one environment

The same file twice in one environment is refused with 409, naming the existing
document. The same file in two environments is allowed, since one textbook can
serve two subjects. A unique constraint on `(environment_id, sha256)` backs the
check in code, so two identical uploads arriving together cannot both succeed.

### What counts as a failure

A document fails when the file cannot be opened, is password-protected, or has
no pages. Everything else is `ready`:

- A scanned PDF with no text layer is ready with zero pages of text, and the
  interface says it may be a scan. OCR is out of scope.
- A damaged file that the library repairs while opening is ready and flagged as
  repaired. In the prototype, a file cut to 90% of its length was repaired with
  every page recovered, so treating it as failed would have discarded good
  content. The flag tells the reader that something may be missing.

### The parser sits behind an interface

`app/parsing.py` defines a `Parser` that turns a file into page-numbered text,
and nothing else in the backend imports the PDF library. The implementation uses
PyMuPDF 1.28.2. The prototype shaped it:

- PyMuPDF opened a PNG as a one-page document, so the parser requires `is_pdf`
  as well as the signature check at upload.
- NUL characters survive extraction and Postgres text columns refuse them, so
  they are removed. Without this, a valid PDF would fail with a database error.
- A zero-page file opens without error, so it is rejected explicitly.
- The library's sorted extraction mode interleaves the two columns of a
  two-column page line by line, so text is taken in the PDF's own order.
- PyMuPDF's documentation says it does not support use from multiple threads.
  Background tasks run on threads, so every call holds one lock. A 300-page
  file parses in under a tenth of a second, so the lock costs little.

Version 1.28.2 rather than 2.0: version 2.0 bundles a machine-learning layout
engine with eight extra dependencies, about 245 MB against 58 MB, and behaved
identically on every prototype check. It is worth revisiting when chunking by
section and heading needs layout information.

PyMuPDF is licensed under the AGPL-3.0. That requires a project which
distributes it or offers it as a network service to publish its own source under
compatible terms. This repository is public, so the condition is met. If that
ever changed, the parser interface allows a swap to a permissively licensed
library such as pypdfium2.

### Every Python dependency is pinned

The project previously pinned only its direct dependencies. A fresh install
pulled in over forty packages, a dozen of which had already drifted from the
development machine, so CI was not testing what ran locally. Direct
dependencies are now listed in `api/requirements.in`, and pip-tools compiles
`api/requirements.txt` with every package pinned.

pip-tools resolves only for the platform it runs on. SQLAlchemy needs `greenlet`
on Linux but not on Apple Silicon, so it is listed explicitly to be pinned for
CI too. After installation, the only unpinned package on either platform is pip
itself.

## Consequences

- Every table that belongs to an environment cascades on delete, and deleting an
  environment also removes its upload folder after the database commit.
- The `data/` folder must be backed up separately from the database.
- Adding a parser means one new class in `app/parsing.py`.
- Changing a dependency means editing `requirements.in` and recompiling, never
  editing `requirements.txt` by hand.
