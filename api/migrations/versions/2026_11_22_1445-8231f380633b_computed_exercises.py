"""computed exercises

Revision ID: 8231f380633b
Revises: 07c21bc337f6
Create Date: 2026-11-22 14:45:26.950490

Phase 27: computed exercises. A learning item may now be an exercise, whose
numbers the backend writes afresh for every review and marks itself
(decision record 27). Written by hand: autogenerate does not compare check
constraints.

"""

from collections.abc import Sequence

from alembic import op

# Revision identifiers, used by Alembic to order migrations into a chain.
revision: str = "8231f380633b"
down_revision: str | Sequence[str] | None = "07c21bc337f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this migration."""
    op.drop_constraint(op.f("ck_learning_items_kind"), "learning_items", type_="check")
    op.create_check_constraint(
        op.f("ck_learning_items_kind"),
        "learning_items",
        "kind IN ('short_answer', 'multiple_choice', 'true_false', 'flashcard', "
        "'exercise')",
    )


def downgrade() -> None:
    """Undo this migration. Exercises go with it, with their answers and
    schedule: the older schema has no such kind."""
    op.execute("DELETE FROM learning_items WHERE kind = 'exercise'")
    op.drop_constraint(op.f("ck_learning_items_kind"), "learning_items", type_="check")
    op.create_check_constraint(
        op.f("ck_learning_items_kind"),
        "learning_items",
        "kind IN ('short_answer', 'multiple_choice', 'true_false', 'flashcard')",
    )
