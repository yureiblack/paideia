"""The FastAPI application and its HTTP endpoints.

Purpose
-------
Expose the backend over HTTP. This is the only module aware of both the
configuration and the database, which is precisely why it would be the only one
to change if the web framework were ever swapped out (eg: Flask instead of FastAPI).

Run locally with:  uvicorn app.main:app --reload
Interactive API docs are then generated automatically at /docs.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db import engine

# The application object. Every route and every piece of middleware attaches to
# this, and uvicorn is pointed at it by name as "app.main:app".
app = FastAPI(title="Paideia API", version="0.1.0")

# Browsers refuse to let a page served from one origin call another unless the
# server explicitly allows it. The Next.js dev server runs on port 3000 while
# this API runs on 8000, which counts as a different origin, so without this the
# frontend health indicator would be blocked before the request ever arrived.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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
