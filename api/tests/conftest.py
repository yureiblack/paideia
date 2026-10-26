"""Shared test fixtures: a separate test database, and a clean slate per test.

Purpose
-------
Tests that write data must never touch the development database. This file
gives them their own:

1. A database named after the real one with "_test" appended, so "paideia"
   becomes "paideia_test". It is dropped and recreated empty at the start of
   every test run, then built purely by running the Alembic migrations. A
   model change that ships without its migration therefore breaks the tests.
2. A guard that refuses to run against any database not named *_test.
3. A Session per test, inside a transaction that is rolled back when the test
   ends. Every test starts from an empty database, and nothing is ever really
   written, which also makes the suite fast.

Code under test may call session.commit() freely. Inside the outer transaction
each commit only releases a savepoint, a bookmark inside the transaction, so
the final rollback still undoes everything.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import URL, Engine, create_engine, make_url, text
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_session
from app.main import app

API_DIR = Path(__file__).resolve().parents[1]


def _test_database_url() -> URL:
    """The development URL with "_test" appended to the database name."""
    url = make_url(settings.database_url)
    test_url = url.set(database=f"{url.database}_test")
    if not (test_url.database or "").endswith("_test"):
        raise RuntimeError(
            f"Refusing to run tests against {test_url.database!r}: "
            "the test database name must end in _test."
        )
    return test_url


def _recreate_database(url: URL) -> None:
    """Drop the test database if it exists and create it empty.

    CREATE and DROP DATABASE cannot run inside a transaction, so this connects
    to Postgres's built-in "postgres" database in autocommit mode. WITH (FORCE)
    closes any leftover connections, from an editor or a crashed run, that
    would otherwise block the drop.
    """
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(
            text(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)')
        )
        connection.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()


def alembic_config(url: URL) -> Config:
    """Alembic's configuration, aimed at the given database instead of dev."""
    config = Config(str(API_DIR / "alembic.ini"))
    config.attributes["database_url"] = url.render_as_string(hide_password=False)
    return config


@pytest.fixture(scope="session")
def test_database_url() -> URL:
    return _test_database_url()


@pytest.fixture(scope="session")
def test_engine(test_database_url: URL) -> Iterator[Engine]:
    """Build the test database once per run, from the migrations alone."""
    _recreate_database(test_database_url)
    command.upgrade(alembic_config(test_database_url), "head")
    engine = create_engine(test_database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def session(test_engine: Engine) -> Iterator[Session]:
    """A Session whose every change is rolled back when the test ends."""
    with test_engine.connect() as connection:
        transaction = connection.begin()
        session = Session(
            bind=connection,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )
        try:
            yield session
        finally:
            session.close()
            transaction.rollback()


@pytest.fixture
def client(session: Session) -> Iterator[TestClient]:
    """An HTTP client whose requests all use the rolled-back test Session."""
    app.dependency_overrides[get_session] = lambda: session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
