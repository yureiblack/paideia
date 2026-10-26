"""Alembic's entry point: connects to the database and runs the migrations.

Purpose
-------
Alembic executes this file for every command: upgrade, downgrade, current,
revision. It decides which database to talk to and hands Alembic a connection.

The connection string comes from app.config.settings, the same object the
application uses. That keeps one source of truth: the DATABASE_URL in the root
.env locally, or the DATABASE_URL environment variable in CI.

The one exception is the test suite, which runs these same migrations against
a separate *_test database. It passes that URL in through config.attributes,
a dictionary Alembic offers for exactly this kind of programmatic override.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.config import settings
from app.models import Base

# The parsed alembic.ini. Used here only for its logging section.
config = context.config

# Apply the [loggers] section of alembic.ini, which is what prints the
# "Running upgrade ..." lines.
# disable_existing_loggers=False matters when tests run migrations from inside
# Python: without it, this would silence every logger already set up.
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# The URL to migrate: the test suite's override if one was given, otherwise the
# application's own setting.
database_url = config.attributes.get("database_url", settings.database_url)

# The model catalogue that `alembic check` and `alembic revision --autogenerate`
# compare the live database against.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Print the migration SQL instead of running it.

    Triggered by the --sql flag, for example `alembic upgrade head --sql`.
    Nothing connects to the database; useful for reading exactly what a
    migration would do.
    """
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect to the database and apply the migrations for real."""
    # NullPool opens one connection, uses it and closes it. A migration run is
    # a short one-off process, so a pool of idle connections would be waste.
    engine = create_engine(database_url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Off by default, which lets a column default in a model drift from
            # the table unnoticed. On, `alembic check` catches that too.
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
