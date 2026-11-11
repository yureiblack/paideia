"""add practice engine

Revision ID: f746f4eeeed4
Revises: 3799c2eb5d03
Create Date: 2026-11-11 22:35:23.835253

Phase 14: the practice engine. learning_items holds practice items written
from a concept's passages and checked by the backend, with their kind,
content and key, difficulty, the fingerprint of the evidence they came from
and how they were made; learning_item_sources the passages each answer comes
from; attempts every answer and how it was graded; review_schedule each
item's Leitner box and when it is due. generated_artifacts gains a sixth
kind, practice_set: one generation of a concept's items.

Drafted with --autogenerate and reviewed by hand; widening the artifact_type
check constraint was added by hand. Undoing this migration deletes practice
generations first.

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Revision identifiers, used by Alembic to order migrations into a chain.
revision: str = "f746f4eeeed4"
down_revision: str | Sequence[str] | None = "3799c2eb5d03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this migration."""
    op.drop_constraint(
        op.f("ck_generated_artifacts_artifact_type"), "generated_artifacts"
    )
    op.create_check_constraint(
        op.f("ck_generated_artifacts_artifact_type"),
        "generated_artifacts",
        "artifact_type IN ('document_summary', 'environment_summary', "
        "'concept_extraction', 'knowledge_graph', 'learning_roadmap', "
        "'practice_set')",
    )
    op.create_table(
        "learning_items",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("environment_id", sa.Uuid(), nullable=False),
        sa.Column("concept_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("difficulty", sa.Integer(), nullable=False),
        sa.Column("evidence_key", sa.String(length=64), nullable=False),
        sa.Column("model_name", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind IN ('short_answer', 'multiple_choice', 'true_false', 'flashcard')",
            name=op.f("ck_learning_items_kind"),
        ),
        sa.CheckConstraint(
            "difficulty BETWEEN 1 AND 3", name=op.f("ck_learning_items_difficulty")
        ),
        sa.ForeignKeyConstraint(
            ["concept_id"],
            ["concepts.id"],
            name=op.f("fk_learning_items_concept_id_concepts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["environment_id"],
            ["environments.id"],
            name=op.f("fk_learning_items_environment_id_environments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("learning_items_pkey")),
    )
    op.create_index(
        op.f("ix_learning_items_concept_id"),
        "learning_items",
        ["concept_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_learning_items_environment_id"),
        "learning_items",
        ["environment_id"],
        unique=False,
    )
    op.create_table(
        "attempts",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("response", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("correct", sa.Boolean(), nullable=False),
        sa.Column("graded_by", sa.Text(), nullable=False),
        sa.Column("seconds", sa.Float(), nullable=True),
        sa.CheckConstraint(
            "graded_by IN ('key', 'learner')", name=op.f("ck_attempts_graded_by")
        ),
        sa.CheckConstraint(
            "seconds IS NULL OR seconds >= 0", name=op.f("ck_attempts_seconds")
        ),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["learning_items.id"],
            name=op.f("fk_attempts_item_id_learning_items"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("attempts_pkey")),
    )
    op.create_index(op.f("ix_attempts_item_id"), "attempts", ["item_id"], unique=False)
    op.create_table(
        "learning_item_sources",
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["document_chunks.id"],
            name=op.f("fk_learning_item_sources_chunk_id_document_chunks"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_learning_item_sources_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["learning_items.id"],
            name=op.f("fk_learning_item_sources_item_id_learning_items"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "item_id", "chunk_id", name=op.f("learning_item_sources_pkey")
        ),
    )
    op.create_index(
        op.f("ix_learning_item_sources_chunk_id"),
        "learning_item_sources",
        ["chunk_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_learning_item_sources_document_id"),
        "learning_item_sources",
        ["document_id"],
        unique=False,
    )
    op.create_table(
        "review_schedule",
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("box", sa.Integer(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("box BETWEEN 0 AND 5", name=op.f("ck_review_schedule_box")),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["learning_items.id"],
            name=op.f("fk_review_schedule_item_id_learning_items"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("item_id", name=op.f("review_schedule_pkey")),
    )
    op.create_index(
        op.f("ix_review_schedule_due_at"), "review_schedule", ["due_at"], unique=False
    )


def downgrade() -> None:
    """Undo this migration."""
    op.drop_index(op.f("ix_review_schedule_due_at"), table_name="review_schedule")
    op.drop_table("review_schedule")
    op.drop_index(
        op.f("ix_learning_item_sources_document_id"), table_name="learning_item_sources"
    )
    op.drop_index(
        op.f("ix_learning_item_sources_chunk_id"), table_name="learning_item_sources"
    )
    op.drop_table("learning_item_sources")
    op.drop_index(op.f("ix_attempts_item_id"), table_name="attempts")
    op.drop_table("attempts")
    op.drop_index(op.f("ix_learning_items_environment_id"), table_name="learning_items")
    op.drop_index(op.f("ix_learning_items_concept_id"), table_name="learning_items")
    op.drop_table("learning_items")
    op.execute("DELETE FROM generated_artifacts WHERE artifact_type = 'practice_set'")
    op.drop_constraint(
        op.f("ck_generated_artifacts_artifact_type"), "generated_artifacts"
    )
    op.create_check_constraint(
        op.f("ck_generated_artifacts_artifact_type"),
        "generated_artifacts",
        "artifact_type IN ('document_summary', 'environment_summary', "
        "'concept_extraction', 'knowledge_graph', 'learning_roadmap')",
    )
