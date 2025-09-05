"""
Job system Pydantic schemas for Step 11.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from api.v1.infra.jobs.models import JobStatus


class JobCreate(BaseModel):
    """Schema for creating a new job."""

    type: str = Field(..., description="Job type identifier")
    payload: dict[str, Any] = Field(default_factory=dict, description="Job parameters")
    priority: int = Field(
        default=5, ge=1, le=10, description="Priority (1=highest, 10=lowest)"
    )
    run_at: datetime | None = Field(
        default=None, description="Earliest time to run job"
    )
    dedupe_key: str | None = Field(default=None, description="Deduplication key")


class JobUpdate(BaseModel):
    """Schema for updating job status and results."""

    status: JobStatus | None = None
    result: dict[str, Any] | None = None
    progress: dict[str, Any] | None = None
    error_code: str | None = None
    last_error: str | None = None


class JobResponse(BaseModel):
    """Schema for job API responses."""

    id: UUID
    type: str
    org_id: UUID
    user_id: UUID | None
    payload: dict[str, Any]
    status: str
    priority: int
    run_at: datetime
    attempts: int

    # Worker coordination
    locked_at: datetime | None = None
    locked_by: str | None = None
    heartbeat_at: datetime | None = None

    # Results
    result: dict[str, Any] | None = None
    progress: dict[str, Any] | None = None
    progress_percentage: float | None = None
    error_code: str | None = None
    last_error: str | None = None

    # Metadata
    dedupe_key: str | None = None
    requested_by_user_id: UUID | None = None
    request_id: str | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class JobListFilters(BaseModel):
    """Schema for job listing filters."""

    status: list[JobStatus] | None = Field(
        default=None, description="Filter by job status"
    )
    type: str | None = Field(default=None, description="Filter by job type")
    org_id: UUID | None = Field(default=None, description="Filter by organization")
    user_id: UUID | None = Field(default=None, description="Filter by user")
    limit: int = Field(
        default=50, ge=1, le=1000, description="Maximum results to return"
    )
    offset: int = Field(default=0, ge=0, description="Results offset for pagination")


class JobListResponse(BaseModel):
    """Schema for job list API response."""

    jobs: list[JobResponse]
    total: int
    limit: int
    offset: int


class JobStatsResponse(BaseModel):
    """Schema for job statistics."""

    total_jobs: int
    by_status: dict[str, int]
    by_type: dict[str, int]
    queue_depth: int  # queued + running
    failed_last_hour: int
    avg_runtime_seconds: float | None = None


class JobActionRequest(BaseModel):
    """Schema for job actions (retry, cancel)."""

    job_ids: list[UUID] = Field(..., description="Job IDs to act upon")


class JobActionResponse(BaseModel):
    """Schema for job action responses."""

    success_ids: list[UUID]
    failed_ids: list[UUID]
    errors: dict[str, str]  # job_id -> error message


class JobEnqueueRequest(BaseModel):
    """Schema for enqueueing jobs via API."""

    type: str = Field(..., description="Job type")
    payload: dict[str, Any] = Field(default_factory=dict, description="Job payload")
    priority: int = Field(default=5, ge=1, le=10, description="Job priority")
    run_at: datetime | None = Field(default=None, description="Scheduled run time")
    dedupe_key: str | None = Field(default=None, description="Deduplication key")


class JobEnqueueResponse(BaseModel):
    """Schema for job enqueue response."""

    job_id: UUID
    status: str
    deduplicated: bool = Field(
        default=False, description="Whether job was deduplicated"
    )
