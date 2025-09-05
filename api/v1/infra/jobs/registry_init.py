"""
Job registry initialization for Step 11.

Registers all job handlers with the global job registry.
"""

import logging

from api.config.settings import settings
from api.v1.core.registries import job_registry
from api.v1.infra.jobs.handlers import (
    ComputeEmbeddingsBatchHandler,
    ComputeItemEmbeddingHandler,
    MaintenanceCleanupHandler,
)

logger = logging.getLogger(__name__)


def register_job_handlers() -> None:
    """Register all job handlers with the job registry."""

    logger.info("Registering job handlers")

    # Embedding job handlers
    job_registry.register(
        "compute_item_embedding", ComputeItemEmbeddingHandler(settings)
    )

    job_registry.register(
        "compute_embeddings_batch", ComputeEmbeddingsBatchHandler(settings)
    )

    # Maintenance job handlers
    job_registry.register("maintenance_cleanup", MaintenanceCleanupHandler(settings))

    logger.info(
        "Job handlers registered", extra={"registered_handlers": job_registry.list()}
    )


# Auto-register handlers when module is imported
register_job_handlers()
