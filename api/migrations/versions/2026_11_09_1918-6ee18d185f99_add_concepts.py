"""add concepts

Revision ID: 6ee18d185f99
Revises: a73d4eb95ab0
Create Date: 2026-11-09 19:18:24.396045

Phase 11: concept extraction. Three tables, written only by the backend from
validated model output: concepts (one per normalized name per environment),
document_concepts (how each document presents a concept) and
concept_evidence (the passages explaining it, deleted with their chunk).
generated_artifacts gains a third kind, concept_extraction.

Drafted with --autogenerate and reviewed by hand; widening the artifact_type
check constraint was added by hand, as Alembic does not compare check
constraints. Undoing this migration deletes concept extractions first.

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Revision identifiers, used by Alembic to order migrations into a chain.
revision: str = "6ee18d185f99"
down_revision: str | Sequence[str] | None = "a73d4eb95ab0"
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
        "artifact_type IN "
        "('document_summary', 'environment_summary', 'concept_extraction')",
    )
    op.create_table(
        "concepts",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("environment_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("normalized_name", sa.Text(), nullable=False),
        sa.Column("definition", sa.Text(), nullable=False),
        sa.Column(
            "aliases",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
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
        sa.ForeignKeyConstraint(
            ["environment_id"],
            ["environments.id"],
            name=op.f("fk_concepts_environment_id_environments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("concepts_pkey")),
        sa.UniqueConstraint(
            "environment_id",
            "normalized_name",
            name=op.f("uq_concepts_environment_id_normalized_name"),
        ),
    )
    op.create_table(
        "document_concepts",
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("concept_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("definition", sa.Text(), nullable=False),
        sa.Column(
            "aliases",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["concept_id"],
            ["concepts.id"],
            name=op.f("fk_document_concepts_concept_id_concepts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_document_concepts_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "document_id", "concept_id", name=op.f("document_concepts_pkey")
        ),
    )
    op.create_index(
        op.f("ix_document_concepts_concept_id"),
        "document_concepts",
        ["concept_id"],
        unique=False,
    )
    op.create_table(
        "concept_evidence",
        sa.Column("concept_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["document_chunks.id"],
            name=op.f("fk_concept_evidence_chunk_id_document_chunks"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["concept_id"],
            ["concepts.id"],
            name=op.f("fk_concept_evidence_concept_id_concepts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_concept_evidence_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "concept_id", "chunk_id", name=op.f("concept_evidence_pkey")
        ),
    )
    op.create_index(
        op.f("ix_concept_evidence_chunk_id"),
        "concept_evidence",
        ["chunk_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_concept_evidence_document_id"),
        "concept_evidence",
        ["document_id"],
        unique=False,
    )


def downgrade() -> None:
    """Undo this migration."""
    op.drop_index(
        op.f("ix_concept_evidence_document_id"), table_name="concept_evidence"
    )
    op.drop_index(op.f("ix_concept_evidence_chunk_id"), table_name="concept_evidence")
    op.drop_table("concept_evidence")
    op.drop_index(
        op.f("ix_document_concepts_concept_id"), table_name="document_concepts"
    )
    op.drop_table("document_concepts")
    op.drop_table("concepts")
    op.execute(
        "DELETE FROM generated_artifacts WHERE artifact_type = 'concept_extraction'"
    )
    op.drop_constraint(
        op.f("ck_generated_artifacts_artifact_type"), "generated_artifacts"
    )
    op.create_check_constraint(
        op.f("ck_generated_artifacts_artifact_type"),
        "generated_artifacts",
        "artifact_type IN ('document_summary', 'environment_summary')",
    )
