"""Tests for the migrations in migrations/versions/.

Purpose: prove the models and the migrations agree, and that the whole chain
of migrations can be undone and reapplied. Both run against the test database.
"""

from alembic import command
from sqlalchemy import URL, Engine, inspect

from tests.conftest import alembic_config


def test_models_match_migrations(test_engine: Engine, test_database_url: URL):
    # Raises if `alembic revision --autogenerate` would find anything to add:
    # a model column, type, nullability or default with no migration behind it.
    command.check(alembic_config(test_database_url))


def test_migrations_downgrade_and_upgrade_cleanly(
    test_engine: Engine, test_database_url: URL
):
    config = alembic_config(test_database_url)

    command.downgrade(config, "base")
    assert "environments" not in inspect(test_engine).get_table_names()

    command.upgrade(config, "head")
    assert "environments" in inspect(test_engine).get_table_names()
