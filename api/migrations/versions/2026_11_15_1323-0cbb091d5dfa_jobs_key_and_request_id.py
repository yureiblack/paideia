"""jobs key and request id

Revision ID: 0cbb091d5dfa
Revises: 10c2a3abdfcd
Create Date: 2026-11-15 13:23:37.205275

Phase 21: reliability. key fingerprints what a job does, its kind and its
steps; a partial unique index allows one queued or running job per
environment and key, so the same work is never queued twice. request_id
records the request that queued a job, for following it through the logs.
Jobs from before this migration have neither; they never conflict.

Drafted with --autogenerate and reviewed by hand.

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Revision identifiers, used by Alembic to order migrations into a chain.
revision: str = "0cbb091d5dfa"
down_revision: str | Sequence[str] | None = "10c2a3abdfcd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this migration."""
    op.add_column("jobs", sa.Column("key", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("request_id", sa.Text(), nullable=True))
    op.create_index(
        "uq_jobs_active_key",
        "jobs",
        ["environment_id", "key"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )


def downgrade() -> None:
    """Undo this migration."""
    op.drop_index(
        "uq_jobs_active_key",
        table_name="jobs",
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )
    op.drop_column("jobs", "request_id")
    op.drop_column("jobs", "key")
