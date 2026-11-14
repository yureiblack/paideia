"""add material updates

Revision ID: 2c164c68b8e3
Revises: f746f4eeeed4
Create Date: 2026-11-14 11:32:32.290702

Phase 17: incremental updates. material_updates records every change to an
environment's material (a document added, a new version, a reprocess, a
deletion) with its steps, so the page can follow it, and what it changed.
document_chunks.content_hash gets an index: a passage's embedding is looked
up by its text in every document before any is computed. Relationship
decisions no longer go with their concepts (their links are set to null):
a document deleted and added again finds every decision about its pairs.

Drafted with --autogenerate and reviewed by hand.

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Revision identifiers, used by Alembic to order migrations into a chain.
revision: str = "2c164c68b8e3"
down_revision: str | Sequence[str] | None = "f746f4eeeed4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this migration."""
    # Decisions about pairs outlive the concepts they name: their key is
    # the names and passage text, so a document deleted and added again
    # finds them all.
    for side in ("a", "b"):
        op.alter_column("relationship_decisions", f"concept_{side}_id", nullable=True)
        op.drop_constraint(
            op.f(f"fk_relationship_decisions_concept_{side}_id_concepts"),
            "relationship_decisions",
            type_="foreignkey",
        )
        op.create_foreign_key(
            op.f(f"fk_relationship_decisions_concept_{side}_id_concepts"),
            "relationship_decisions",
            "concepts",
            [f"concept_{side}_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_table(
        "material_updates",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("environment_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "steps",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "before",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("report", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind IN ('added', 'new_version', 'reprocessed', 'deleted')",
            name=op.f("ck_material_updates_kind"),
        ),
        sa.CheckConstraint(
            "status IN ('running', 'done', 'failed')",
            name=op.f("ck_material_updates_status"),
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_material_updates_document_id_documents"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["environment_id"],
            ["environments.id"],
            name=op.f("fk_material_updates_environment_id_environments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("material_updates_pkey")),
    )
    op.create_index(
        op.f("ix_material_updates_document_id"),
        "material_updates",
        ["document_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_material_updates_environment_id"),
        "material_updates",
        ["environment_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_chunks_content_hash"),
        "document_chunks",
        ["content_hash"],
        unique=False,
    )


def downgrade() -> None:
    """Undo this migration. Decisions whose concepts are gone go too."""
    op.execute(
        "DELETE FROM relationship_decisions "
        "WHERE concept_a_id IS NULL OR concept_b_id IS NULL"
    )
    for side in ("a", "b"):
        op.drop_constraint(
            op.f(f"fk_relationship_decisions_concept_{side}_id_concepts"),
            "relationship_decisions",
            type_="foreignkey",
        )
        op.create_foreign_key(
            op.f(f"fk_relationship_decisions_concept_{side}_id_concepts"),
            "relationship_decisions",
            "concepts",
            [f"concept_{side}_id"],
            ["id"],
            ondelete="CASCADE",
        )
        op.alter_column("relationship_decisions", f"concept_{side}_id", nullable=False)
    op.drop_index(op.f("ix_document_chunks_content_hash"), table_name="document_chunks")
    op.drop_index(
        op.f("ix_material_updates_environment_id"), table_name="material_updates"
    )
    op.drop_index(
        op.f("ix_material_updates_document_id"), table_name="material_updates"
    )
    op.drop_table("material_updates")
