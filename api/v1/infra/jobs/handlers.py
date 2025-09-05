"""
Job handlers for Step 11 background processing.

This module contains job handlers that implement the JobHandler protocol
and are registered in the job registry for background processing.
"""

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config.settings import Settings
from api.v1.core.security import Principal
from api.v1.infra.jobs.service import JobService
from api.v1.items.models import Item
from api.v1.search.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


class ComputeItemEmbeddingHandler:
    """
    Job handler for computing embeddings for individual items.

    Payload expected:
    {
        "item_id": "uuid-string",
        "model_version": "embedding-model-version",
        "force_recompute": false  # optional
    }
    """

    def __init__(self, settings: Settings):
        self.settings = settings

    async def handle(
        self,
        session: AsyncSession,
        principal_ctx: Principal,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Process embedding computation for a single item."""

        # Validate payload
        item_id_str = payload.get("item_id")
        if not item_id_str:
            raise ValueError("item_id is required in payload")

        try:
            item_id = UUID(item_id_str)
        except ValueError:
            raise ValueError(f"Invalid item_id format: {item_id_str}")

        force_recompute = payload.get("force_recompute", False)
        expected_model_version = payload.get("model_version")

        # Get the item with org isolation
        result = await session.execute(
            select(Item).where(
                Item.id == item_id,
                Item.org_id == principal_ctx.org_uuid,
                Item.deleted_at.is_(None),
            )
        )
        item = result.scalar_one_or_none()

        if not item:
            logger.warning(
                "Item not found for embedding computation",
                extra={"item_id": str(item_id), "org_id": str(principal_ctx.org_uuid)},
            )
            return {"status": "skipped", "reason": "item_not_found"}

        # Only process published items
        if item.status != "published":
            logger.info(
                "Skipping embedding for non-published item",
                extra={"item_id": str(item_id), "item_status": item.status},
            )
            return {"status": "skipped", "reason": "item_not_published"}

        # Compute embedding using the embedding service
        embedding_service = EmbeddingService(self.settings)

        try:
            embedding = await embedding_service.compute_embedding_for_item(
                session, item, force_recompute=force_recompute
            )

            # Verify model version if specified
            if (
                expected_model_version
                and embedding.model_version != expected_model_version
            ):
                logger.warning(
                    "Model version mismatch in embedding computation",
                    extra={
                        "item_id": str(item_id),
                        "expected_version": expected_model_version,
                        "actual_version": embedding.model_version,
                    },
                )

            logger.info(
                "Embedding computed successfully",
                extra={
                    "item_id": str(item_id),
                    "model_version": embedding.model_version,
                    "force_recompute": force_recompute,
                },
            )

            return {
                "status": "completed",
                "item_id": str(item_id),
                "embedding_id": str(embedding.item_id),
                "model_version": embedding.model_version,
                "was_recomputed": force_recompute
                or "recomputed" in (embedding.meta or {}),
            }

        except Exception as e:
            logger.error(
                "Failed to compute embedding",
                extra={"item_id": str(item_id), "error": str(e)},
            )
            raise  # Re-raise for job retry logic


class ComputeEmbeddingsBatchHandler:
    """
    Job handler for computing embeddings in batch for multiple items.

    Payload expected:
    {
        "org_id": "uuid-string",  # optional, defaults to job org_id
        "force_recompute": false,  # optional
        "batch_size": 100,  # optional
        "item_type": "flashcard",  # optional filter
        "tags": ["tag1", "tag2"]   # optional filter
    }
    """

    def __init__(self, settings: Settings):
        self.settings = settings

    async def handle(
        self,
        session: AsyncSession,
        principal_ctx: Principal,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Process batch embedding computation."""

        # Parse payload parameters
        org_id = principal_ctx.org_uuid  # Always use job's org context
        force_recompute = payload.get("force_recompute", False)
        batch_size = payload.get("batch_size", 100)

        # Validate batch size
        if batch_size < 1 or batch_size > 1000:
            raise ValueError(
                f"batch_size must be between 1 and 1000, got: {batch_size}"
            )

        logger.info(
            "Starting batch embedding computation",
            extra={
                "org_id": str(org_id),
                "force_recompute": force_recompute,
                "batch_size": batch_size,
            },
        )

        # Use embedding service for batch processing
        embedding_service = EmbeddingService(self.settings)

        try:
            stats = await embedding_service.compute_embeddings_for_published_items(
                session=session,
                org_id=org_id,
                batch_size=batch_size,
                force_recompute=force_recompute,
            )

            logger.info(
                "Batch embedding computation completed",
                extra={"org_id": str(org_id), "stats": stats},
            )

            return {
                "status": "completed",
                "org_id": str(org_id),
                "processing_stats": stats,
                "force_recompute": force_recompute,
                "batch_size": batch_size,
            }

        except Exception as e:
            logger.error(
                "Batch embedding computation failed",
                extra={"org_id": str(org_id), "error": str(e)},
            )
            raise  # Re-raise for job retry logic


class MaintenanceCleanupHandler:
    """
    Job handler for maintenance tasks like cleaning up old jobs.

    Payload expected:
    {
        "tasks": ["cleanup_jobs", "vacuum_embeddings"],  # optional, defaults to all
        "dry_run": false  # optional
    }
    """

    def __init__(self, settings: Settings):
        self.settings = settings

    async def handle(
        self,
        session: AsyncSession,
        principal_ctx: Principal,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Process maintenance tasks."""

        tasks = payload.get("tasks", ["cleanup_jobs"])
        dry_run = payload.get("dry_run", False)
        results = {}

        logger.info(
            "Starting maintenance tasks",
            extra={
                "tasks": tasks,
                "dry_run": dry_run,
                "org_id": str(principal_ctx.org_uuid),
            },
        )

        # Job cleanup task
        if "cleanup_jobs" in tasks:
            try:
                if not dry_run:
                    job_service = JobService(self.settings)
                    deleted_count = await job_service.cleanup_old_jobs(session)
                    results["cleanup_jobs"] = {
                        "status": "completed",
                        "deleted_count": deleted_count,
                    }
                else:
                    results["cleanup_jobs"] = {
                        "status": "dry_run",
                        "message": "Would clean up old jobs",
                    }

                logger.info("Job cleanup task completed", extra=results["cleanup_jobs"])

            except Exception as e:
                results["cleanup_jobs"] = {"status": "failed", "error": str(e)}
                logger.error("Job cleanup task failed", extra={"error": str(e)})

        # TODO: Add other maintenance tasks as needed
        # - vacuum_embeddings: Remove orphaned embeddings
        # - reindex_search: Rebuild search indexes
        # - validate_data: Data consistency checks

        logger.info(
            "Maintenance tasks completed",
            extra={"results": results, "dry_run": dry_run},
        )

        return {
            "status": "completed",
            "tasks_processed": tasks,
            "dry_run": dry_run,
            "results": results,
        }
