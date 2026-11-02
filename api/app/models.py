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

Tables so far: environments, documents, document_pages, document_chunks.
"""

import uuid
from datetime import datetime
from typing import Any, ClassVar

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Predictable names for constraints and indexes, so a later migration can find
# and drop them by name. The primary-key pattern matches Postgres's own default,
# "<table>_pkey", so the existing environments_pkey already conforms.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    # Every column, so a two-column constraint names both: uq_documents_environment_id_sha256.
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
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


# The four stages of a document, in order. Stored lowercase as text with a
# CHECK constraint rather than a native Postgres ENUM, so adding a stage later
# is an ordinary migration.
DOCUMENT_STATUSES = ("uploaded", "processing", "ready", "failed")


class Document(Base):
    """One uploaded PDF belonging to an environment.

    The original file lives on disk at
    <data_dir>/uploads/<environment_id>/<id>.pdf, never in the database.
    status moves uploaded -> processing -> ready or failed; error says why a
    document failed. page_count, pages_with_text and repaired are filled in
    by a successful parse.
    """

    __tablename__ = "documents"
    __table_args__ = (
        # The same PDF twice in one environment is a mistake; the same PDF in
        # two environments is fine. Enforced here, not only in code, so two
        # simultaneous uploads cannot both slip through.
        UniqueConstraint("environment_id", "sha256"),
        CheckConstraint(
            "status IN ('uploaded', 'processing', 'ready', 'failed')", name="status"
        ),
    )
    __mapper_args__: ClassVar[dict[str, Any]] = {"eager_defaults": True}

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    # Deleting an environment deletes its documents in the database itself.
    environment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("environments.id", ondelete="CASCADE")
    )
    # The name the file had when it was uploaded. Display only: the file on
    # disk is named by id, so a hostile name can never become a path.
    filename: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    # SHA-256 of the file as 64 lowercase hex characters: its fingerprint.
    sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(Text, server_default=text("'uploaded'"))
    error: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int | None]
    # Pages with any extractable text. 0 of 12 usually means a scanned PDF.
    pages_with_text: Mapped[int | None]
    # True when the file was damaged and PyMuPDF had to repair it to read it.
    repaired: Mapped[bool] = mapped_column(server_default=false())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.statement_timestamp(),
    )


class DocumentPage(Base):
    """The text of one page of a document, as extracted.

    Pages are derived data: a reprocess deletes and rewrites all of a
    document's pages in one transaction, so they carry no timestamps of their
    own. page_number counts from 1, as a reader would.
    """

    __tablename__ = "document_pages"
    __table_args__ = (
        UniqueConstraint("document_id", "page_number"),
        CheckConstraint("page_number >= 1", name="page_number_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE")
    )
    page_number: Mapped[int]
    # Named content rather than text, which would shadow SQLAlchemy's text()
    # in this module and is also the name of a Postgres type.
    content: Mapped[str] = mapped_column(Text)


# What full-text search matches against. The English dictionary reduces words
# to their stems, so "processes" matches "process". The heading is weighted A
# and the body B, so a match in a chunk's heading ranks above one in its text.
SEARCH_VECTOR = (
    "setweight(to_tsvector('english', coalesce(heading, '')), 'A') || "
    "setweight(to_tsvector('english', content), 'B')"
)


class DocumentChunk(Base):
    """A passage of a document, the unit of search and later of citation.

    Made by app/chunking.py. Its id is computed there from the document, the
    content and its occurrence, never by the database, so the same text always
    gets the same id and a reprocess never duplicates chunks. The position
    columns locate its exact text in the stored pages.
    """

    __tablename__ = "document_chunks"
    __table_args__ = (
        CheckConstraint("ordinal >= 0", name="ordinal_not_negative"),
        CheckConstraint(
            "page_start >= 1 AND page_end >= page_start", name="page_range"
        ),
        CheckConstraint(
            "char_start >= 0 AND char_end >= 0", name="offsets_not_negative"
        ),
        # GIN is the index type built for full-text search.
        Index(
            "ix_document_chunks_search_vector", "search_vector", postgresql_using="gin"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int]
    page_start: Mapped[int]
    char_start: Mapped[int]
    page_end: Mapped[int]
    char_end: Mapped[int]
    heading: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    # Computed and stored by Postgres itself from heading and content, so it
    # can never drift from the text. Deferred: loaded only when asked for.
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR, Computed(SEARCH_VECTOR, persisted=True), deferred=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
