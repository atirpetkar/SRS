"""add idempotency support table

Revision ID: fc2036340bcb
Revises: 91ecd4334c59
Create Date: 2025-09-03 05:53:55.150049

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'fc2036340bcb'
down_revision: Union[str, Sequence[str], None] = '91ecd4334c59'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create idempotency keys table
    op.create_table(
        'idempotency_keys',
        sa.Column('key', sa.String(255), primary_key=True),
        sa.Column('endpoint', sa.String(100), nullable=False),
        sa.Column('org_id', postgresql.UUID(), nullable=False),
        sa.Column('user_id', postgresql.UUID(), nullable=False), 
        sa.Column('response_data', sa.JSON, nullable=False),
        sa.Column('status_code', sa.Integer, nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('expires_at', sa.TIMESTAMP(timezone=True), nullable=False),
    )
    
    # Create index for efficient cleanup
    op.create_index('idx_idempotency_keys_expires_at', 'idempotency_keys', ['expires_at'])
    
    # Create composite index for efficient lookups
    op.create_index('idx_idempotency_keys_org_user', 'idempotency_keys', ['org_id', 'user_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('idempotency_keys')
