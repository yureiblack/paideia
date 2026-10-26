"""
Database connectivity.

## Purpose

Create one shared SQLAlchemy Engine for the application. The Engine manages a
pool of reusable database connections, allowing multiple requests to talk to
PostgreSQL concurrently instead of making every module create its own engine
and connection pool.

A connection is a single communication channel with PostgreSQL. The pool keeps
several of these channels available, reusing them as requests need them.
Too few connections can make requests wait; too many waste resources.

This module takes the database URL from config.py and is the only place that
turns that configuration into database connectivity. It knows nothing about
HTTP, routes, or business logic.
"""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)

# A factory for Sessions. A Session is a short-lived unit of work: it tracks the
# objects you load and change, and turns them into SQL on commit.
# expire_on_commit=False keeps objects readable after commit, which is exactly
# when an endpoint turns them into its JSON response.
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """Give one request its own Session, and close it when the request ends.

    FastAPI calls this for every request that declares a SessionDep parameter.
    Tests replace it with a Session that is rolled back after each test.
    """
    with SessionLocal() as session:
        yield session


# Shorthand for endpoint signatures: `session: SessionDep`.
SessionDep = Annotated[Session, Depends(get_session)]
