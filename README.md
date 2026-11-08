# Paideia

An adaptive learning workspace. You create one environment per subject, upload
your study material into it, and the workspace maintains its own summaries,
concept map, learning roadmap, practice questions and review schedule as the
material grows.

The point is that the system is stateful and proactive. You do not ask it for a
summary; adding a document updates the summary. Chat is deliberately not the
centre of the product.

## Status

Learning environments and their study material work end to end. You can create
environments, upload PDFs into each one, watch every PDF being read, and read
its text page by page. Each document is then cut into chunks along its
paragraphs and headings, ready for search: the same PDF always produces the
same chunks. Every chunk is also embedded by a local model, so passages can
be found by meaning as well as by their words.

The Search tab runs both kinds of search at once: keyword search inside
Postgres catches exact terms such as "TLB" or "Belady's anomaly", semantic
search catches paraphrases, Reciprocal Rank Fusion merges the two lists, and
a local cross-encoder reranks the best of them. On a labelled set of 32
questions this puts the right passage at the top far more often than either
search alone, and "Show scoring" reveals how each result was ranked.

Every result cites exactly where it came from: the document, the version of
its file, the pages and the passage. "Show in page" opens the citation, with
the passage highlighted in its page. Summaries and answers will cite their
sources the same way. A local language model comes next.

## Stack

| Layer | Choice |
|---|---|
| Frontend | Next.js 16, TypeScript, Tailwind CSS, TanStack Query |
| Backend | FastAPI, Pydantic, SQLAlchemy 2, Alembic |
| PDF reading | PyMuPDF |
| Embeddings and reranking | fastembed (ONNX Runtime) running BAAI/bge-small-en-v1.5 and ms-marco-MiniLM-L-6-v2, locally |
| Database | PostgreSQL 16 with pgvector |
| Jobs | Redis, provisioned but not yet used |
| Language models | Local, via Ollama, in a later phase |
| Quality | Ruff, pytest, ESLint, TypeScript, GitHub Actions |

The reasoning behind these choices is in
[docs/architecture/](docs/architecture/), starting with
[01-foundation.md](docs/architecture/01-foundation.md).

## Running it locally

Prerequisites: Docker Desktop, Python 3.13, Node 22, pnpm.

1. Start the database and Redis:

   ```sh
   docker compose up -d
   ```

2. Create your settings file:

   ```sh
   cp .env.example .env
   ```

   For local development, replace the placeholders as the comments describe:
   user, password and database are all `paideia`, host is `localhost`.

3. Backend, in one terminal:

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
   and the first search the reranking model, about 87 MB, both into
   `data/models/`. Those two moments need an internet connection; after that
   everything runs offline.

4. Frontend, in another:

   ```sh
   cd web
   pnpm install
   pnpm dev
   ```

Open http://localhost:3000. The header shows whether the API and the database
are reachable. The API's generated documentation is at
http://localhost:8000/docs.

The frontend reads the same root `.env` as the backend. It needs nothing from it
by default, since it assumes the API is at http://localhost:8000.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Is the API process alive. Touches nothing else. |
| GET | `/health/db` | Can the API reach Postgres, and is pgvector available. Returns 503 if not. |
| GET | `/api/environments` | Every environment, newest first. |
| POST | `/api/environments` | Create one. Body: `name`, optional `description`. Returns 201. |
| GET | `/api/environments/{id}` | One environment, or 404. |
| PATCH | `/api/environments/{id}` | Change only the fields sent. Returns the updated environment. |
| DELETE | `/api/environments/{id}` | Delete one, with its documents and files. Returns 204. |
| POST | `/api/environments/{id}/documents?filename=...` | Upload a PDF as the raw request body. Returns 201; reading happens in the background. |
| GET | `/api/environments/{id}/documents` | The environment's documents, newest first, with their status. |
| GET | `/api/documents/{id}` | One document: status is `uploaded`, `processing`, `ready` or `failed`. |
| GET | `/api/documents/{id}/pages` | The extracted text, page by page, numbered from 1. Paragraphs are separated by a blank line. |
| GET | `/api/documents/{id}/chunks` | The passages the document was cut into, in reading order, each with its heading and exact position in the pages. |
| POST | `/api/documents/{id}/reprocess` | Read a document again, for example after a failure. Returns 202. |
| DELETE | `/api/documents/{id}` | Delete one, with its pages and file. Returns 204. |
| POST | `/api/search` | Search one environment by keywords and meaning, fused and reranked. Body: `environment_id`, `query`, optional `top_k` (1 to 50, default 10), optional `debug`. Returns the best passages first, each as a `citation` (environment, document, `document_version`, the file's SHA-256, filename, chunk, pages, heading and `excerpt`) and a `score`, the reranker's judgement from 0 to 1. With `debug: true` it also returns every candidate with its keyword, semantic, fusion and rerank scores. |
| GET | `/api/chunks/{id}/preview` | A cited passage in its place: its citation, and every page it touches with the part it covers (`highlight_start` to `highlight_end`). 404 if the passage is no longer in its document. |

Invalid input gets a 422 listing each problem and the field it belongs to. An
upload is refused with 409 if the same file is already in that environment, 413
if it is larger than the limit (50 MB by default), and 415 if it is not a PDF.
Search returns 404 for an unknown environment, and 503 with the reason if the
embedding or reranking model cannot be loaded. A query written with search
syntax, a "quoted phrase", `OR` or a `-word`, is matched exactly; otherwise
any of its words may match.

Uploaded files are stored under `data/uploads/`, one folder per environment,
outside the database and outside git.

Documents read by an earlier version keep their old text format and may have
no chunks or no embeddings; a chunk without an embedding is still found by
its words.
`POST /api/documents/{id}/reprocess` reads one again with the current version,
embedding only the chunks that need it.

## Development

Backend, from `api/` with the virtual environment active:

```sh
ruff check --fix .   # lint
ruff format .        # format
pytest               # tests; needs docker compose up
```

The tests never touch your development database or your uploaded files. Each
run drops and rebuilds a separate `paideia_test` database from the migrations,
every test is rolled back when it finishes, and every test gets its own
temporary data folder. Test PDFs are built in code, so the repository holds no
binary files.

Most tests use stand-ins for the two models. A few load the real ones,
including the roadmap's "process scheduling" test and the retrieval
evaluation; they share the models in `data/models/`, so the first run
downloads them. The evaluation scores each way of searching on a labelled
set of questions; to print its table, from `api/`:

```sh
python -m tests.retrieval_eval
```

Python dependencies are pinned with pip-tools. Edit `api/requirements.in`, never
`api/requirements.txt`, then from `api/`:

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

Frontend, from `web/`:

```sh
pnpm lint
pnpm typecheck
pnpm build
```

CI runs all of the above on every pull request, with a real pgvector Postgres
behind the tests. It also applies the migrations and fails if a model changed
without a migration to match, and keeps both models cached between runs.

## Layout

```
api/                    FastAPI backend
  app/                  application code
    models.py           database tables, as Python classes
    schemas.py          request and response shapes
    parsing.py          PDF to page-numbered paragraphs and headings
    chunking.py         page text to deterministic chunks
    embedding.py        text to vectors, through a local model
    reranking.py        scoring passages against a query, through a local model
    storage.py          where uploaded files live on disk
    services/           business logic, no HTTP
    routers/            HTTP endpoints
  migrations/           Alembic migrations
  tests/                pytest suite
  requirements.in       direct dependencies, edited by hand
  requirements.txt      every dependency pinned, generated
web/                    Next.js frontend
  src/app/              pages and layouts
  src/components/       UI pieces
  src/hooks/            data fetching
  src/lib/              API client, types, config
data/                   uploaded files and the model cache, never committed
docs/architecture/      decision records
docker-compose.yml      local Postgres and Redis
.github/workflows/      CI
```
