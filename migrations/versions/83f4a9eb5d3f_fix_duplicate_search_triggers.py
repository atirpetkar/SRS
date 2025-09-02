"""fix duplicate search triggers

Revision ID: 83f4a9eb5d3f
Revises: 22ab0a4a5340
Create Date: 2025-09-02 10:05:09.699678

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "83f4a9eb5d3f"
down_revision: Union[str, Sequence[str], None] = "22ab0a4a5340"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fix duplicate search triggers by dropping all and recreating once."""
    # Drop all instances of the trigger
    op.execute("DROP TRIGGER IF EXISTS items_search_document_trigger ON items;")

    # Recreate the trigger once
    op.execute(
        """
        CREATE TRIGGER items_search_document_trigger
            BEFORE INSERT OR UPDATE OF type, payload, tags ON items
            FOR EACH ROW EXECUTE FUNCTION items_update_search_document();
    """
    )


def downgrade() -> None:
    """Downgrade - drop the trigger."""
    op.execute("DROP TRIGGER IF EXISTS items_search_document_trigger ON items;")
