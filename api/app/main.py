"""The FastAPI application and its HTTP endpoints.

Purpose
-------
Expose the backend over HTTP. This is the only module aware of both the
configuration and the database, which is precisely why it would be the only one
to change if the web framework were ever swapped out (eg: Flask instead of FastAPI).

Run locally with:  uvicorn app.main:app --reload
Interactive API docs are then generated automatically at /docs.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app import correlation, logs
from app.config import settings
from app.db import engine
from app.routers import (
    concepts,
    documents,
    environment_summaries,
    environments,
    graph,
    jobs,
    plan,
    practice,
    roadmap,
    search,
    sources,
    summaries,
    updates,
)
from app.routers.deps import DispatcherDep, LLMDep


# The application object. Every route and every piece of middleware attaches to
# this, and uvicorn is pointed at it by name as "app.main:app".
@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Set up structured logging when the server starts (app/logs.py). The
    tests never start the server this way, so they keep pytest's own log
    capture."""
    logs.configure()
    yield


app = FastAPI(title="Paideia API", version="0.1.0", lifespan=lifespan)

# Request ids, one log line per request, and error bodies that carry the id
# (app/correlation.py). Added before CORS, so that CORS wraps it and even its
# own error responses reach the page.
correlation.install(app)

# Browsers refuse to let a page served from one origin call another unless the
# server explicitly allows it. The Next.js dev server runs on port 3000 while
# this API runs on 8000, which counts as a different origin, so without this the
# frontend would be blocked before the request ever arrived. Which origins are
# allowed is configuration, not code, so it comes from the settings object.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
    # Lets the page read the request id, to show it beside an error.
    expose_headers=[correlation.HEADER],
)

# Feature endpoints live in app/routers/ and are mounted under /api, which keeps
# them apart from the health checks and any future non-API routes.
app.include_router(environments.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
app.include_router(search.router, prefix="/api")
app.include_router(sources.router, prefix="/api")
app.include_router(summaries.router, prefix="/api")
app.include_router(environment_summaries.router, prefix="/api")
app.include_router(concepts.router, prefix="/api")
app.include_router(graph.router, prefix="/api")
app.include_router(roadmap.router, prefix="/api")
app.include_router(practice.router, prefix="/api")
app.include_router(plan.router, prefix="/api")
app.include_router(updates.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")


class Health(BaseModel):
    """Response shape for GET /health.

    Declaring the response as a class rather than returning a loose dictionary
    is what lets FastAPI validate what goes out and publish an accurate schema.
    """

    status: str


class DatabaseHealth(BaseModel):
    """Response shape for GET /health/db."""

    status: str
    pgvector_available: bool


class LLMHealth(BaseModel):
    """Response shape for GET /health/llm."""

    status: str
    model: str


@app.get("/health", response_model=Health)
def health() -> Health:
    """Report whether the API process is alive.

    Deliberately touches nothing else, so it keeps answering truthfully even
    when the database is unreachable. This is the endpoint a container
    healthcheck or load balancer should call, because it distinguishes "the
    process is gone" from "a dependency is struggling".
    """
    return Health(status="ok")


@app.get("/health/db", response_model=DatabaseHealth)
def health_db() -> DatabaseHealth:
    """Report whether the API can reach Postgres, and whether pgvector is there.

    Answers 503 rather than raising, so an unreachable database reads as an
    unhealthy service instead of an unhandled crash. The pgvector check confirms
    the container is the right image, which everything from Phase 05 onward
    depends on.
    """
    try:
        with engine.connect() as connection:
            # The cheapest possible query. Proves the connection genuinely
            # works, rather than merely being open.
            connection.execute(text("select 1"))

            # Reports whether Postgres carries the extension, not whether it is
            # switched on in this database. Enabling it is a schema change and
            # therefore belongs in an Alembic migration, not here.
            found = connection.execute(
                text(
                    "select count(*) from pg_available_extensions where name = 'vector'"
                )
            ).scalar_one()
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc

    return DatabaseHealth(status="ok", pgvector_available=found == 1)


class WorkerHealth(BaseModel):
    """Response shape for GET /health/worker."""

    status: str
    workers: int


@app.get("/health/worker", response_model=WorkerHealth)
def health_worker(dispatcher: DispatcherDep) -> WorkerHealth:
    """Report whether a background worker is running (decision record 18).

    Answers 503 with what to do, rather than failing, so the header can say
    so: without a worker, jobs wait in the queue."""
    count = dispatcher.workers()
    if count is None:
        raise HTTPException(
            status_code=503, detail="Redis is not reachable, so no worker can be seen."
        )
    if count == 0:
        raise HTTPException(
            status_code=503,
            detail="No worker is running. Start one with: python -m app.worker",
        )
    return WorkerHealth(status="ok", workers=count)


@app.get("/health/llm", response_model=LLMHealth)
def health_llm(llm: LLMDep) -> LLMHealth:
    """Report whether the language model is ready: Ollama answering, and the
    configured model downloaded.

    Like /health/db it answers 503, with the reason, rather than failing, so
    the header can show what to fix. Only summaries need the model; the rest
    of the app works without it.
    """
    problem = llm.check()
    if problem is not None:
        raise HTTPException(status_code=503, detail=problem)
    return LLMHealth(status="ok", model=llm.model_name)
