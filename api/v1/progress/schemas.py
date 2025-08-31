from datetime import date as Date

from pydantic import BaseModel, Field


class ProgressOverviewResponse(BaseModel):
    """Schema for progress overview metrics."""

    attempts_7d: int = Field(..., description="Total review attempts in last 7 days")
    accuracy_7d: float = Field(
        ..., description="Average accuracy in last 7 days (0.0-1.0)"
    )
    avg_latency_ms_7d: float | None = Field(
        ..., description="Average response latency in ms"
    )
    streak_days: int = Field(..., description="Current daily review streak")
    total_items: int = Field(..., description="Total items in the system")
    reviewed_items: int = Field(
        ..., description="Items that have been reviewed at least once"
    )


class WeakAreaItem(BaseModel):
    """Schema for a single weak area analysis item."""

    name: str = Field(..., description="Tag, type, or difficulty level name")
    accuracy: float = Field(..., description="Accuracy rate (0.0-1.0)")
    attempts: int = Field(..., description="Total number of attempts")


class WeakAreasResponse(BaseModel):
    """Schema for weak areas analysis."""

    tags: list[WeakAreaItem] = Field(..., description="Weak areas by tag")
    types: list[WeakAreaItem] = Field(..., description="Weak areas by item type")
    difficulty: list[WeakAreaItem] = Field(
        ..., description="Weak areas by difficulty level"
    )


class ForecastDay(BaseModel):
    """Schema for a single day's forecast."""

    date: Date = Field(..., description="Date for the forecast")
    due_count: int = Field(..., description="Number of items due for review")


class ForecastResponse(BaseModel):
    """Schema for forecast response."""

    by_day: list[ForecastDay] = Field(..., description="Daily due item forecasts")
