"""add learning roadmap

Revision ID: 3799c2eb5d03
Revises: 373e52355d3c
Create Date: 2026-11-10 20:48:32.545879

Phase 13: the learning roadmap. Its stages and order are computed from the
concepts and the knowledge graph whenever it is read, so it needs no table
of its own. Only the stage titles the model writes are stored, as a fifth
kind of generated artifact, learning_roadmap.

Written by hand: autogenerate does not see check constraints change.
Undoing this migration deletes the stored titles first.

"""

from collections.abc import Sequence

from alembic import op

# Revision identifiers, used by Alembic to order migrations into a chain.
revision: str = "3799c2eb5d03"
down_revision: str | Sequence[str] | None = "373e52355d3c"
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
        "'concept_extraction', 'knowledge_graph', 'learning_roadmap')",
    )


def downgrade() -> None:
    """Undo this migration."""
    op.execute(
        "DELETE FROM generated_artifacts WHERE artifact_type = 'learning_roadmap'"
    )
    op.drop_constraint(
        op.f("ck_generated_artifacts_artifact_type"), "generated_artifacts"
    )
    op.create_check_constraint(
        op.f("ck_generated_artifacts_artifact_type"),
        "generated_artifacts",
        "artifact_type IN ('document_summary', 'environment_summary', "
        "'concept_extraction', 'knowledge_graph')",
    )
