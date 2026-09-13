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

from sqlalchemy import create_engine

from app.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
