"""add knowledge graph

Revision ID: 373e52355d3c
Revises: 6ee18d185f99
Create Date: 2026-11-10 18:44:35.352739

Phase 12: the knowledge graph. relationship_decisions remembers what the
model decided about each candidate pair of concepts; concept_relationships
holds the graph's edges, at most one per pair in either direction (a unique
index on the pair in sorted order), with checks on type, confidence and
self-edges; relationship_evidence holds the passages showing each edge.
generated_artifacts gains a fourth kind, knowledge_graph.

Drafted with --autogenerate and reviewed by hand; widening the artifact_type
check constraint was added by hand. Undoing this migration deletes graph
builds first.

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Revision identifiers, used by Alembic to order migrations into a chain.
revision: str = "373e52355d3c"
down_revision: str | Sequence[str] | None = "6ee18d185f99"
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
        "'concept_extraction', 'knowledge_graph')",
    )
    op.create_table(
        "concept_relationships",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("environment_id", sa.Uuid(), nullable=False),
        sa.Column("source_concept_id", sa.Uuid(), nullable=False),
        sa.Column("target_concept_id", sa.Uuid(), nullable=False),
        sa.Column("relationship_type", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "relationship_type IN ('PREREQUISITE_OF', 'RELATED_TO', 'PART_OF')",
            name=op.f("ck_concept_relationships_relationship_type"),
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name=op.f("ck_concept_relationships_confidence"),
        ),
        sa.CheckConstraint(
            "source_concept_id <> target_concept_id",
            name=op.f("ck_concept_relationships_no_self_edge"),
        ),
        sa.ForeignKeyConstraint(
            ["environment_id"],
            ["environments.id"],
            name=op.f("fk_concept_relationships_environment_id_environments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_concept_id"],
            ["concepts.id"],
            name=op.f("fk_concept_relationships_source_concept_id_concepts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_concept_id"],
            ["concepts.id"],
            name=op.f("fk_concept_relationships_target_concept_id_concepts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("concept_relationships_pkey")),
    )
    op.create_index(
        op.f("ix_concept_relationships_environment_id"),
        "concept_relationships",
        ["environment_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_concept_relationships_source_concept_id"),
        "concept_relationships",
        ["source_concept_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_concept_relationships_target_concept_id"),
        "concept_relationships",
        ["target_concept_id"],
        unique=False,
    )
    op.create_index(
        "uq_concept_relationships_pair",
        "concept_relationships",
        [
            sa.literal_column("least(source_concept_id, target_concept_id)"),
            sa.literal_column("greatest(source_concept_id, target_concept_id)"),
        ],
        unique=True,
    )
    op.create_table(
        "relationship_decisions",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("environment_id", sa.Uuid(), nullable=False),
        sa.Column("pair_key", sa.String(length=64), nullable=False),
        sa.Column("concept_a_id", sa.Uuid(), nullable=False),
        sa.Column("concept_b_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("model_name", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "decision IN ('a_before_b', 'b_before_a', 'a_part_of_b', 'b_part_of_a', 'related', 'none')",
            name=op.f("ck_relationship_decisions_decision"),
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name=op.f("ck_relationship_decisions_confidence"),
        ),
        sa.ForeignKeyConstraint(
            ["concept_a_id"],
            ["concepts.id"],
            name=op.f("fk_relationship_decisions_concept_a_id_concepts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["concept_b_id"],
            ["concepts.id"],
            name=op.f("fk_relationship_decisions_concept_b_id_concepts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["environment_id"],
            ["environments.id"],
            name=op.f("fk_relationship_decisions_environment_id_environments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("relationship_decisions_pkey")),
        sa.UniqueConstraint(
            "environment_id",
            "pair_key",
            "model_name",
            "prompt_version",
            name=op.f(
                "uq_relationship_decisions_environment_id_pair_key_model_name_prompt_version"
            ),
        ),
    )
    op.create_index(
        op.f("ix_relationship_decisions_concept_a_id"),
        "relationship_decisions",
        ["concept_a_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_relationship_decisions_concept_b_id"),
        "relationship_decisions",
        ["concept_b_id"],
        unique=False,
    )
    op.create_table(
        "relationship_evidence",
        sa.Column("relationship_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["document_chunks.id"],
            name=op.f("fk_relationship_evidence_chunk_id_document_chunks"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_relationship_evidence_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["relationship_id"],
            ["concept_relationships.id"],
            name=op.f("fk_relationship_evidence_relationship_id_concept_relationships"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "relationship_id", "chunk_id", name=op.f("relationship_evidence_pkey")
        ),
    )
    op.create_index(
        op.f("ix_relationship_evidence_chunk_id"),
        "relationship_evidence",
        ["chunk_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_relationship_evidence_document_id"),
        "relationship_evidence",
        ["document_id"],
        unique=False,
    )


def downgrade() -> None:
    """Undo this migration."""
    op.drop_index(
        op.f("ix_relationship_evidence_document_id"), table_name="relationship_evidence"
    )
    op.drop_index(
        op.f("ix_relationship_evidence_chunk_id"), table_name="relationship_evidence"
    )
    op.drop_table("relationship_evidence")
    op.drop_index(
        op.f("ix_relationship_decisions_concept_b_id"),
        table_name="relationship_decisions",
    )
    op.drop_index(
        op.f("ix_relationship_decisions_concept_a_id"),
        table_name="relationship_decisions",
    )
    op.drop_table("relationship_decisions")
    op.drop_index("uq_concept_relationships_pair", table_name="concept_relationships")
    op.drop_index(
        op.f("ix_concept_relationships_target_concept_id"),
        table_name="concept_relationships",
    )
    op.drop_index(
        op.f("ix_concept_relationships_source_concept_id"),
        table_name="concept_relationships",
    )
    op.drop_index(
        op.f("ix_concept_relationships_environment_id"),
        table_name="concept_relationships",
    )
    op.drop_table("concept_relationships")
    op.execute(
        "DELETE FROM generated_artifacts WHERE artifact_type = 'knowledge_graph'"
    )
    op.drop_constraint(
        op.f("ck_generated_artifacts_artifact_type"), "generated_artifacts"
    )
    op.create_check_constraint(
        op.f("ck_generated_artifacts_artifact_type"),
        "generated_artifacts",
        "artifact_type IN "
        "('document_summary', 'environment_summary', 'concept_extraction')",
    )
