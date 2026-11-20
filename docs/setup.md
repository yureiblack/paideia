# Local setup

How to run Paideia on your own machine, work on it, and run its tests. Every
part runs locally: the database, the search models and the language model.
Nothing is sent to a hosted service.

- [Prerequisites](#prerequisites)
- [First run](#first-run)
- [Checking that it works](#checking-that-it-works)
- [Settings](#settings)
- [Development](#development)
- [Tests](#tests)
- [When something is not ready](#when-something-is-not-ready)

## Prerequisites

- Docker Desktop, for Postgres and Redis
- Python 3.13
- Node 22 and pnpm 10
- Ollama, for everything the language model writes (on a Mac:
  `brew install ollama`)

The language model needs about 6 GB of disk and about 7.5 GB of memory while it
works. Everything else in the app runs without it.

## First run

Run each step from the repository root unless it says otherwise.

1. **Start the database and Redis:**

   ```sh
   docker compose up -d
   ```

2. **Create your settings file:**

   ```sh
   cp .env.example .env
   ```

   Then, in `.env`, replace the placeholders in `DATABASE_URL` as its comment
   describes: user, password and database are all `paideia`, and host is
   `localhost`. Every other setting has a working default; see
   [Settings](#settings).

3. **The backend,** in one terminal:

   ```sh
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r api/requirements.txt
   cd api
   alembic upgrade head
   uvicorn app.main:app --reload
   ```

   `alembic upgrade head` creates the tables. Run it again whenever you pull a
   change that adds a migration.

   The first document you upload downloads the embedding model, about 64 MB,
   and the first search downloads the reranking model, about 87 MB, both into
   `data/models/`. Those two moments need an internet connection; after that
   everything runs offline.

4. **The background worker,** in a second terminal, from `api/` with the
   same virtual environment active:

   ```sh
   python -m app.worker
   ```

   It reads uploaded documents and does all of the language model's work,
   outside the API, so restarting the API loses nothing. Without it, uploads
   wait in the queue, and the page's header says so. Stop it with Ctrl+C: it
   finishes the step it is on and puts its job back for the next worker. At
   start and every hour, it removes files that no document accounts for, and
   logs each one.

5. **The frontend,** in a third terminal:

   ```sh
   cd web
   pnpm install
   pnpm dev
   ```

6. **The language model.** Start Ollama and download the model once, about
   6 GB:

   ```sh
   brew services start ollama
   ollama pull ministral-3:8b
   ```

   Ollama runs on the machine itself rather than in Docker. On a Mac, Docker
   cannot use the GPU, and the model would be several times slower.

Open http://localhost:3000.

On later runs, only these are needed:
- `docker compose up -d`;
- the three processes from steps 3 to 5, without the install lines;
- Ollama, if it is not already running as a service.

## Checking that it works

The page's header shows whether the API, the database, the language model and
the worker are ready. Hover over one that is down to see why. The same checks
answer at:

| Address | Answers |
|---|---|
| http://localhost:8000/health | The API process is alive. |
| http://localhost:8000/health/db | Postgres is reachable, with pgvector. |
| http://localhost:8000/health/worker | A worker is running. |
| http://localhost:8000/health/llm | Ollama answers, with the model downloaded. |

The API's generated documentation is at http://localhost:8000/docs, and
[api.md](api.md) describes every endpoint.

To see the whole loop:
1. Create an environment.
2. Upload a lecture PDF on its Materials tab, and watch each step finish.
3. Upload a second one. Its update lists what changed: new concepts, new
   relationships, new stages, and what was left as it was.

The lectures in [`docs/evaluation/corpus/`](evaluation/corpus/) were written
for this project. `api/evaluation/corpus.py` turns them into PDFs for the
benchmark.

## Settings

Every setting is listed in [`.env.example`](../.env.example), with its
default and what it does. The ones you are most likely to change:

| Setting | Default | What it is |
|---|---|---|
| `DATABASE_URL` | none, required | Postgres, with the `+psycopg` driver |
| `LOG_FORMAT` | `json` | `text` makes the API's and worker's logs readable while working locally |
| `LLM_MODEL` | `ministral-3:8b` | The Ollama model that writes summaries, concepts, relationships, stage titles and practice |
| `DATA_DIR` | `data` | Where uploaded PDFs are kept, one folder per environment |
| `MAX_UPLOAD_MB`, `MAX_PAGES` | 50, 1000 | The largest PDF accepted, in megabytes and in pages |
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | Where the browser finds the API; read when the frontend is built or `pnpm dev` starts |

The frontend reads the same root `.env` as the backend.

## Development

Backend checks, from `api/` with the virtual environment active:

```sh
ruff check --fix .   # lint
ruff format .        # format
mypy                 # check the type annotations in app/
```

Frontend checks, from `web/`:

```sh
pnpm lint
pnpm typecheck
pnpm build
```

The backend checks formulas against the commands the page's KaTeX supports,
listed in `api/app/katex.json` (decision record 24). After changing KaTeX's
version, write the list again from `web/`, and commit it:

```sh
pnpm katex:commands
```

Python dependencies are pinned with pip-tools. Edit `api/requirements.in`, never
`api/requirements.txt`. Then, from `api/`:

```sh
pip-compile --strip-extras --unsafe-package pip requirements.in   # pin everything
pip install -r requirements.txt                                     # install it
```

Changing the schema, also from `api/`:

```sh
alembic revision --autogenerate -m "describe the change"   # draft a migration
alembic upgrade head                                       # apply it
alembic check                                              # models match tables?
alembic downgrade -1                                       # undo the latest one
```

Always read a generated migration before applying it.

## Tests

Postgres and Redis must be up (`docker compose up -d`). None of the tests
touch:
- your development database;
- your uploaded files;
- development's Redis database.

[Decision record 22](architecture/22-testing-and-ci.md) maps every kind of
test to the files that hold it.

**Backend,** from `api/`:

```sh
pytest                              # every backend test
pytest --cov                        # the same, with a coverage summary
pytest --cov --cov-report=html      # and a page per file in htmlcov/
```

How each run is isolated:
- It drops and rebuilds a separate `paideia_test` database from the
  migrations.
- Every test is rolled back when it finishes, and every test gets its own
  temporary data folder.
- Test PDFs are built in code, so the repository holds no binary test files.

Most tests use stand-ins for the models. A few load the real search models,
among them the retrieval evaluation, which shares `data/models/` with
development. One test summarizes a document with the real language model. It
runs only when Ollama is up with the model downloaded, and is skipped
otherwise, including in CI. To print the retrieval evaluation's table, from
`api/`:

```sh
python -m tests.retrieval_eval
```

**Frontend component tests,** from `web/`. They run in a simulated browser,
and each test supplies the API's answers:

```sh
pnpm test               # once
pnpm test:watch         # again on every change
pnpm test:coverage      # with a coverage report in coverage/
```

**The end-to-end journey,** from `web/`. It walks one learner through the
running app in a real browser:
1. creates an environment, uploads a PDF and waits for it to be read;
2. searches it and opens a citation;
3. reads the summary, the knowledge map and the roadmap;
4. answers a practice item and sees its review scheduled;
5. adds a second PDF and sees what it changed.

Once:

```sh
pnpm exec playwright install chromium
```

Then each time:

```sh
pnpm e2e
```

It starts its own API, worker and page, on ports 8100 and 3100. They use their
own database (`paideia_e2e`), data folder (`web/e2e/.state/`) and Redis
database, all emptied at the start of every run, so the journey can run while
the development servers are up.

Everything is real except the language model, which is a stand-in
(`api/tests/e2e/`), because the local model cannot run in CI. A run takes
about half a minute once the page is built.

**The benchmark** (decision record 20) is not run in CI. It takes about
twenty minutes. Run it from the repository root, with the services up:

```sh
python scripts/evaluate_retrieval.py                # retrieval, about twenty minutes
python scripts/evaluate_retrieval.py --generation   # also the summaries, with Ollama
```

It rebuilds its own database, the development database's name with `_eval`
appended, and rewrites the tables in
[`docs/evaluation/retrieval-benchmark.md`](evaluation/retrieval-benchmark.md).

**CI** runs on every pull request and every push to main, in three jobs:
- **Backend:** lint, format, types, the migrations, the check that models
  match them, and the tests with coverage.
- **Frontend:** lint, types, component tests with coverage, and the build.
- **End to end:** the journey.

Coverage is reported on each run's page, and no percentage fails a build. A
failed test is never retried. When the journey fails, its trace and report
are kept.

## When something is not ready

- **The header shows the worker as down.** Start it (step 4). Uploads wait
  in the queue until a worker takes them.
- **The header shows the language model as down.** Start Ollama, and check
  that `ollama list` shows `ministral-3:8b`. Documents are still read,
  embedded and searchable without it. What the model writes fails, with the
  reason shown where it would appear. Once Ollama answers, use Try again on
  each section that failed.
- **The database is down.** Run `docker compose up -d`, and check
  `docker compose ps` says `healthy`.
- **Errors carry a Reference.** Every error the page shows has one. It is the
  request's id, which finds the request in the API's log, and the log lines of
  any job it queued.
