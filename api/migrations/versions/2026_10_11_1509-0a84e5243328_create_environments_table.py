"""create environments table

Revision ID: 0a84e5243328
Revises:
Create Date: 2026-10-11 15:09:44.242486

The first table in Paideia. A learning environment is one subject, such as
Operating Systems or Economics, and later owns its documents, concepts, roadmap
and practice. This migration creates only the environment itself.

Written by hand rather than with --autogenerate: no SQLAlchemy model existed to
compare against yet, and writing it out keeps every default explicit.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Revision identifiers, used by Alembic to order migrations into a chain.
revision: str = "0a84e5243328"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the environments table."""
    op.create_table(
        "environments",
        # A UUID rather than 1, 2, 3: ids cannot be guessed from a URL, and
        # they can be generated anywhere without asking the database first.
        # The database fills it in itself, so any insert works without one.
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.Text(), nullable=False),
        # Optional: an environment can exist before anyone describes it.
        sa.Column("description", sa.Text(), nullable=True),
        # "timezone=True" stores timestamptz: an exact instant, displayed in
        # whatever zone the reader asks for, instead of a wall-clock time with
        # no zone attached.
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        # The default only covers the insert. Keeping this current on every
        # update is the SQLAlchemy model's job, added in the next step.
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    """Drop the environments table, and every environment in it."""
    op.drop_table("environments")
