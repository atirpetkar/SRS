"""
Pydantic schemas for content generation API endpoints.

Defines request/response models for the generation functionality.
"""

from typing import Any

from pydantic import BaseModel, Field, validator


class GenerateRequest(BaseModel):
    """Request schema for content generation."""

    text: str | None = Field(
        None,
        description="Input text to generate items from",
        min_length=50,
        max_length=50000,
    )
    topic: str | None = Field(
        None, description="Topic context for generation", max_length=200
    )
    types: list[str] | None = Field(
        None, description="Item types to generate (flashcard, mcq, cloze, short_answer)"
    )
    count: int | None = Field(
        None, description="Target number of items to generate", ge=1, le=50
    )
    difficulty: str | None = Field(
        None, description="Difficulty level (intro, core, stretch)"
    )

    @validator("text", "topic")
    def text_not_empty(cls, v):
        if v is not None and not v.strip():
            raise ValueError("Text fields cannot be empty")
        return v

    @validator("types")
    def valid_types(cls, v):
        if v is not None:
            valid_types = {"flashcard", "mcq", "cloze", "short_answer"}
            for item_type in v:
                if item_type not in valid_types:
                    raise ValueError(
                        f"Invalid item type: {item_type}. Must be one of {valid_types}"
                    )
        return v

    @validator("difficulty")
    def valid_difficulty(cls, v):
        if v is not None and v not in {"intro", "core", "stretch"}:
            raise ValueError("Difficulty must be one of: intro, core, stretch")
        return v

    class Config:
        schema_extra = {
            "example": {
                "text": "Photosynthesis is the process by which plants convert sunlight into energy. The equation is 6CO2 + 6H2O + light energy → C6H12O6 + 6O2. This process occurs in the chloroplasts of plant cells.",
                "types": ["flashcard", "mcq", "cloze"],
                "count": 15,
                "difficulty": "core",
            }
        }


class GeneratedItem(BaseModel):
    """Schema for a generated item before validation."""

    type: str = Field(description="Item type")
    payload: dict[str, Any] = Field(description="Item payload")
    tags: list[str] = Field(default_factory=list, description="Item tags")
    difficulty: str | None = Field(None, description="Difficulty level")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Generation metadata"
    )


class RejectedItem(BaseModel):
    """Schema for items that failed quality gates."""

    item: GeneratedItem = Field(description="The rejected item")
    reason: str = Field(description="Reason for rejection")
    details: str | None = Field(None, description="Additional details about rejection")


class GenerationDiagnostics(BaseModel):
    """Diagnostics information about the generation process."""

    input_length: int = Field(description="Length of input text")
    extracted_keypoints: int = Field(description="Number of keypoints extracted")
    extracted_numeric_facts: int = Field(
        description="Number of numeric facts extracted"
    )
    extracted_sentences: int = Field(description="Number of sentences processed")
    extracted_procedures: int = Field(
        description="Number of procedures/formulas extracted"
    )
    total_generated: int = Field(
        description="Total items generated before quality gates"
    )
    quality_filtered: int = Field(description="Items rejected by quality gates")
    final_count: int = Field(description="Final number of items returned")
    processing_time_ms: int | None = Field(
        None, description="Processing time in milliseconds"
    )


class GenerateResponse(BaseModel):
    """Response schema for content generation."""

    generated: list[GeneratedItem] = Field(
        description="Successfully generated items (draft status)"
    )
    rejected: list[RejectedItem] = Field(
        default_factory=list, description="Items rejected by quality gates"
    )
    diagnostics: GenerationDiagnostics = Field(
        description="Generation process diagnostics"
    )
    warnings: list[str] = Field(
        default_factory=list, description="Non-fatal warnings during generation"
    )

    class Config:
        schema_extra = {
            "example": {
                "generated": [
                    {
                        "type": "flashcard",
                        "payload": {
                            "front": "What is photosynthesis?",
                            "back": "The process by which plants convert sunlight into energy",
                        },
                        "tags": ["generated", "definition"],
                        "difficulty": "core",
                        "metadata": {
                            "generation_method": "keypoint_extraction",
                            "confidence": 0.8,
                            "provenance": {
                                "generator": "basic_rules",
                                "rule": "definition_extraction",
                            },
                        },
                    }
                ],
                "rejected": [],
                "diagnostics": {
                    "input_length": 215,
                    "extracted_keypoints": 2,
                    "extracted_numeric_facts": 1,
                    "extracted_sentences": 3,
                    "extracted_procedures": 1,
                    "total_generated": 5,
                    "quality_filtered": 0,
                    "final_count": 5,
                    "processing_time_ms": 1250,
                },
                "warnings": [],
            }
        }
