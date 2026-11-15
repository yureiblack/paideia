# 22. Automated testing and CI

Date: 2026-11-15
Status: accepted

## Context

The roadmap asks for:

- **Backend:** unit, API, database integration, ingestion fixture, retrieval
  and scheduler tests.
- **Frontend:** component tests where they are worth having, and Playwright
  end-to-end tests of twelve scenarios.
- **CI:** formatting and lint, type checking, backend tests, frontend tests
  and Playwright smoke tests.
- **Coverage:** reported, without optimizing for a percentage.

Before this phase, the backend had 604 tests, and CI ran lint, formatting,
the migrations and the check that models match them, the backend tests, and
the frontend's lint, type check and build. There was no type checker for the
backend, no frontend test of any kind, no end-to-end test and no coverage
measurement.

## The tests, by kind

The backend's tests stay where they are, one file per module or router. This
is where each kind the roadmap names lives, all under `api/tests/` unless
said otherwise:

| Kind | What it covers | Files |
|---|---|---|
| Unit | The fixed rules, as pure functions with no database: chunking, concept names, candidate pairs, the roadmap's order, practice checks, the review schedule, the study plan, display names, prompts, log lines, the benchmark's metrics | `test_chunking`, `test_concept_names`, `test_graph_pairs`, `test_roadmap_rules`, `test_practice_rules`, `test_learner_rules`, `test_planner_rules`, `test_filenames`, `test_prompting`, `test_logs`, `test_settings`, `test_evaluation`, `test_evaluation_report` |
| API | Every endpoint through FastAPI's test client, against the test database: status codes, bodies, errors | `test_*_api`, `test_health`, `test_cors` |
| Database integration | The migrations from an empty database, services on real Postgres, and failures forced between the database and the files | `test_migrations`, `test_transactions`, `test_document_service`, `test_environment_service`, `test_chunk_storage`, `test_summaries`, `test_environment_summaries`, `test_concepts`, `test_graph`, `test_roadmap`, `test_practice`, `test_practice_history`, `test_update_report`, `test_sources` |
| Ingestion fixtures | PDFs built in code (`tests/pdfs.py`, `tests/parsed.py`): headings, columns, scans, encryption, damage, page limits | `test_parser`, `test_storage`, `test_document_service`, `test_sweep` |
| Retrieval | Keyword, semantic and hybrid search on fixtures, some with the real models, and a labelled evaluation | `test_hybrid_search`, `test_semantic_search`, `test_retrieval_quality`, `test_embedding`, `test_search_api`, `retrieval_eval.py` |
| Scheduler | The review schedule and the study plan; the job queue and the worker that runs it | `test_learner_rules`, `test_practice`, `test_planner_rules`, `test_plan_api`; `test_jobs`, `test_jobs_api`, `test_worker`, `test_transactions` |
| The real language model | One document summarized by the local model | `test_summary_with_real_model`, skipped without Ollama, so never in CI |
| Frontend components | The API client, the overview's helpers, the loading and failure states, a practice session | `web/src/**/*.test.ts(x)` |
| End to end | One learner's journey through the running app | `web/e2e/journey.spec.ts` |

## Decisions

### Type checking the backend with mypy

mypy checks `app/` in its default mode, with Pydantic's plugin, and CI runs
it (`api/pyproject.toml`). The tests are not type checked: their fixtures
carry no annotations to check. mypy was chosen over pyright because it
installs and pins like every other Python tool here (pip-tools); a trial run
of both found much the same (157 errors and 165).

It found 134 errors in 24 files, all fixed:

- **The largest share were a value that can be missing,** used without a
  check.
  - Where the value cannot be missing by an invariant the code relies on, the
    code now says so: it narrows the type, or raises an error naming the
    invariant if it is ever broken. For example, a locked artifact's
    document exists, because deleting the document waits for that lock.
  - The others were annotations that were missing or too loose.
- **Two were real bugs,** each now with a test that fails without its fix:
  - **A job whose environment was deleted while it ran** raised three
    errors in turn. It also left the deleted job's id on the worker's later
    log lines in that thread. It now stops where it is and logs that it was
    deleted.
  - **A passage whose document was deleted** between reading the passage
    and reading the document gave a 500 instead of the 404 that says it is
    gone.
- **Ten lines carry `# type: ignore`, each with its reason.** The schemas the
  model's answers are checked against are built at run time, from the
  passages a prompt holds, so mypy cannot know their fields.
- **`__mapper_args__` on ten models** is annotated as a read-only `Mapping`,
  which both mypy and Ruff accept. Its value did not change.

### Coverage, reported and never enforced

`pytest --cov` measures lines and branches with coverage.py; the frontend's
tests measure theirs with Vitest's V8 coverage. CI writes a summary on each
run's page and keeps the full reports for 14 days. No percentage fails a
build.

The report was read once, for code worth a test, and these gaps were filled:

- **The benchmark's report writer** (0% before). A test now checks that
  every table in the committed report is the one `results.json` gives, so a
  number edited by hand fails the build. It also checks that only the text
  between markers is replaced, empty marker pairs included, where Phase 20
  had a bug.
- **The worker's loops** (45% before).
  - One keep-alive pass sweeps leftover files, keeps its own job alive before
    looking for jobs a stopped worker left, and announces the worker in
    Redis.
  - A lane that meets an error goes on.
  - A worker that stops takes its announcement back.
- **The two bugs above.**

After them the backend is at 90%. The largest parts left uncovered on
purpose:

- **The benchmark's run itself** (`evaluation/benchmark.py`). It needs the
  real models and twenty minutes, and is run by hand.
- **The worker's `main()` and its signal handling.** The end-to-end test
  runs both, but its coverage is not measured.

The frontend's overall figure is low, 14%, by choice. Its component tests
are few, and the pages as a whole are covered by the end-to-end journey,
which coverage does not measure.

### Component tests where they are worth having

The tests use Vitest, React Testing Library and jsdom. They run the real API
client, with `fetch` replaced by answers each test lists (`src/test/network.ts`),
so what a page sends is checked as well as what it shows. They query the page
by role and name, as a reader and a screen reader find things, and use no
snapshots. They cover:

- **The API client** (`api.test.ts`): the message, status and request id of
  a failed request, as every section shows them; a request with no body sent
  without a content type, sparing a CORS preflight; ids escaped in paths.
- **The overview's helpers** (`overview.test.ts`): stage progress, the map's
  most connected concepts and where to start, sizes in bytes.
- **The loading and failure states** (`query-states.test.tsx`): the failure
  with its Reference, Try again and not twice at once, loading then data.
- **A practice session** (`practice-session.test.tsx`):
  - answer first, then the right answer, its source and when the concept
    comes back;
  - a short answer marked by the learner only after seeing the stored one;
  - what was sent, which decides the review schedule;
  - the summary at the end.

### One end-to-end journey

`web/e2e/journey.spec.ts` is one test, whose steps are the roadmap's twelve
scenarios, in order, through the page as a learner uses it:

| Step | What it checks |
|---|---|
| 1. Create an environment | The form makes it and opens it |
| 2. Upload a PDF | It appears in Materials |
| 3. Wait for processing | It is read (three pages), and its update names the three concepts it brought |
| 4. Search | The passage on round robin comes first for a question that asks about it |
| 5. View a citation | Show in page opens page 3 with the passage marked |
| 6. Summary | Written from one document; a key point's citation opens its passage |
| 7. Knowledge map | Two relationships, both through Threads |
| 8. Roadmap | One stage, its concepts in the material's order |
| 9. Practice | Preparing makes three concepts due; one item answered says when its concept comes back |
| 10. Review schedule | That concept is no longer due today, and has its next review |
| 11. Second PDF | It is read (two pages) |
| 12. The environment updates | Two new concepts, a relationship to the first document's Processes, practice kept, the summary from two documents, two stages, two documents read |

It also fails on any uncaught error on the page, any error the page logs, and
any request the API refuses. The one exception is a document's summary
answering 404 while it is not written yet, which the page shows as "not yet".

- **Real except the language model.** The API, the worker and the page are
  real, and so are PDF reading, embeddings, the reranker, Postgres and Redis.
  The language model is a stand-in, because the local model cannot run in CI
  (`api/tests/e2e/`). It is the backend tests' MockProvider through the same
  dependency override, except that each concept is named after its passage's
  heading. Real names matter here: the map pairs two concepts when a passage
  of one names the other, so with numbered names it would never show a
  relationship. The app's code has no knowledge of the stand-in.
- **A world of its own.** Playwright starts everything
  (`web/playwright.config.ts`).
  - Its own ports (8100 and 3100), database (`paideia_e2e`), data folder and
    Redis database.
  - `tests/e2e/prepare.py` empties all three at the start of every run, and
    refuses unless they are not development's. Emptying Redis forgets a
    worker an earlier run left behind without saying goodbye, which the
    first version of this test tripped over.
  - It runs while the development servers are up; that was tried.
- **Chromium only,** to keep the run short. Other browsers are not tested.

### CI in three jobs

- **API:**
  - lint, format and types;
  - the migrations, and the check that models match them;
  - the tests with coverage, with Postgres and Redis as services. The
    worker's tests talk to Redis.
- **Web:** lint, types, the component tests with coverage, and the build.
- **End to end:** Postgres and Redis as services, Chromium, and the journey.
  On failure it keeps Playwright's report and the trace, which replays every
  step with the page as it was.

A newer push to a pull request cancels the run it replaces. On main every
push keeps its run. Nothing is retried: a flaky test shows as a failure, and
its log is kept. This is how the one failure of the semantic search tests in
CI, during Phase 18, was handled: its log was kept before running again.

### Not added

- **A coverage target,** as the roadmap says.
- **Snapshot or visual tests.** They fail on every deliberate change of
  wording or style, and say nothing about whether the page works.
- **Other browsers,** to keep the run short.
- **The real language model and the benchmark in CI.** The model is a
  download of several gigabytes and CI's machines have no GPU, and the
  benchmark takes twenty minutes; both are run by hand (README, Tests).

## Testing the tests

- **Deliberate breaks:** 22 of 22 were caught by the new backend and
  frontend tests, and 2 of 2 by the journey.
  - Backend: the worker's beat, sweep, recovery order, announcement and lane
    errors; the report's markers and numbers.
  - Frontend: request ids, error messages, the JSON content type, the
    Reference, Try again, what a practice answer sends, how the session's
    end and gaps are worded, the overview's counts and order, byte sizes.
  - Journey: an answer that schedules nothing; a citation that marks
    nothing.
- **The two bugs' tests** each fail without their fix.
- **Stability:** the journey passed three runs in a row, about half a minute
  each, and once more with the development page server running beside it.

## Consequences

- **New code in `app/` must pass mypy.**
- **Running the journey locally** needs `pnpm exec playwright install
  chromium` once, and Postgres and Redis up.
- **The journey asserts visible text.** A change of wording on those pages
  means changing the test with it.
- **The benchmark's inputs fingerprint changed** with the fixes in `app/`.
  Its published results stay tied to the commit they record (record 20).
