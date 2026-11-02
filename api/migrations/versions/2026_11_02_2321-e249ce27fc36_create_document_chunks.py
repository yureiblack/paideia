"""create document chunks

Revision ID: e249ce27fc36
Revises: 890e8bee0d58
Create Date: 2026-11-02 23:21:18.289594

Phase 04: document_chunks holds the passages app/chunking.py cuts each
document into, the unit of search now and of embeddings and citations later.
Each row's id comes from the chunker, not the database, so the same text
always gets the same id.

Drafted with --autogenerate from app/models.py, then reviewed by hand.

search_vector is a generated column: Postgres computes and stores it from the
heading and content on every insert or update, so it can never drift from the
text. The GIN index is what makes full-text queries on it fast. Chunks are
deleted with their document through the foreign key.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Revision identifiers, used by Alembic to order migrations into a chain.
revision: str = "e249ce27fc36"
down_revision: str | Sequence[str] | None = "890e8bee0d58"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this migration."""
    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("page_end", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("heading", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(
                "setweight(to_tsvector('english', coalesce(heading, '')), 'A') || setweight(to_tsvector('english', content), 'B')",
                persisted=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_start >= 0 AND char_end >= 0",
            name=op.f("ck_document_chunks_offsets_not_negative"),
        ),
        sa.CheckConstraint(
            "ordinal >= 0", name=op.f("ck_document_chunks_ordinal_not_negative")
        ),
        sa.CheckConstraint(
            "page_start >= 1 AND page_end >= page_start",
            name=op.f("ck_document_chunks_page_range"),
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_document_chunks_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("document_chunks_pkey")),
    )
    op.create_index(
        op.f("ix_document_chunks_document_id"),
        "document_chunks",
        ["document_id"],
        unique=False,
    )
    op.create_index(
        "ix_document_chunks_search_vector",
        "document_chunks",
        ["search_vector"],
        unique=False,
        postgresql_using="gin",
    )


def downgrade() -> None:
    """Undo this migration."""
    op.drop_index(
        "ix_document_chunks_search_vector",
        table_name="document_chunks",
        postgresql_using="gin",
    )
    op.drop_index(op.f("ix_document_chunks_document_id"), table_name="document_chunks")
    op.drop_table("document_chunks")
