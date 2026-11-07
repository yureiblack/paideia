"""add chunk embeddings

Revision ID: 839239e5f6ac
Revises: e249ce27fc36
Create Date: 2026-11-07 19:45:42.105649

Phase 05: semantic search. Switches on pgvector in this database, which Phase
01 left for "an Alembic migration", and gives every chunk an embedding column
of 384 numbers, the size BAAI/bge-small-en-v1.5 produces, plus the name of the
model that made it. Both stay empty until processing computes them.

Drafted with --autogenerate from app/models.py, then reviewed by hand: the
extension, and the import for the vector type, are not things autogenerate
writes. The size is written out as 384 rather than read from settings, so this
migration means the same thing whatever the settings say later.

The HNSW index makes nearest-neighbour search by cosine distance fast.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

# Revision identifiers, used by Alembic to order migrations into a chain.
revision: str = "839239e5f6ac"
down_revision: str | Sequence[str] | None = "e249ce27fc36"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this migration."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column(
        "document_chunks",
        sa.Column("embedding", Vector(384), nullable=True),
    )
    op.add_column(
        "document_chunks", sa.Column("embedding_model", sa.Text(), nullable=True)
    )
    op.create_index(
        "ix_document_chunks_embedding",
        "document_chunks",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    """Undo this migration."""
    op.drop_index(
        "ix_document_chunks_embedding",
        table_name="document_chunks",
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.drop_column("document_chunks", "embedding_model")
    op.drop_column("document_chunks", "embedding")
    op.execute("DROP EXTENSION IF EXISTS vector")
