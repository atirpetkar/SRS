"""fix quiz user_id type inconsistency - convert string to uuid

This migration converts quiz.user_id and result.user_id from VARCHAR to UUID type.
It uses a deterministic UUID5 conversion to maintain data integrity.

Revision ID: 91ecd4334c59
Revises: 12ff5e1154c0
Create Date: 2025-09-03 05:28:41.309258

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '91ecd4334c59'
down_revision: Union[str, Sequence[str], None] = '12ff5e1154c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Enable uuid-ossp extension if not already enabled
    op.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")
    
    # Add temporary UUID columns
    op.add_column('quizzes', sa.Column('user_uuid_temp', postgresql.UUID(), nullable=True))
    op.add_column('results', sa.Column('user_uuid_temp', postgresql.UUID(), nullable=True))
    
    # Convert existing string user_ids to UUIDs using deterministic uuid5 conversion
    # Using DNS namespace for consistency with existing codebase pattern
    op.execute("""
        UPDATE quizzes 
        SET user_uuid_temp = uuid_generate_v5(
            '6ba7b810-9dad-11d1-80b4-00c04fd430c8'::uuid, 
            user_id
        ) 
        WHERE user_id IS NOT NULL
    """)
    
    op.execute("""
        UPDATE results 
        SET user_uuid_temp = uuid_generate_v5(
            '6ba7b810-9dad-11d1-80b4-00c04fd430c8'::uuid, 
            user_id
        ) 
        WHERE user_id IS NOT NULL
    """)
    
    # Drop old columns and rename new ones
    op.drop_column('quizzes', 'user_id')
    op.drop_column('results', 'user_id')
    
    op.alter_column('quizzes', 'user_uuid_temp', new_column_name='user_id')
    op.alter_column('results', 'user_uuid_temp', new_column_name='user_id')
    
    # Make the columns non-nullable
    op.alter_column('quizzes', 'user_id', nullable=False)
    op.alter_column('results', 'user_id', nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    # Add temporary string columns
    op.add_column('quizzes', sa.Column('user_id_temp', sa.String(255), nullable=True))
    op.add_column('results', sa.Column('user_id_temp', sa.String(255), nullable=True))
    
    # Convert UUIDs back to original string format (this is lossy!)
    # We'll use a simple conversion pattern for downgrade
    op.execute("""
        UPDATE quizzes 
        SET user_id_temp = 'user_' || replace(user_id::text, '-', '')
        WHERE user_id IS NOT NULL
    """)
    
    op.execute("""
        UPDATE results 
        SET user_id_temp = 'user_' || replace(user_id::text, '-', '')
        WHERE user_id IS NOT NULL
    """)
    
    # Drop UUID columns and rename string ones
    op.drop_column('quizzes', 'user_id')
    op.drop_column('results', 'user_id') 
    
    op.alter_column('quizzes', 'user_id_temp', new_column_name='user_id')
    op.alter_column('results', 'user_id_temp', new_column_name='user_id')
    
    # Make the columns non-nullable
    op.alter_column('quizzes', 'user_id', nullable=False)
    op.alter_column('results', 'user_id', nullable=False)
