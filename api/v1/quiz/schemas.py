from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class QuizStartRequest(BaseModel):
    """Schema for starting a quiz session."""

    mode: str = Field(..., description="Quiz mode: review, drill, or mock")
    params: dict[str, Any] = Field(default_factory=dict, description="Quiz parameters")

    class Config:
        schema_extra = {
            "example": {
                "mode": "drill",
                "params": {
                    "tags": ["italian", "vocabulary"],
                    "type": "flashcard",
                    "length": 10,
                    "time_limit_s": 300,
                },
            }
        }


class QuizItemResponse(BaseModel):
    """Schema for items in a quiz."""

    id: UUID
    type: str
    render_payload: dict[str, Any]
    position: int

    class Config:
        from_attributes = True


class QuizStartResponse(BaseModel):
    """Schema for quiz start response."""

    quiz_id: UUID
    mode: str
    params: dict[str, Any]
    started_at: datetime
    items: list[QuizItemResponse]
    total_items: int
    time_limit_s: int | None = None

    class Config:
        from_attributes = True


class QuizSubmitRequest(BaseModel):
    """Schema for submitting a quiz item response."""

    quiz_id: UUID
    item_id: UUID
    response: dict[str, Any]

    class Config:
        schema_extra = {
            "examples": {
                "mcq": {
                    "quiz_id": "123e4567-e89b-12d3-a456-426614174000",
                    "item_id": "456e7890-e89b-12d3-a456-426614174001",
                    "response": {"selected_option_ids": ["a", "c"]},
                },
                "cloze": {
                    "quiz_id": "123e4567-e89b-12d3-a456-426614174000",
                    "item_id": "456e7890-e89b-12d3-a456-426614174001",
                    "response": {
                        "blank_answers": {"blank1": "hello", "blank2": "world"}
                    },
                },
                "short_answer": {
                    "quiz_id": "123e4567-e89b-12d3-a456-426614174000",
                    "item_id": "456e7890-e89b-12d3-a456-426614174001",
                    "response": {"answer": "42 meters"},
                },
                "flashcard": {
                    "quiz_id": "123e4567-e89b-12d3-a456-426614174000",
                    "item_id": "456e7890-e89b-12d3-a456-426614174001",
                    "response": {"rating": 3, "self_correct": True},
                },
            }
        }


class GradingResult(BaseModel):
    """Schema for grading results."""

    correct: bool
    partial: float | None = Field(
        None, ge=0.0, le=1.0, description="Partial credit score"
    )
    rationale: str | None = None
    normalized_answer: Any = None


class QuizSubmitResponse(BaseModel):
    """Schema for quiz submit response."""

    item_id: UUID
    grading: GradingResult
    position: int
    total_items: int


class QuizFinishRequest(BaseModel):
    """Schema for finishing a quiz."""

    quiz_id: UUID


class ScoreBreakdown(BaseModel):
    """Schema for quiz score breakdown."""

    total_items: int
    correct_items: int
    partial_credit_items: int
    incorrect_items: int
    average_partial_score: float | None = None
    items_by_type: dict[str, dict[str, int]] = Field(default_factory=dict)
    time_taken_s: int | None = None


class QuizFinishResponse(BaseModel):
    """Schema for quiz finish response."""

    quiz_id: UUID
    final_score: float = Field(
        ..., ge=0.0, le=1.0, description="Final score as percentage"
    )
    breakdown: ScoreBreakdown
    finished_at: datetime
    time_taken_s: int | None = None

    class Config:
        from_attributes = True


# Supporting schemas for quiz management


class QuizBase(BaseModel):
    """Base schema for quiz."""

    mode: str
    params: dict[str, Any]


class QuizCreate(QuizBase):
    """Schema for creating a quiz."""

    org_id: UUID
    user_id: str


class QuizUpdate(BaseModel):
    """Schema for updating a quiz."""

    finished_at: datetime | None = None
    params: dict[str, Any] | None = None


class QuizResponse(QuizBase):
    """Schema for quiz response."""

    id: UUID
    org_id: UUID
    user_id: str
    started_at: datetime
    finished_at: datetime | None = None

    class Config:
        from_attributes = True


class ResultBase(BaseModel):
    """Base schema for quiz result."""

    score: float = Field(..., ge=0.0, le=1.0)
    breakdown: dict[str, Any]


class ResultCreate(ResultBase):
    """Schema for creating a result."""

    quiz_id: UUID
    user_id: str


class ResultResponse(ResultBase):
    """Schema for result response."""

    quiz_id: UUID
    user_id: str

    class Config:
        from_attributes = True
