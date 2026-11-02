"""create documents and document pages

Revision ID: 890e8bee0d58
Revises: 0a84e5243328
Create Date: 2026-11-02 21:30:28.733521

Phase 03: uploaded PDFs. documents holds one row per uploaded file: its
metadata, fingerprint and processing status. document_pages holds the text of
each page. The PDF itself stays on disk, never in the database.

Drafted with --autogenerate from app/models.py, then reviewed by hand.

Both foreign keys cascade on delete, so deleting an environment removes its
documents, and deleting a document removes its pages, in the database itself.
No extra indexes are needed: each unique constraint builds an index whose
first column is the foreign key, which already serves "all documents of this
environment" and "all pages of this document".
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Revision identifiers, used by Alembic to order migrations into a chain.
revision: str = "890e8bee0d58"
down_revision: str | Sequence[str] | None = "0a84e5243328"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this migration."""
    op.create_table(
        "documents",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("environment_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "status", sa.Text(), server_default=sa.text("'uploaded'"), nullable=False
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("pages_with_text", sa.Integer(), nullable=True),
        sa.Column(
            "repaired", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('uploaded', 'processing', 'ready', 'failed')",
            name=op.f("ck_documents_status"),
        ),
        sa.ForeignKeyConstraint(
            ["environment_id"],
            ["environments.id"],
            name=op.f("fk_documents_environment_id_environments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("documents_pkey")),
        sa.UniqueConstraint(
            "environment_id", "sha256", name=op.f("uq_documents_environment_id_sha256")
        ),
    )
    op.create_table(
        "document_pages",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "page_number >= 1", name=op.f("ck_document_pages_page_number_positive")
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_document_pages_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("document_pages_pkey")),
        sa.UniqueConstraint(
            "document_id",
            "page_number",
            name=op.f("uq_document_pages_document_id_page_number"),
        ),
    )


def downgrade() -> None:
    """Undo this migration."""
    op.drop_table("document_pages")
    op.drop_table("documents")
