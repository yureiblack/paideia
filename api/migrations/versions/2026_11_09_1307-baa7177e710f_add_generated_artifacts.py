"""add generated artifacts

Revision ID: baa7177e710f
Revises: 839239e5f6ac
Create Date: 2026-11-09 13:07:55.630617

Phase 09: stored summaries. One table for everything the language model
writes, starting with document summaries. A unique key on (document, type,
source version, model, prompt version) lets the database itself refuse to
write the same summary twice; anything new is a new row, so earlier
summaries are kept. Deleting a document or an environment deletes what was
written from it.

Drafted with --autogenerate from app/models.py and reviewed by hand.

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Revision identifiers, used by Alembic to order migrations into a chain.
revision: str = "baa7177e710f"
down_revision: str | Sequence[str] | None = "839239e5f6ac"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this migration."""
    op.create_table(
        "generated_artifacts",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("environment_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("artifact_type", sa.Text(), nullable=False),
        sa.Column("source_version", sa.String(length=64), nullable=False),
        sa.Column(
            "status", sa.Text(), server_default=sa.text("'pending'"), nullable=False
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("model_name", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
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
            "artifact_type IN ('document_summary')",
            name=op.f("ck_generated_artifacts_artifact_type"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'generating', 'ready', 'failed')",
            name=op.f("ck_generated_artifacts_status"),
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_generated_artifacts_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["environment_id"],
            ["environments.id"],
            name=op.f("fk_generated_artifacts_environment_id_environments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("generated_artifacts_pkey")),
        sa.UniqueConstraint(
            "document_id",
            "artifact_type",
            "source_version",
            "model_name",
            "prompt_version",
            name="uq_generated_artifacts_key",
        ),
    )
    op.create_index(
        op.f("ix_generated_artifacts_environment_id"),
        "generated_artifacts",
        ["environment_id"],
        unique=False,
    )


def downgrade() -> None:
    """Undo this migration."""
    op.drop_index(
        op.f("ix_generated_artifacts_environment_id"), table_name="generated_artifacts"
    )
    op.drop_table("generated_artifacts")
