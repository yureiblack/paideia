"""add background jobs

Revision ID: 10c2a3abdfcd
Revises: 2c164c68b8e3
Create Date: 2026-11-14 15:06:08.187395

Phase 18: background processing. jobs holds the work the worker process
does outside any request: its lane (read or model), the steps it runs,
status, progress, error, attempts and when it may run again. Postgres is
the queue's truth; Redis only wakes the worker. material_updates may now be
cancelled, with the job carrying it out.

Drafted with --autogenerate and reviewed by hand; widening the update
status check was added by hand.

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Revision identifiers, used by Alembic to order migrations into a chain.
revision: str = "10c2a3abdfcd"
down_revision: str | Sequence[str] | None = "2c164c68b8e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this migration."""
    op.drop_constraint(op.f("ck_material_updates_status"), "material_updates")
    op.create_check_constraint(
        op.f("ck_material_updates_status"),
        "material_updates",
        "status IN ('running', 'done', 'failed', 'cancelled')",
    )
    op.create_table(
        "jobs",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("environment_id", sa.Uuid(), nullable=False),
        sa.Column("update_id", sa.Uuid(), nullable=True),
        sa.Column("after_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("lane", sa.Text(), nullable=False),
        sa.Column("steps", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "progress", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("step", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "attempts", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "max_attempts", sa.Integer(), server_default=sa.text("3"), nullable=False
        ),
        sa.Column(
            "cancel_requested",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("worker", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("not_before", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("lane IN ('read', 'model')", name=op.f("ck_jobs_lane")),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name=op.f("ck_jobs_status"),
        ),
        sa.CheckConstraint("attempts >= 0", name=op.f("ck_jobs_attempts")),
        sa.CheckConstraint("progress BETWEEN 0 AND 100", name=op.f("ck_jobs_progress")),
        sa.ForeignKeyConstraint(
            ["after_id"],
            ["jobs.id"],
            name=op.f("fk_jobs_after_id_jobs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["environment_id"],
            ["environments.id"],
            name=op.f("fk_jobs_environment_id_environments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["update_id"],
            ["material_updates.id"],
            name=op.f("fk_jobs_update_id_material_updates"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("jobs_pkey")),
    )
    op.create_index(
        "ix_jobs_claim", "jobs", ["lane", "status", "created_at"], unique=False
    )
    op.create_index(
        op.f("ix_jobs_environment_id"), "jobs", ["environment_id"], unique=False
    )


def downgrade() -> None:
    """Undo this migration."""
    op.drop_index(op.f("ix_jobs_environment_id"), table_name="jobs")
    op.drop_index("ix_jobs_claim", table_name="jobs")
    op.drop_table("jobs")
    op.execute(
        "UPDATE material_updates SET status = 'failed' WHERE status = 'cancelled'"
    )
    op.drop_constraint(op.f("ck_material_updates_status"), "material_updates")
    op.create_check_constraint(
        op.f("ck_material_updates_status"),
        "material_updates",
        "status IN ('running', 'done', 'failed')",
    )
