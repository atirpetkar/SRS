"""add_item_embeddings_table_for_step_8

Revision ID: 22ab0a4a5340
Revises: 2865d07e2745
Create Date: 2025-09-01 12:29:52.654511

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "22ab0a4a5340"
down_revision: str | Sequence[str] | None = "2865d07e2745"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create pgvector extension if it doesn't exist
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # Create item_embeddings table
    # Note: Using raw SQL for vector column type as SQLAlchemy doesn't have native pgvector support
    op.execute(
        """
        CREATE TABLE item_embeddings (
            item_id UUID NOT NULL REFERENCES items(id) ON DELETE CASCADE,
            embedding vector(768) NOT NULL,
            model_version TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            metadata JSONB NOT NULL DEFAULT '{}',
            PRIMARY KEY (item_id)
        );
    """
    )

    # Create HNSW index for vector similarity search with 2024-2025 best practices
    # Using m=16, ef_construction=200 based on latest research
    op.execute(
        """
        CREATE INDEX item_embeddings_hnsw
        ON item_embeddings USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 200);
    """
    )

    # Create index on model_version for efficient filtering
    op.create_index(
        "idx_item_embeddings_model_version", "item_embeddings", ["model_version"]
    )

    # Create index on created_at for chronological queries
    op.create_index("idx_item_embeddings_created_at", "item_embeddings", ["created_at"])


def downgrade() -> None:
    """Downgrade schema."""
    # Drop indexes first
    op.drop_index("idx_item_embeddings_created_at", table_name="item_embeddings")
    op.drop_index("idx_item_embeddings_model_version", table_name="item_embeddings")
    op.execute("DROP INDEX IF EXISTS item_embeddings_hnsw;")

    # Drop the item_embeddings table
    op.drop_table("item_embeddings")

    # Note: We don't drop the vector extension in case other tables use it
