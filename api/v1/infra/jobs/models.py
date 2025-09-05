"""
Job system models for Step 11 background processing.
"""

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, TIMESTAMP, CheckConstraint, SmallInteger, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from api.infra.database import Base


class JobStatus(str, Enum):
    """Job status enumeration."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DEADLETTER = "deadletter"
    CANCELED = "canceled"


class Job(Base):
    """
    Job model for background processing.

    Provides production-ready job queuing with:
    - Worker coordination (locking, heartbeats)
    - Progress tracking and structured errors
    - Idempotent processing via dedupe keys
    - Request tracing and observability
    """

    __tablename__ = "jobs"

    # Core fields
    id: Mapped[UUID] = mapped_column(PG_UUID, primary_key=True, default=uuid4)
    type: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Job type identifier"
    )
    org_id: Mapped[UUID] = mapped_column(
        PG_UUID, nullable=False, comment="Organization scope"
    )
    user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID, nullable=True, comment="Requesting user"
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
        comment="Job-specific parameters",
    )

    # Job state
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default=JobStatus.QUEUED.value,
        comment="Job status: queued|running|succeeded|failed|deadletter|canceled",
    )
    priority: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=5,
        comment="Priority 1-10, lower is higher priority",
    )
    run_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default="now()",
        comment="Earliest time to run job",
    )
    attempts: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, comment="Number of attempts made"
    )

    # Worker coordination
    locked_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True, comment="When job was locked by worker"
    )
    locked_by: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Worker ID that locked the job"
    )
    heartbeat_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True, comment="Last worker heartbeat"
    )

    # Results and progress
    result: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="Job result data"
    )
    progress: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="Progress tracking {processed, total}"
    )
    error_code: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Structured error identifier"
    )
    last_error: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Last error message"
    )

    # Tracing and deduplication
    dedupe_key: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Deduplication key for idempotent jobs"
    )
    requested_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID, nullable=True, comment="Original requesting user"
    )
    request_id: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Original request ID for tracing"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default="now()",
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default="now()",
        default=lambda: datetime.now(UTC),
    )

    # Constraints - only basic ones, indexes are created in migration
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'deadletter', 'canceled')",
            name="jobs_status_check",
        ),
        CheckConstraint("priority BETWEEN 1 AND 10", name="jobs_priority_check"),
    )

    def is_active(self) -> bool:
        """Check if job is in an active state (queued, running)."""
        return self.status in (JobStatus.QUEUED.value, JobStatus.RUNNING.value)

    def can_retry(self, max_attempts: int) -> bool:
        """Check if job can be retried based on attempts and status."""
        return self.status == JobStatus.FAILED.value and self.attempts < max_attempts

    def is_stuck(self, visibility_timeout_s: int) -> bool:
        """Check if running job is stuck based on heartbeat timeout."""
        if self.status != JobStatus.RUNNING.value or not self.heartbeat_at:
            return False

        from datetime import datetime

        timeout_threshold = datetime.now(UTC).timestamp() - visibility_timeout_s
        return self.heartbeat_at.timestamp() < timeout_threshold

    def get_progress_percentage(self) -> float | None:
        """Get progress as percentage if progress data is available."""
        if not self.progress or not isinstance(self.progress, dict):
            return None

        processed = self.progress.get("processed", 0)
        total = self.progress.get("total", 0)

        if total <= 0:
            return None

        return min(100.0, (processed / total) * 100.0)
