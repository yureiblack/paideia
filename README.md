# Paideia

An adaptive learning workspace. You create one environment per subject, upload
your study material into it, and the workspace maintains its own summaries,
concept map, learning roadmap, practice questions and review schedule as the
material grows.

The point is that the system is stateful and proactive. You do not ask it for a
summary; adding a document updates the summary. Chat is deliberately not the
centre of the product.

## Status

Learning environments work end to end. You can create, rename, describe and
delete environments, and each one has its own page with tabs for the features
still to come: materials, knowledge map, roadmap, summary and practice. Document
ingestion is next, followed by retrieval and the learning features.

## Stack

| Layer | Choice |
|---|---|
| Frontend | Next.js 16, TypeScript, Tailwind CSS, TanStack Query |
| Backend | FastAPI, Pydantic, SQLAlchemy 2, Alembic |
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
| DELETE | `/api/environments/{id}` | Delete one. Returns 204. |

Invalid input gets a 422 listing each problem and the field it belongs to.

## Development

Backend, from `api/` with the virtual environment active:

```sh
ruff check --fix .   # lint
ruff format .        # format
pytest               # tests; needs docker compose up
```

The tests never touch your development database. Each run drops and rebuilds a
separate `paideia_test` database from the migrations, and every test is rolled
back when it finishes.

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
without a migration to match.

## Layout

```
api/                    FastAPI backend
  app/                  application code
    models.py           database tables, as Python classes
    schemas.py          request and response shapes
    services/           business logic, no HTTP
    routers/            HTTP endpoints
  migrations/           Alembic migrations
  tests/                pytest suite
web/                    Next.js frontend
  src/app/              pages and layouts
  src/components/       UI pieces
  src/hooks/            data fetching
  src/lib/              API client, types, config
docs/architecture/      decision records
docker-compose.yml      local Postgres and Redis
.github/workflows/      CI
```
