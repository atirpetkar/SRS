"""
Hybrid search implementation combining keyword and vector similarity.

Implements 2024-2025 best practices for hybrid ranking with configurable weights.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import Text, and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.config.settings import Settings
from api.v1.core.registries import vectorizer_registry
from api.v1.items.models import Item
from api.v1.items.utils import canonical_text
from api.v1.search.models import ItemEmbedding


class HybridSearchService:
    """
    Hybrid search service combining keyword and vector similarity.

    Uses weighted combination of BM25/tsvector scores and cosine similarity
    for improved relevance ranking.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.keyword_weight = 0.3  # Weight for keyword/BM25 score
        self.vector_weight = 0.7  # Weight for vector similarity
        self.use_tsvector = settings.environment in ("production", "staging")

    async def search_items(
        self,
        session: AsyncSession,
        org_id: UUID,
        query: str | None = None,
        filters: dict[str, Any] | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Item], int]:
        """
        Perform hybrid search combining keyword and vector similarity.

        Args:
            session: Database session
            org_id: Organization ID for filtering
            query: Search query text
            filters: Additional filters (type, status, etc.)
            limit: Maximum results to return
            offset: Results offset for pagination

        Returns:
            Tuple of (items, total_count)
        """
        # Base conditions
        base_conditions = [
            Item.org_id == org_id,
            Item.deleted_at.is_(None),
        ]

        # Add filters
        if filters:
            if filters.get("type"):
                base_conditions.append(Item.type == filters["type"])
            if filters.get("status"):
                base_conditions.append(Item.status == filters["status"])
            if filters.get("difficulty"):
                base_conditions.append(Item.difficulty == filters["difficulty"])
            if filters.get("source_id"):
                base_conditions.append(Item.source_id == filters["source_id"])
            if filters.get("created_by"):
                base_conditions.append(Item.created_by == filters["created_by"])
            if filters.get("tags"):
                # Match items that have ANY of the specified tags
                tag_conditions = [Item.tags.contains([tag]) for tag in filters["tags"]]
                base_conditions.append(or_(*tag_conditions))

        # Build query based on search type
        if query:
            return await self._hybrid_search(
                session, base_conditions, query, limit, offset
            )
        else:
            return await self._filter_only_search(
                session, base_conditions, limit, offset
            )

    async def _hybrid_search(
        self,
        session: AsyncSession,
        base_conditions: list,
        query: str,
        limit: int,
        offset: int,
    ) -> tuple[list[Item], int]:
        """Perform hybrid search with both keyword and vector scoring."""

        if self.use_tsvector:
            # Production: Use tsvector + vector similarity
            return await self._production_hybrid_search(
                session, base_conditions, query, limit, offset
            )
        else:
            # Development: Use ILIKE fallback
            return await self._dev_hybrid_search(
                session, base_conditions, query, limit, offset
            )

    async def _production_hybrid_search(
        self,
        session: AsyncSession,
        base_conditions: list,
        query: str,
        limit: int,
        offset: int,
    ) -> tuple[list[Item], int]:
        """Production hybrid search with tsvector and pgvector."""

        # Get query embedding
        vectorizer = vectorizer_registry.get(self.settings.embeddings.value)
        query_embedding = vectorizer.vectorize(query)

        # Build hybrid query with both keyword and vector scoring
        search_condition = Item.search_document.op("@@")(
            func.to_tsquery("english", query)
        )
        all_conditions = base_conditions + [search_condition]

        # Calculate keyword rank
        keyword_rank = func.ts_rank_cd(
            Item.search_document, func.to_tsquery("english", query)
        )

        # Calculate vector similarity (cosine distance)
        vector_similarity = func.coalesce(
            text("1 - (item_embeddings.embedding <=> :query_vector)"), text("0")
        ).params(query_vector=query_embedding)

        # Hybrid score: weighted combination
        hybrid_score = (
            self.keyword_weight * keyword_rank + self.vector_weight * vector_similarity
        ).label("hybrid_score")

        # Main query with left join to embeddings
        query_stmt = (
            select(Item, hybrid_score)
            .select_from(Item.__table__.outerjoin(ItemEmbedding.__table__))
            .where(and_(*all_conditions))
            .order_by(text("hybrid_score DESC"), Item.created_at.desc())
            .offset(offset)
            .limit(limit)
            .options(selectinload(Item.source))
        )

        # Get total count
        count_query = (
            select(func.count(Item.id))
            .select_from(Item.__table__.outerjoin(ItemEmbedding.__table__))
            .where(and_(*all_conditions))
        )

        # Execute queries
        result = await session.execute(query_stmt)
        count_result = await session.execute(count_query)

        items = [row[0] for row in result.all()]
        total = count_result.scalar()

        return items, total

    async def _dev_hybrid_search(
        self,
        session: AsyncSession,
        base_conditions: list,
        query: str,
        limit: int,
        offset: int,
    ) -> tuple[list[Item], int]:
        """Development hybrid search with ILIKE fallback."""

        search_text = f"%{query}%"
        search_condition = or_(
            func.cast(Item.payload, Text).ilike(search_text),
            func.array_to_string(Item.tags, " ").ilike(search_text),
            Item.type.ilike(search_text),
        )
        all_conditions = base_conditions + [search_condition]

        # Simple query without vector similarity in dev
        query_stmt = (
            select(Item)
            .where(and_(*all_conditions))
            .order_by(Item.created_at.desc())
            .offset(offset)
            .limit(limit)
            .options(selectinload(Item.source))
        )

        count_query = select(func.count(Item.id)).where(and_(*all_conditions))

        result = await session.execute(query_stmt)
        count_result = await session.execute(count_query)

        items = result.scalars().all()
        total = count_result.scalar()

        return items, total

    async def _filter_only_search(
        self,
        session: AsyncSession,
        base_conditions: list,
        limit: int,
        offset: int,
    ) -> tuple[list[Item], int]:
        """Search without query - just filtering and sorting."""

        query_stmt = (
            select(Item)
            .where(and_(*base_conditions))
            .order_by(Item.created_at.desc())
            .offset(offset)
            .limit(limit)
            .options(selectinload(Item.source))
        )

        count_query = select(func.count(Item.id)).where(and_(*base_conditions))

        result = await session.execute(query_stmt)
        count_result = await session.execute(count_query)

        items = result.scalars().all()
        total = count_result.scalar()

        return items, total

    async def find_similar_items(
        self,
        session: AsyncSession,
        item: Item,
        threshold: float = 0.90,
        limit: int = 10,
    ) -> list[tuple[Item, float]]:
        """
        Find items similar to the given item using embeddings.

        Args:
            session: Database session
            item: Reference item
            threshold: Minimum cosine similarity threshold
            limit: Maximum similar items to return

        Returns:
            List of (item, similarity_score) tuples
        """
        # Get or generate embedding for reference item
        if item.embedding:
            reference_embedding = item.embedding.embedding
        else:
            # Generate embedding on-the-fly
            vectorizer = vectorizer_registry.get(self.settings.embeddings.value)
            item_text = canonical_text(item.type, item.payload)
            reference_embedding = vectorizer.vectorize(item_text)

        # Find similar items using cosine similarity
        similarity_expr = text(
            "1 - (item_embeddings.embedding <=> :ref_vector)"
        ).params(ref_vector=reference_embedding)

        query_stmt = (
            select(Item, similarity_expr.label("similarity"))
            .select_from(Item.__table__.join(ItemEmbedding.__table__))
            .where(
                and_(
                    Item.org_id == item.org_id,
                    Item.id != item.id,  # Exclude self
                    Item.deleted_at.is_(None),
                    similarity_expr >= threshold,
                )
            )
            .order_by(text("similarity DESC"))
            .limit(limit)
        )

        result = await session.execute(query_stmt)
        return [(row[0], float(row[1])) for row in result.all()]
