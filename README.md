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
the passage highlighted in its page.

A local language model, run by Ollama on your own machine, summarizes every
document as soon as it has been read: an overview and key points, each citing
the passages it rests on with the same citations search uses, so every claim
can be opened and checked in its page. Summaries are kept. The same document,
model and prompt never produce a second one; new text or a newer model
writes a new summary and keeps the earlier ones.

Each environment also keeps a summary of all its material, on its Summary tab,
up to date by itself. It is built from the documents' summaries and rebuilt
whenever they change: after a document is added and summarized, or deleted.
When nothing it is built from has changed, nothing is rebuilt. It shows when
it was last updated, which documents it is based on and in which version,
and which documents were left out and why, and every key point cites the
passages it rests on, across all the documents.

The model also proposes the concepts each document teaches, with a short
definition, other names, and the passages that explain them. The backend
checks every proposal before keeping it: names are cleaned up the same way
every time, so "Threads" and "Thread" are one concept, descriptions passed off
as other names are dropped, and only passages the model was actually given
count as evidence. The Knowledge map tab lists the environment's concepts,
each opening the passages behind it.

The concepts are joined into a knowledge graph: which must be understood
before which, which is a part of which, and which are related. The backend
finds the pairs of concepts that a passage connects, in one lecture or
across lectures, and the model only decides how each pair relates, or that
it does not. Every relationship cites the passages it was found in, and
there is at most one per pair of concepts. Decisions are remembered, so
adding a lecture asks the model only about the new pairs, and deleting one
asks nothing. On the Knowledge map tab, picking a concept shows what it
builds on, all the way back, what builds on it, its parts and what it is
related to, each a link to explore further.

The Roadmap tab turns the graph into an ordered path through the material,
in stages. The order is decided by fixed rules, never by the model: what a
concept builds on comes before it, concepts related within a lecture form a
stage, and otherwise the material's own order holds. Prerequisites that
loop are found and shown, to be learned together. The model only writes
each stage's title and a one-sentence description, which are remembered, so
adding a lecture asks only about the stages it changed. Every concept on the
roadmap links to its passages and to the Knowledge map.

The Practice tab is evidence-informed study support: answering from memory,
concepts coming back at growing intervals, and concepts mixed within a
session. Practice is prepared stage by stage. For each concept the model
writes a short answer, a multiple-choice, a true/false and a flashcard item
from the concept's own passages, and the backend keeps an item only if it is
plain, never talks about "the passages", and its answer is found in the
passages it cites. Multiple choice and true/false are checked against the
stored answer; short answers and flashcards are marked by the learner once
the answer is shown.

How the learner stands on each concept is worked out from their answers,
never stored apart from them: how often it was answered and recalled, when
last, and when it comes back. Each time a concept is recalled its next
review moves further away (1, 2, 4, 8, 16, then 32 days, at most one step a
sitting); a miss brings it back the next day. The Practice tab shows what is
due today, in the learner's own day, what needs attention and what is
recently strong, each with why; the Knowledge map and the Roadmap show each
concept's state in a line. Nothing is a grade.

## Stack

| Layer | Choice |
|---|---|
| Frontend | Next.js 16, TypeScript, Tailwind CSS, TanStack Query |
| Backend | FastAPI, Pydantic, SQLAlchemy 2, Alembic |
| PDF reading | PyMuPDF |
| Embeddings and reranking | fastembed (ONNX Runtime) running BAAI/bge-small-en-v1.5 and ms-marco-MiniLM-L-6-v2, locally |
| Database | PostgreSQL 16 with pgvector |
| Jobs | Redis, provisioned but not yet used |
| Language model | Ollama running ministral-3:8b locally, behind a replaceable provider interface |
| Quality | Ruff, pytest, ESLint, TypeScript, GitHub Actions |

The reasoning behind these choices is in
[docs/architecture/](docs/architecture/), starting with
[01-foundation.md](docs/architecture/01-foundation.md).

## Running it locally

Prerequisites: Docker Desktop, Python 3.13, Node 22, pnpm, and for
summaries, Ollama (on a Mac: `brew install ollama`).

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

5. For summaries, start Ollama and download the model once, about 6 GB:

   ```sh
   brew services start ollama
   ollama pull ministral-3:8b
   ```

   Ollama runs on the machine itself rather than in Docker: on a Mac, Docker
   cannot use the GPU, and the model would be several times slower. It needs
   about 7.5 GB of memory while it works. Everything else in the app runs
   without it.

Open http://localhost:3000. The header shows whether the API, the database and
the language model are ready; hover over one that is down to see why. The API's generated documentation is at
http://localhost:8000/docs.

The frontend reads the same root `.env` as the backend. It needs nothing from it
by default, since it assumes the API is at http://localhost:8000.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Is the API process alive. Touches nothing else. |
| GET | `/health/db` | Can the API reach Postgres, and is pgvector available. Returns 503 if not. |
| GET | `/health/llm` | Is Ollama answering, with the configured model downloaded. Returns 503 with the reason if not. |
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
| GET | `/api/documents/{id}/summary` | The document's current summary: `status` (`pending`, `generating`, `ready` or `failed` with an `error`), then its `overview` and `key_points`, each with its `citations`, the `model` and `prompt_versions` that wrote it, and how many `earlier_versions` are kept. 404 if none yet. |
| POST | `/api/documents/{id}/summary` | Make sure the document has a summary: 200 with it if ready, 202 if it is waiting or being written, which this starts if it was missing or had failed. Asking again never writes a second one. 409 if the document is not read yet, 422 if it cannot be summarized (no text, or too long). |
| GET | `/api/documents/{id}/summaries` | Every summary of the document, newest first, `current` marking the one for its present text, model and prompts. |
| GET | `/api/environments/{id}/summary` | Where the environment's summary stands: `state` (`up_to_date`, `updating`, `waiting` for documents still being read or summarized, `stale`, `failed`, or `none`), the newest `summary` with its `overview`, cited `key_points` and the documents it is `based_on`, the documents `not_included` and why, and how many `earlier_versions` are kept. |
| POST | `/api/environments/{id}/summary` | Bring it up to date, or try again after a failure. It never writes twice for the same material, and waits while documents are on their way. 422 if there is nothing summarized to build it from. |
| GET | `/api/environments/{id}/summaries` | Every summary of the environment, newest first. |
| GET | `/api/environments/{id}/concepts` | Every concept in the environment, by name, with its `definition`, `aliases`, the `documents` it appears in and the `evidence` citations; and each document's extraction state (`proposed` and `kept` counts what passed validation). |
| GET | `/api/documents/{id}/concepts` | One document's extraction state and the concepts it contributes. |
| POST | `/api/documents/{id}/concepts` | Make sure the document's concepts are extracted, or try again after a failure: 200 if ready, 202 if waiting or being extracted. 409 if the document is not read yet, 422 if it has no text or is too long. |
| GET | `/api/environments/{id}/graph` | The environment's knowledge graph: every concept as a `node`, every relationship as an `edge` (`source`, `target`, `relationship_type` `PREREQUISITE_OF`, `PART_OF` or `RELATED_TO`, and the model's `confidence`), and where it stands: `state` as for the environment's summary, with `waiting` for documents still being read or having their concepts extracted; `pairs` considered and how many the model was `asked` about in the last build. |
| POST | `/api/environments/{id}/graph` | Bring the graph up to date, or try again after a failure: 200 if up to date, 202 if being built or waiting. It never asks the model twice about the same pair. 422 if no concepts are connected yet. |
| GET | `/api/concepts/{id}/neighbourhood` | One concept and what is next to it: its `prerequisites` and `dependents`, all the way along with their `depth`, what it is `part_of`, its `parts`, and what it is `related` to, each direct relationship with its `confidence` and `evidence` citations. |
| GET | `/api/environments/{id}/roadmap` | The learning roadmap: its `stages` in order, each with a `title` and `description` (`written` by the local model, or a plain title until then), the `documents` it draws on, and its `concepts` in order, each with what it `builds_on`, whether it is `in_cycle`, and its `evidence` citations; the `cycles` of prerequisites; and the `state` of the titles, as for the environment's summary, with `waiting` for the knowledge graph. |
| POST | `/api/environments/{id}/roadmap` | Write the titles of the current stages, or try again after a failure: 200 if up to date, 202 if being written or waiting for the graph. It never asks the model twice about the same stage. 422 if there are no concepts yet. |
| GET | `/api/environments/{id}/practice?until=...` | Practice at a glance, with `until` the end of the learner's day (with its time zone): how many items are practised, how many concepts are `due_concepts` today and `new_concepts`, the next later review, the concepts that `needs_attention` and are `recently_strong` with why, and each concept: its items' `state` (`none`, `pending`, `generating`, `ready`, `failed` with an `error`, or `outdated` when its material changed) and the learner's state worked out from their answers (`review` new, due or scheduled; `exposures`, `recalled`, `failed`, last attempted and recalled, `gap_days`, `next_review_at`, `attention`). |
| POST | `/api/environments/{id}/practice` | Prepare practice items for the concepts in `concept_ids`, in the background: 202 while they are written. Never writes twice for the same passages, model and prompt. |
| POST | `/api/concepts/{id}/practice` | The same, for one concept. |
| GET | `/api/environments/{id}/practice/session?until=...` | A session of up to 10 items, interleaved: two items from each concept due by `until`, overdue first, then new ones in roadmap order; or with `concept_id` repeated (a stage) those concepts' items. Items of the kinds the backend grades never carry their answer. |
| POST | `/api/learning-items/{id}/attempts` | Answer an item: `choice` (multiple choice), `truth` (true/false) or `knew` (short answer, flashcard, after seeing the answer), with optional `text` and `seconds`. Returns whether it was right, the answer, why, the passages it comes from, and when its concept comes back (`due_at`, `gap_days`). 409 if the item was replaced, 422 for an answer of the wrong kind. |
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

Most tests use stand-ins for the models. A few load the real ones,
including the roadmap's "process scheduling" test and the retrieval
evaluation; they share the models in `data/models/`, so the first run
downloads them. One test summarizes a document with the real language model;
it runs only when Ollama is up with the model downloaded, and is skipped
otherwise, including in CI. The evaluation scores each way of searching on a labelled
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
    llm.py              the language model behind a replaceable interface
    prompting.py        prompt templates, loaded by name and version
    prompts/            the templates, one file per version, never edited
    concepts.py         concept names and the validation of the model's proposals
    graph.py            candidate pairs of concepts, and what a decision means
    roadmap.py          the roadmap's stages and order, by fixed rules
    practice.py         practice items' checks, review boxes and sessions
    learner.py          learner state per concept, from the answers, and its schedule
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
