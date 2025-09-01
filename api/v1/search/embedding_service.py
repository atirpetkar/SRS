"""
Embedding computation service for Step 8.

Handles embedding generation, storage, and batch processing for published items.
"""

import asyncio
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from api.config.settings import Settings
from api.v1.core.registries import vectorizer_registry
from api.v1.items.models import Item
from api.v1.items.utils import canonical_text
from api.v1.search.models import ItemEmbedding


class EmbeddingService:
    """
    Service for computing and managing item embeddings.

    Provides methods for generating embeddings, batch processing,
    and maintaining embedding consistency.
    """

    def __init__(self, settings: Settings):
        self.settings = settings

    async def compute_embedding_for_item(
        self, session: AsyncSession, item: Item, force_recompute: bool = False
    ) -> ItemEmbedding:
        """
        Compute and store embedding for a single item.

        Args:
            session: Database session
            item: Item to process
            force_recompute: Whether to recompute existing embeddings

        Returns:
            ItemEmbedding instance
        """
        # Check if embedding already exists
        existing = await session.execute(
            select(ItemEmbedding).where(ItemEmbedding.item_id == item.id)
        )
        existing_embedding = existing.scalar_one_or_none()

        # Get current vectorizer and model version
        vectorizer = vectorizer_registry.get(self.settings.embeddings.value)
        current_model_version = vectorizer.get_model_version()

        # Skip if embedding exists and is current (unless forced)
        if (
            existing_embedding
            and existing_embedding.model_version == current_model_version
            and not force_recompute
        ):
            return existing_embedding

        # Generate canonical text and embedding
        item_text = canonical_text(item.type, item.payload)
        embedding_vector = vectorizer.vectorize(item_text)

        # Create or update embedding
        if existing_embedding:
            # Update existing embedding
            existing_embedding.embedding = embedding_vector
            existing_embedding.model_version = current_model_version
            existing_embedding.meta = {
                "text_length": len(item_text),
                "item_type": item.type,
                "recomputed": True,
            }
            await session.commit()
            await session.refresh(existing_embedding)
            return existing_embedding
        else:
            # Create new embedding
            new_embedding = ItemEmbedding(
                item_id=item.id,
                embedding=embedding_vector,
                model_version=current_model_version,
                meta={
                    "text_length": len(item_text),
                    "item_type": item.type,
                    "initial_computation": True,
                },
            )
            session.add(new_embedding)
            await session.commit()
            await session.refresh(new_embedding)
            return new_embedding

    async def compute_embeddings_for_published_items(
        self,
        session: AsyncSession,
        org_id: UUID | None = None,
        batch_size: int = 100,
        force_recompute: bool = False,
    ) -> dict[str, int]:
        """
        Batch compute embeddings for all published items.

        Args:
            session: Database session
            org_id: Optional organization filter
            batch_size: Number of items to process at once
            force_recompute: Whether to recompute existing embeddings

        Returns:
            Statistics dictionary with processing counts
        """
        stats = {"processed": 0, "created": 0, "updated": 0, "errors": 0}

        # Build query for published items without embeddings (or all if force_recompute)
        base_query = select(Item).where(
            Item.status == "published", Item.deleted_at.is_(None)
        )

        if org_id:
            base_query = base_query.where(Item.org_id == org_id)

        if not force_recompute:
            # Only items without embeddings
            base_query = base_query.outerjoin(ItemEmbedding).where(
                ItemEmbedding.item_id.is_(None)
            )

        # Process in batches
        offset = 0
        while True:
            # Get batch of items
            result = await session.execute(base_query.offset(offset).limit(batch_size))
            items = result.scalars().all()

            if not items:
                break

            # Process each item in the batch
            for item in items:
                try:
                    existing_count = await session.execute(
                        select(func.count(ItemEmbedding.item_id)).where(
                            ItemEmbedding.item_id == item.id
                        )
                    )
                    had_embedding = existing_count.scalar() > 0

                    await self.compute_embedding_for_item(
                        session, item, force_recompute
                    )

                    stats["processed"] += 1
                    if had_embedding:
                        stats["updated"] += 1
                    else:
                        stats["created"] += 1

                except Exception as e:
                    stats["errors"] += 1
                    # Log error but continue processing
                    print(f"Error computing embedding for item {item.id}: {e}")

            offset += batch_size

            # Brief pause to avoid overwhelming the system
            await asyncio.sleep(0.1)

        return stats

    async def detect_duplicates(
        self, session: AsyncSession, item: Item, threshold: float = 0.90
    ) -> list[tuple[Item, float]]:
        """
        Detect potential duplicate items using embedding similarity.

        Args:
            session: Database session
            item: Item to check for duplicates
            threshold: Minimum cosine similarity for duplicate detection

        Returns:
            List of (similar_item, similarity_score) tuples
        """
        # Generate embedding for the item if not already done
        item_text = canonical_text(item.type, item.payload)
        vectorizer = vectorizer_registry.get(self.settings.embeddings.value)
        item_embedding = vectorizer.vectorize(item_text)

        # Find similar items in the same organization

        similarity_expr = text(
            "1 - (item_embeddings.embedding <=> :item_vector)"
        ).params(item_vector=item_embedding)

        query = (
            select(Item, similarity_expr.label("similarity"))
            .select_from(Item.__table__.join(ItemEmbedding.__table__))
            .where(
                Item.org_id == item.org_id,
                Item.id != item.id,  # Exclude the item itself
                Item.deleted_at.is_(None),
                similarity_expr >= threshold,
            )
            .order_by(text("similarity DESC"))
            .limit(10)  # Limit to top 10 most similar
        )

        result = await session.execute(query)
        return [(row[0], float(row[1])) for row in result.all()]

    async def get_embedding_stats(
        self, session: AsyncSession, org_id: UUID | None = None
    ) -> dict[str, Any]:
        """
        Get statistics about embeddings in the system.

        Args:
            session: Database session
            org_id: Optional organization filter

        Returns:
            Dictionary with embedding statistics
        """
        from sqlalchemy import func

        # Base queries
        items_query = select(func.count(Item.id)).where(Item.deleted_at.is_(None))
        embeddings_query = select(func.count(ItemEmbedding.item_id))

        if org_id:
            items_query = items_query.where(Item.org_id == org_id)
            embeddings_query = embeddings_query.join(Item).where(Item.org_id == org_id)

        # Published items count
        published_query = items_query.where(Item.status == "published")

        # Execute queries
        total_items = await session.scalar(items_query)
        total_published = await session.scalar(published_query)
        total_embeddings = await session.scalar(embeddings_query)

        # Model version breakdown
        model_versions = await session.execute(
            select(
                ItemEmbedding.model_version,
                func.count(ItemEmbedding.item_id).label("count"),
            ).group_by(ItemEmbedding.model_version)
        )

        version_breakdown = {row[0]: row[1] for row in model_versions.all()}

        return {
            "total_items": total_items,
            "published_items": total_published,
            "items_with_embeddings": total_embeddings,
            "coverage_rate": total_embeddings / max(total_published, 1),
            "model_versions": version_breakdown,
            "missing_embeddings": max(0, total_published - total_embeddings),
        }
