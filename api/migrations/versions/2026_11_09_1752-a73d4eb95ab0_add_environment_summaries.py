"""add environment summaries

Revision ID: a73d4eb95ab0
Revises: baa7177e710f
Create Date: 2026-11-09 17:52:28.357429

Phase 10: environment summaries. generated_artifacts gains a second kind,
environment_summary, which belongs to an environment and no document. The
existing unique key cannot cover such rows, since NULLs are distinct in a
unique constraint, so they get their own: a partial unique index over rows
without a document.

Autogenerate wrote the index; widening the artifact_type check constraint
was added by hand, as Alembic does not compare check constraints. Undoing
this migration deletes environment summaries first, since the narrower
constraint would reject them.

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Revision identifiers, used by Alembic to order migrations into a chain.
revision: str = "a73d4eb95ab0"
down_revision: str | Sequence[str] | None = "baa7177e710f"
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
        "artifact_type IN ('document_summary', 'environment_summary')",
    )
    op.create_index(
        "uq_generated_artifacts_environment_key",
        "generated_artifacts",
        [
            "environment_id",
            "artifact_type",
            "source_version",
            "model_name",
            "prompt_version",
        ],
        unique=True,
        postgresql_where=sa.text("document_id IS NULL"),
    )


def downgrade() -> None:
    """Undo this migration."""
    op.drop_index(
        "uq_generated_artifacts_environment_key",
        table_name="generated_artifacts",
        postgresql_where=sa.text("document_id IS NULL"),
    )
    op.execute(
        "DELETE FROM generated_artifacts WHERE artifact_type = 'environment_summary'"
    )
    op.drop_constraint(
        op.f("ck_generated_artifacts_artifact_type"), "generated_artifacts"
    )
    op.create_check_constraint(
        op.f("ck_generated_artifacts_artifact_type"),
        "generated_artifacts",
        "artifact_type IN ('document_summary')",
    )
