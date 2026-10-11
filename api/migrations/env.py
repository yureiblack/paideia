"""Alembic's entry point: connects to the database and runs the migrations.

Purpose
-------
Alembic executes this file for every command: upgrade, downgrade, current,
revision. It decides which database to talk to and hands Alembic a connection.

The connection string comes from app.config.settings, the same object the
application uses. That keeps one source of truth: the DATABASE_URL in the root
.env locally, or the DATABASE_URL environment variable in CI.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.config import settings

# The parsed alembic.ini. Used here only for its logging section.
config = context.config

# Apply the [loggers] section of alembic.ini, which is what prints the
# "Running upgrade ..." lines.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The model metadata that `alembic revision --autogenerate` compares the live
# database against. None until the first SQLAlchemy model exists; it becomes
# Base.metadata in the next step of this phase.
target_metadata = None


def run_migrations_offline() -> None:
    """Print the migration SQL instead of running it.

    Triggered by the --sql flag, for example `alembic upgrade head --sql`.
    Nothing connects to the database; useful for reading exactly what a
    migration would do.
    """
    context.configure(
        url=settings.database_url,
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
    engine = create_engine(settings.database_url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
