# 21. Reliability, security and data integrity

Date: 2026-11-15
Status: accepted

## Context

The roadmap asks for an audit of the application for eleven risks, and for
the additions that close what the audit finds:

- **Risks:** malformed uploads, path traversal, oversized files, invalid ids,
  duplicate jobs, partial failures, database transaction boundaries, orphaned
  files, stale generated artifacts, model timeouts and malformed model output.
- **Additions:** upload limits, safe filenames, validation, transaction
  handling, retry policies, structured logs and correlation ids.

It rules out cloud infrastructure. Much of this had been built phase by
phase, so the audit below states for each risk what protected against it
before this phase, what gap was found, and what closes it, with the tests
that prove it.

## The audit

| Risk | Protection before this phase | Gap found | Added now | Proven by |
|---|---|---|---|---|
| Malformed uploads | PDF signature checked in the first kilobyte; the parser refuses empty, damaged, encrypted and zero-page files with a reason (record 03) | none | none | `test_storage`, `test_parser`, `test_documents_api` |
| Path traversal | Files on disk named by document id; the upload's name cut to its last path part | Displayed names could carry control characters, invisible bidirectional overrides, line breaks and any length | Safe display names | `test_filenames` |
| Oversized files | `MAX_UPLOAD_MB` enforced while the upload streams, 413 before or during | A small PDF with thousands of pages would occupy the worker for hours | `MAX_PAGES` | `test_storage`, `test_documents_api`, `test_parser` |
| Invalid ids | Non-UUID ids refused with 422, unknown ones with 404 | An error could not be matched to the server's log | A request id in every error body and response | `test_environments_api`, `test_logs` |
| Duplicate jobs | Model rebuilds deduplicated by their artifact; the same file refused twice | Repeated practice preparation could queue twice; reading a document again while it was queued started a second chain | A job key refused twice by the database; reading again refused while queued | `test_jobs`, `test_jobs_api` |
| Partial failures | Each step of a material update records its state; crashed jobs retried (record 18) | A crash mid-write left an artifact "generating", and the retry skipped it for up to an hour | Unfinished artifacts settled when a job stops | `test_jobs` |
| Transaction boundaries | Upload and deletions order the database and the files safely | A new version replaced the file before committing; a job whose outcome could not be recorded stayed alive forever | File set aside until commit; files checked before reading; heartbeats only for jobs being run | `test_transactions` |
| Orphaned files | none | Nothing removed what a crash left on disk | A sweep in the worker | `test_sweep` |
| Stale generated artifacts | A one-hour rule frees "generating" artifacts; stopped workers' jobs recovered | As for partial failures | As for partial failures | `test_jobs`, earlier stale-rule tests |
| Model timeouts | A timeout per call; connection failures and timeouts retried after a pause (record 08) | none | none | `test_llm` |
| Malformed model output | Structured output validated, retried once, then reported (record 08); practice items checked (record 14) | none | none | `test_llm`, `test_practice` |

## Decisions

### Safe display names

The name a client sends is only ever displayed (`app/filenames.py`). The
cleaning:

- keeps the last part of a path, whichever slash it uses;
- normalises Unicode (NFC);
- removes control and formatting characters, among them the right-to-left
  override, which can disguise "fdp.exe" as "exe.pdf";
- turns whitespace and line separators into single spaces;
- cuts the name to 200 characters, keeping its extension.

A name with nothing displayable left, or only dots, is refused with 422.

### A page limit

`MAX_PAGES`, 1,000 by default, is checked as soon as a PDF is opened, before
any text is extracted, so a long PDF fails at once with a clear reason.

### Duplicate jobs refused by the database

Each job stores a key: a hash of its kind and its steps with their arguments,
ignoring which steps are done (migration 13). A partial unique index allows
one queued or running job per environment and key. Starting the same work
again returns the job already queued. When two requests arrive together,
both miss the check: the second insert is refused by the index inside a
savepoint, and the job that won is returned.

Reading a document again, or uploading a new version of it, is refused while
a job reading it is queued or running. That is found with a JSON containment
query on the jobs' steps. The job key cannot see this case as the same work,
since each request starts its own material update. A document that is merely
"uploaded" can still be read again, in case its job was lost.

### Settling what a stopped job leaves unfinished

When a model job stops without finishing, its artifacts are settled at once,
not left to the one-hour rule. A job stops this way when it fails, is
cancelled, or is put back for a retry after a crash or a stopped worker.

- **An artifact still "generating" is this job's.** Only a running model job
  writes, one at a time.
  - If a step of the job will write it again on the retry, it goes back to
    "pending".
  - Otherwise it fails with the job's reason, and a retried chain step, or a
    person on the page, asks for it again.
- **A "pending" artifact no step reached** fails when the job ends for good,
  unless another active job will still write it.

A queued job that is cancelled touches no "generating" artifact: those belong
to the job that is running. Reading jobs write no artifacts.

### An orphan sweep in the worker

At start and every hour, the worker removes what no document accounts for:

- parts of uploads more than a day old;
- stored files with no row, more than an hour old;
- empty folders of environments with no documents.

The grace periods spare an upload in progress, whose file is in place a
moment before its row is committed. Everything removed is logged with its
path.

### Transactions where the database and the disk meet

- **A new version** sets the old file aside rather than overwriting it, and
  puts it back if the commit fails.
- **Before reading a document,** the app checks that the file's SHA-256 is
  the one its row records, and fails with a clear reason if not. That covers
  a crash between replacing the file and committing, which no ordering can
  rule out.
- **Uploads and deletions** were already ordered safely: an upload's file is
  removed if its commit fails, and deletions remove files only after the
  commit. Forced failures now prove all of this.
- **Heartbeats** go only to the jobs a worker is running at that moment. A job
  whose outcome could not be recorded stops being kept alive and is run again
  when stale.

### Retry policies

They are gathered here; this phase changed none of them:

- **Jobs:** after 30 seconds, then 2 minutes, for 3 attempts (record 18).
- **Model calls:** connection failures and timeouts are retried after a
  pause; an answer that does not validate, once (record 08).
- **The database pool** tests each connection before using it.
- **The page** retries a failed query twice, never a 4xx answer.

### Structured logs and request ids

- **Log format:** the API and the worker write one JSON object per line,
  using Python's standard logging (`app/logs.py`). `LOG_FORMAT=text` gives
  readable lines for working locally.
- **Ids on every line:** each line carries the ids of what is being worked
  on (`app/context.py`): the request, and in the worker the job and the
  material update.
- **Request ids:** every request gets an id (`app/correlation.py`). A
  well-formed `X-Request-ID` from the caller is kept; otherwise a new one is
  made. It comes back in a header and in every error body. Each request is
  logged in one line with its method, path, status and duration, and the
  health checks at debug level.
- **Unexpected errors** become a 500 with a short message and the id; the
  traceback goes only to the log.
- **Jobs** record the request that queued them, and log their start, each
  step's duration and their end. One upload can be followed from its request
  through every step of its jobs.
- **The page** shows the first eight characters of the id as a "Reference"
  under its error messages.

### Not added

- **Authentication.** Paideia is a single-user application run on the
  learner's own machine; CORS limits which pages may call the API.
- **Rate limiting.** With one user there is nobody to limit.
- **Cloud infrastructure,** which the roadmap rules out.

## Testing

- **50 new tests:**
  - filenames (19);
  - the sweep (3);
  - logs and request ids (10);
  - forced failures between the steps of uploads, new versions, deletions
    and the end of a job (7);
  - duplicate jobs and the race (3);
  - settling unfinished artifacts (6);
  - reading a queued document again (1);
  - the page limit (1).
- **Deliberate breaks:** 22 of 23 were caught. Two were first missed by weak
  tests, now strengthened: one heartbeat test ran no other job, and one
  upload part was exactly an hour old. The remaining one removes the
  duplicate check from the code, and the database's unique index still
  refuses the duplicate, which is the reason it exists.
- **Against the real API, worker and page, in a throwaway environment:**
  - the worker's start-up sweep removed exactly two planted leftovers and
    left the real documents' files alone;
  - a hostile name was stored as "Week 6 signals.pdf";
  - reading the document again at once was refused;
  - a running job cancelled mid-chain left nothing "generating";
  - the upload's request id appeared on the API's line and on every line of
    both its jobs;
  - the page's Reference matched a line in the API's log.
- **A mistake in the tests, found and fixed.** One test helper undid every
  patch in its test, including the one that keeps tests out of the real data
  folder. Nothing there changed, but the helper now restores only what it
  patched.

## Consequences

- Logs are JSON by default. Set `LOG_FORMAT=text` in `.env` for readable
  output when working locally.
- Settling unfinished artifacts assumes one worker, as record 18 already
  does for the model's one-at-a-time lock.
- The sweep deletes files. It never touches a file whose document exists,
  nor anything changed in the last hour, and it logs every path it removes.
- An error's Reference finds the request in the API's log; finding the jobs
  it queued takes searching for the same id in the worker's log.
