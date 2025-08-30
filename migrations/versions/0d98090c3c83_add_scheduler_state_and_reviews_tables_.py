"""Add scheduler_state and reviews tables for Step 4

Revision ID: 0d98090c3c83
Revises: e993aae79d58
Create Date: 2025-08-30 18:44:09.277752

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0d98090c3c83'
down_revision: Union[str, Sequence[str], None] = 'e993aae79d58'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create scheduler_state table
    op.create_table(
        'scheduler_state',
        sa.Column('user_id', sa.dialects.postgresql.UUID(), nullable=False),
        sa.Column('item_id', sa.dialects.postgresql.UUID(), nullable=False),
        sa.Column('stability', sa.Float(), nullable=False),
        sa.Column('difficulty', sa.Float(), nullable=False),
        sa.Column('due_at', sa.dialects.postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('last_interval', sa.Integer(), nullable=False, default=0),
        sa.Column('reps', sa.Integer(), nullable=False, default=0),
        sa.Column('lapses', sa.Integer(), nullable=False, default=0),
        sa.Column('last_reviewed_at', sa.dialects.postgresql.TIMESTAMP(timezone=True)),
        sa.Column('scheduler_name', sa.String(50), nullable=False, default='fsrs_v6'),
        sa.Column('version', sa.Integer(), nullable=False, default=1),
        sa.PrimaryKeyConstraint('user_id', 'item_id'),
        sa.ForeignKeyConstraint(['item_id'], ['items.id']),
    )

    # Create indexes for scheduler_state
    op.create_index('idx_scheduler_state_due_at', 'scheduler_state', ['due_at'])
    op.create_index('idx_scheduler_state_user_due', 'scheduler_state', ['user_id', 'due_at'])

    # Create reviews table
    op.create_table(
        'reviews',
        sa.Column('id', sa.dialects.postgresql.UUID(), primary_key=True, default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', sa.dialects.postgresql.UUID(), nullable=False),
        sa.Column('item_id', sa.dialects.postgresql.UUID(), nullable=False),
        sa.Column('ts', sa.dialects.postgresql.TIMESTAMP(timezone=True), nullable=False, default=sa.func.now()),
        sa.Column('mode', sa.String(20), nullable=False),  # review, drill, mock
        sa.Column('response', sa.dialects.postgresql.JSON(), nullable=False),
        sa.Column('correct', sa.Boolean()),
        sa.Column('latency_ms', sa.Integer()),
        sa.Column('latency_bucket', sa.SmallInteger()),
        sa.Column('ease', sa.Integer(), nullable=False),  # 1-4 FSRS rating
        sa.ForeignKeyConstraint(['item_id'], ['items.id']),
    )

    # Create indexes for reviews
    op.create_index('idx_reviews_user_ts', 'reviews', ['user_id', 'ts'])
    op.create_index('idx_reviews_user_item', 'reviews', ['user_id', 'item_id'])
    op.create_index('idx_reviews_ts', 'reviews', ['ts'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('reviews')
    op.drop_table('scheduler_state')
