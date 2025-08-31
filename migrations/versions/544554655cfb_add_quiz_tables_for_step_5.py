"""Add quiz tables for Step 5

Revision ID: 544554655cfb
Revises: 0d98090c3c83
Create Date: 2025-08-30 20:32:10.771247

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "544554655cfb"
down_revision: str | Sequence[str] | None = "0d98090c3c83"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create quizzes table
    op.create_table(
        "quizzes",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(),
            primary_key=True,
            default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("org_id", sa.dialects.postgresql.UUID(), nullable=False),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),  # review, drill, mock
        sa.Column(
            "params",
            sa.dialects.postgresql.JSON(),
            nullable=False,
            default=sa.text("{}"),
        ),
        sa.Column(
            "started_at",
            sa.dialects.postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            default=sa.func.now(),
        ),
        sa.Column("finished_at", sa.dialects.postgresql.TIMESTAMP(timezone=True)),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"]),
        sa.CheckConstraint(
            "mode IN ('review', 'drill', 'mock')", name="quiz_mode_check"
        ),
    )

    # Create quiz_items table
    op.create_table(
        "quiz_items",
        sa.Column("quiz_id", sa.dialects.postgresql.UUID(), nullable=False),
        sa.Column("item_id", sa.dialects.postgresql.UUID(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("quiz_id", "item_id"),
        sa.ForeignKeyConstraint(["quiz_id"], ["quizzes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"]),
        sa.UniqueConstraint(
            "quiz_id", "position", name="quiz_items_quiz_position_unique"
        ),
    )

    # Create results table
    op.create_table(
        "results",
        sa.Column("quiz_id", sa.dialects.postgresql.UUID(), nullable=False),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column(
            "breakdown",
            sa.dialects.postgresql.JSON(),
            nullable=False,
            default=sa.text("{}"),
        ),
        sa.PrimaryKeyConstraint("quiz_id", "user_id"),
        sa.ForeignKeyConstraint(["quiz_id"], ["quizzes.id"], ondelete="CASCADE"),
    )

    # Create indexes for performance
    op.create_index("idx_quizzes_org_user", "quizzes", ["org_id", "user_id"])
    op.create_index("idx_quizzes_user_started", "quizzes", ["user_id", "started_at"])
    op.create_index("idx_quiz_items_item", "quiz_items", ["item_id"])
    op.create_index("idx_results_user", "results", ["user_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("results")
    op.drop_table("quiz_items")
    op.drop_table("quizzes")
