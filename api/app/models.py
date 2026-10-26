"""Database models: how the Python code sees each table.

Purpose
-------
A model is a Python class that mirrors one table. The class is the table, each
attribute is a column, and each object is one row. Code builds and reads these
objects; SQLAlchemy turns that into SQL.

The models describe the tables but never change them. Tables are created and
altered only by the Alembic migrations in migrations/versions/. `alembic check`
compares the two and fails if they disagree, so a model change that ships
without its migration is caught.

One flat file until a second model arrives.
"""

import uuid
from datetime import datetime
from typing import Any, ClassVar

from sqlalchemy import DateTime, MetaData, Text, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Predictable names for constraints and indexes, so a later migration can find
# and drop them by name. The primary-key pattern matches Postgres's own default,
# "<table>_pkey", so the existing environments_pkey already conforms.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "%(table_name)s_pkey",
}


class Base(DeclarativeBase):
    """Parent of every model. Its metadata is the catalogue Alembic compares."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Environment(Base):
    """One learning environment: a subject such as Operating Systems.

    Mirrors revision 0a84e5243328 column for column.
    """

    __tablename__ = "environments"

    # Values the database generates (id, timestamps) come back in the same
    # INSERT or UPDATE statement through RETURNING, instead of a second query.
    __mapper_args__: ClassVar[dict[str, Any]] = {"eager_defaults": True}

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # statement_timestamp(), not now(): Postgres's now() is frozen at the start
    # of the transaction, so an edit made later in the same transaction, which
    # is how every test runs, would not move it.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.statement_timestamp(),
    )
