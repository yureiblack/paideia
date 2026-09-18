# Paideia

An adaptive learning workspace. You create one environment per subject, upload
your study material into it, and the workspace maintains its own summaries,
concept map, learning roadmap, practice questions and review schedule as the
material grows.

The point is that the system is stateful and proactive. You do not ask it for a
summary; adding a document updates the summary. Chat is deliberately not the
centre of the product.

## Status

Foundation only. The repository currently contains the local infrastructure, a
backend with health endpoints, a frontend that reports whether it can reach
them, and CI. Document ingestion, retrieval and the learning features come next,
in that order.

## Stack

| Layer | Choice |
|---|---|
| Frontend | Next.js 16, TypeScript, Tailwind CSS |
| Backend | FastAPI, Pydantic, SQLAlchemy 2 |
| Database | PostgreSQL 16 with pgvector |
| Jobs | Redis, provisioned but not yet used |
| Language models | Local, via Ollama, in a later phase |
| Quality | Ruff, pytest, ESLint, TypeScript, GitHub Actions |

The reasoning behind these choices is in
[docs/architecture/01-foundation.md](docs/architecture/01-foundation.md).

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
   uvicorn app.main:app --reload
   ```

4. Frontend, in another:

   ```sh
   cd web
   pnpm install
   pnpm dev
   ```

Open http://localhost:3000. The page shows whether the API and the database are
reachable. The API's generated documentation is at http://localhost:8000/docs.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Is the API process alive. Touches nothing else. |
| GET | `/health/db` | Can the API reach Postgres, and is pgvector available. Returns 503 if not. |

## Development

Backend, from `api/` with the virtual environment active:

```sh
ruff check --fix .   # lint
ruff format .        # format
pytest               # tests; needs docker compose up
```

Frontend, from `web/`:

```sh
pnpm lint
pnpm typecheck
pnpm build
```

CI runs all of the above on every pull request, with a real pgvector Postgres
behind the tests.

## Layout

```
api/                    FastAPI backend
  app/                  application code
  tests/                pytest suite
web/                    Next.js frontend
docs/architecture/      decision records
docker-compose.yml      local Postgres and Redis
.github/workflows/      CI
```
