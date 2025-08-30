from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from api.v1.items.utils import normalize_tags, validate_difficulty


class ItemCreate(BaseModel):
    """Schema for creating a new item."""

    type: str = Field(
        ..., description="Item type (flashcard, mcq, cloze, short_answer)"
    )
    payload: dict[str, Any] = Field(..., description="Item-specific payload")
    tags: list[str] | None = Field(default=None, description="Tags for categorization")
    difficulty: str | None = Field(
        default=None, description="Difficulty level (intro, core, stretch)"
    )
    source_id: UUID | None = Field(default=None, description="Source reference")
    media: dict[str, Any] | None = Field(default=None, description="Media attachments")
    meta: dict[str, Any] | None = Field(default=None, description="Additional metadata")

    @field_validator("type")
    @classmethod
    def validate_type(cls, v):
        valid_types = {"flashcard", "mcq", "cloze", "short_answer"}
        if v not in valid_types:
            raise ValueError(f"Invalid item type: {v}. Must be one of {valid_types}")
        return v

    @field_validator("tags")
    @classmethod
    def normalize_tags_field(cls, v):
        return normalize_tags(v)

    @field_validator("difficulty")
    @classmethod
    def validate_difficulty_field(cls, v):
        return validate_difficulty(v)

    @field_validator("media", "meta")
    @classmethod
    def validate_dict_fields(cls, v):
        return v or {}


class ItemResponse(BaseModel):
    """Schema for item responses."""

    id: UUID
    type: str
    payload: dict[str, Any]
    tags: list[str]
    difficulty: str | None
    source_id: UUID | None
    media: dict[str, Any]
    meta: dict[str, Any]
    content_hash: str | None
    schema_version: int
    status: str
    version: int
    created_by: str | None
    org_id: UUID
    created_at: datetime
    deleted_at: datetime | None

    class Config:
        from_attributes = True


class ItemUpdate(BaseModel):
    """Schema for updating an existing item."""

    payload: dict[str, Any] | None = Field(default=None, description="Updated payload")
    tags: list[str] | None = Field(default=None, description="Updated tags")
    difficulty: str | None = Field(default=None, description="Updated difficulty")
    media: dict[str, Any] | None = Field(default=None, description="Updated media")
    meta: dict[str, Any] | None = Field(default=None, description="Updated metadata")
    status: str | None = Field(default=None, description="Updated status")

    @field_validator("tags")
    @classmethod
    def normalize_tags_field(cls, v):
        return normalize_tags(v) if v is not None else None

    @field_validator("difficulty")
    @classmethod
    def validate_difficulty_field(cls, v):
        return validate_difficulty(v) if v is not None else None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        if v is not None:
            valid_statuses = {"draft", "published"}
            if v not in valid_statuses:
                raise ValueError(
                    f"Invalid status: {v}. Must be one of {valid_statuses}"
                )
        return v


class ItemList(BaseModel):
    """Schema for item list responses."""

    items: list[ItemResponse]
    total: int
    offset: int
    limit: int
    has_more: bool


class ItemFilters(BaseModel):
    """Schema for item filtering parameters."""

    type: str | None = Field(default=None, description="Filter by item type")
    tags: list[str] | None = Field(
        default=None, description="Filter by tags (ANY match)"
    )
    status: str | None = Field(default=None, description="Filter by status")
    difficulty: str | None = Field(default=None, description="Filter by difficulty")
    source_id: UUID | None = Field(default=None, description="Filter by source")
    created_by: str | None = Field(default=None, description="Filter by creator")
    limit: int = Field(
        default=50, ge=1, le=1000, description="Number of items to return"
    )
    offset: int = Field(default=0, ge=0, description="Number of items to skip")

    @field_validator("tags")
    @classmethod
    def normalize_tags_field(cls, v):
        return normalize_tags(v) if v else None

    @field_validator("type", "status", "difficulty")
    @classmethod
    def validate_filter_strings(cls, v):
        return v.strip().lower() if v and isinstance(v, str) else v


# Import-related schemas


class ImportDiagnostic(BaseModel):
    """Schema for import diagnostics."""

    line: int | None = Field(default=None, description="Line number in source")
    row: int | None = Field(default=None, description="Row number in CSV")
    item: int | None = Field(default=None, description="Item index in JSON")
    issue: str = Field(..., description="Description of the issue")
    severity: Literal["error", "warning", "info"] = Field(
        ..., description="Severity level"
    )


class ImportRequest(BaseModel):
    """Schema for import requests."""

    format: Literal["markdown", "csv", "json"] = Field(
        ..., description="Format of the data"
    )
    data: str = Field(..., description="Content to import")
    source_id: UUID | None = Field(
        default=None, description="Optional source reference"
    )
    metadata: dict[str, Any] | None = Field(
        default=None, description="Additional metadata"
    )

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, v):
        return v or {}


class ImportResult(BaseModel):
    """Schema for import results."""

    staged_ids: list[UUID] = Field(
        ..., description="IDs of items created in draft status"
    )
    warnings: list[str] = Field(default=[], description="General warnings")
    diagnostics: list[ImportDiagnostic] = Field(
        default=[], description="Detailed diagnostics"
    )
    total_parsed: int = Field(..., description="Total items found in source")
    total_created: int = Field(..., description="Total items successfully created")
    total_errors: int = Field(..., description="Total items that failed validation")


class ApprovalRequest(BaseModel):
    """Schema for approving staged items."""

    ids: list[UUID] = Field(..., description="Item IDs to approve")

    @field_validator("ids")
    @classmethod
    def validate_ids(cls, v):
        if not v:
            raise ValueError("At least one item ID must be provided")
        if len(v) > 1000:
            raise ValueError("Cannot approve more than 1000 items at once")
        return v


class ApprovalResult(BaseModel):
    """Schema for approval results."""

    approved_ids: list[UUID] = Field(
        ..., description="IDs that were successfully approved"
    )
    failed_ids: list[UUID] = Field(..., description="IDs that failed approval")
    errors: dict[str, str] = Field(default={}, description="Errors keyed by item ID")
