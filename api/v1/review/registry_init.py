"""
Registry initialization for review module.
Registers FSRS-6 scheduler implementation.
"""

from api.v1.core.registries import scheduler_registry
from api.v1.review.fsrs import FSRSScheduler, FSRSState


class FSRSRegistryAdapter:
    """Adapter to make FSRSScheduler compatible with SchedulerRegistry protocol."""

    def __init__(self):
        self.scheduler = FSRSScheduler()

    def seed(self, user_id: str, item_id: str) -> FSRSState:
        """Initialize scheduler state for a new user/item pair."""
        return self.scheduler.seed(user_id, item_id)

    def update(
        self, state: FSRSState, rating: int, correct: bool | None, latency_ms: int
    ) -> FSRSState:
        """Update scheduler state based on review results."""
        return self.scheduler.update(state, rating, correct, latency_ms)


def init_review_registries():
    """Initialize review-related registries."""
    # Register FSRS-6 scheduler
    scheduler_registry.register("fsrs_v6", FSRSRegistryAdapter())
    scheduler_registry.register("fsrs_latest", FSRSRegistryAdapter())
