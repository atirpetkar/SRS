from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class SchedulerStateBase(BaseModel):
    """Base schema for scheduler state."""

    user_id: str
    item_id: UUID
    stability: float
    difficulty: float
    due_at: datetime
    last_interval: int
    reps: int
    lapses: int
    last_reviewed_at: datetime | None = None
    scheduler_name: str = "fsrs_v6"
    version: int = 1


class SchedulerStateCreate(SchedulerStateBase):
    """Schema for creating scheduler state."""

    pass


class SchedulerStateUpdate(BaseModel):
    """Schema for updating scheduler state."""

    stability: float
    difficulty: float
    due_at: datetime
    last_interval: int
    reps: int
    lapses: int
    last_reviewed_at: datetime | None = None
    version: int


class SchedulerStateResponse(SchedulerStateBase):
    """Schema for scheduler state response."""

    class Config:
        from_attributes = True


class ReviewBase(BaseModel):
    """Base schema for reviews."""

    user_id: str
    item_id: UUID
    mode: str
    response: dict[str, Any]
    correct: bool | None = None
    latency_ms: int | None = None
    ease: int = Field(..., ge=1, le=4, description="FSRS rating 1-4")


class ReviewCreate(ReviewBase):
    """Schema for creating a review."""

    pass


class ReviewResponse(ReviewBase):
    """Schema for review response."""

    id: UUID
    ts: datetime
    latency_bucket: int | None = None

    class Config:
        from_attributes = True


class QueueItemResponse(BaseModel):
    """Schema for items in the review queue."""

    id: UUID
    type: str
    render_payload: dict[str, Any]
    due_at: datetime | None = None  # None for new items
    is_new: bool

    class Config:
        from_attributes = True


class ReviewQueueResponse(BaseModel):
    """Schema for review queue response."""

    due: list[QueueItemResponse]
    new: list[QueueItemResponse]


class ReviewRecordRequest(BaseModel):
    """Schema for recording a review."""

    item_id: UUID
    rating: int = Field(
        ..., ge=1, le=4, description="FSRS rating: 1=Again, 2=Hard, 3=Good, 4=Easy"
    )
    correct: bool | None = None
    latency_ms: int | None = None
    mode: str = "review"
    response: dict[str, Any] = Field(default_factory=dict)


class ReviewRecordResponse(BaseModel):
    """Schema for review record response."""

    updated_state: SchedulerStateResponse
    next_due: datetime
    interval_days: int
