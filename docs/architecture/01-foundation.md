# 01. Foundation

Date: 2026-09-18
Status: accepted

## Context

Paideia needs ordinary relational data (environments, documents, concepts,
attempts, schedules), full-text search, vector search for semantic retrieval,
and a language model for extraction and generation. It is a personal project
that has to run on one laptop at no cost, and every choice should be easy to
explain and defend.

## Decisions

### PostgreSQL with pgvector, not a separate vector database

One database holds the relational tables, the full-text index and the
embeddings. pgvector supports exact and approximate nearest-neighbour search
and combines with Postgres full-text search in a single query, which is what
hybrid retrieval needs. A dedicated vector store would add a second system to
run, back up and keep consistent, for a dataset that will stay small.

### FastAPI for the backend

The heavy work is Python: PDF parsing, embeddings, reranking, model calls.
Keeping the API in the same language as that processing avoids a second
service and a serialization boundary between them. FastAPI gives typed request
and response contracts through Pydantic and generates the API documentation
from those same types.

### Next.js for the frontend

The product is a dashboard: environments, documents, graphs, schedules.
Next.js provides routing, server rendering and a mature component ecosystem
without assembling them by hand. Tailwind keeps styling next to the components
that use it.

### Local-first AI

Embeddings will come from Sentence Transformers and generation from a local
model served by Ollama, each behind a small interface so it can be swapped.
This removes API cost, keeps the project reproducible offline, and forces the
deterministic parts of the system, such as scheduling, change detection and
provenance, to stay in application code rather than drift into prompts.

### Redis now, background jobs later

Redis is in the Compose file so the local stack is complete from the start,
but nothing reads from it. Background processing will begin with FastAPI's
built-in background tasks and move to a Redis-backed queue only once ingestion
becomes long-running enough to need one.

## Consequences

- One `docker compose up` produces a complete local environment.
- Schema changes go through Alembic migrations, including enabling pgvector.
  That is why the database health check reports the extension as available
  rather than switching it on.
- The language model is a replaceable dependency, not the architecture.
- No orchestration framework and no graph database until a concrete need
  appears.
