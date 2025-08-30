from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator


class FlashcardPayload(BaseModel):
    """Flashcard item payload validator."""

    front: str = Field(..., min_length=1, description="Front side of the card")
    back: str = Field(..., min_length=1, description="Back side of the card")
    examples: list[str] | None = Field(default=None, description="Usage examples")
    hints: list[str] | None = Field(default=None, description="Hints for remembering")
    pronunciation: str | None = Field(default=None, description="Pronunciation guide")

    @field_validator("examples", "hints")
    @classmethod
    def validate_string_lists(cls, v):
        if v is not None and not all(
            isinstance(item, str) and len(item.strip()) > 0 for item in v
        ):
            raise ValueError("All items must be non-empty strings")
        return v


class MCQOption(BaseModel):
    """MCQ option model."""

    id: str = Field(..., min_length=1, description="Option identifier")
    text: str = Field(..., min_length=1, description="Option text")
    is_correct: bool = Field(..., description="Whether this option is correct")
    rationale: str | None = Field(
        default=None, description="Explanation for this option"
    )


class MCQPayload(BaseModel):
    """Multiple Choice Question item payload validator."""

    stem: str = Field(..., min_length=1, description="Question stem")
    options: list[MCQOption] = Field(..., min_items=2, description="Answer options")
    multiple_select: bool | None = Field(
        default=False, description="Allow multiple correct answers"
    )

    @field_validator("options")
    @classmethod
    def validate_options(cls, v):
        if len(v) < 2:
            raise ValueError("Must have at least 2 options")

        # Check for duplicate IDs
        ids = [opt.id for opt in v]
        if len(set(ids)) != len(ids):
            raise ValueError("Option IDs must be unique")

        # Check for at least one correct answer
        correct_count = sum(1 for opt in v if opt.is_correct)
        if correct_count == 0:
            raise ValueError("Must have at least one correct option")

        return v


class ClozeBlank(BaseModel):
    """Cloze deletion blank model."""

    id: str = Field(..., min_length=1, description="Blank identifier")
    answers: list[str] = Field(..., min_items=1, description="Acceptable answers")
    alt_answers: list[str] | None = Field(
        default=None, description="Alternative acceptable answers"
    )
    case_sensitive: bool | None = Field(
        default=False, description="Whether matching is case sensitive"
    )

    @field_validator("answers")
    @classmethod
    def validate_answers(cls, v):
        if not all(isinstance(ans, str) and len(ans.strip()) > 0 for ans in v):
            raise ValueError("All answers must be non-empty strings")
        return v

    @field_validator("alt_answers")
    @classmethod
    def validate_alt_answers(cls, v):
        if v is not None and not all(
            isinstance(ans, str) and len(ans.strip()) > 0 for ans in v
        ):
            raise ValueError("All alternative answers must be non-empty strings")
        return v


class ClozePayload(BaseModel):
    """Cloze deletion item payload validator."""

    text: str = Field(..., min_length=1, description="Text with blanks marked")
    blanks: list[ClozeBlank] = Field(..., min_items=1, description="Blank definitions")
    context_note: str | None = Field(default=None, description="Additional context")

    @field_validator("blanks")
    @classmethod
    def validate_blanks(cls, v):
        if len(v) == 0:
            raise ValueError("Must have at least one blank")

        # Check for duplicate blank IDs
        ids = [blank.id for blank in v]
        if len(set(ids)) != len(ids):
            raise ValueError("Blank IDs must be unique")

        return v


class ShortAnswerExpected(BaseModel):
    """Expected answer for short answer questions."""

    value: str | None = Field(default=None, description="Expected answer value")
    unit: str | None = Field(
        default=None, description="Expected unit (for numeric answers)"
    )


class ShortAnswerGrading(BaseModel):
    """Grading configuration for short answer."""

    method: str = Field(
        default="exact", description="Grading method: exact, regex, numeric"
    )


class ShortAnswerPayload(BaseModel):
    """Short answer item payload validator."""

    prompt: str = Field(..., min_length=1, description="Question prompt")
    expected: ShortAnswerExpected = Field(..., description="Expected answer")
    acceptable_patterns: list[str] | None = Field(
        default=None, description="Regex patterns for acceptable answers"
    )
    grading: ShortAnswerGrading = Field(
        default_factory=ShortAnswerGrading, description="Grading configuration"
    )

    @field_validator("acceptable_patterns")
    @classmethod
    def validate_patterns(cls, v):
        if v is not None:
            import re

            for pattern in v:
                try:
                    re.compile(pattern)
                except re.error as e:
                    raise ValueError(f"Invalid regex pattern '{pattern}': {e}") from e
        return v


class FlashcardValidator:
    """Validator for flashcard items."""

    def validate(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Validate and normalize flashcard payload."""
        try:
            validated = FlashcardPayload(**payload)
            return validated.model_dump(exclude_none=True)
        except ValidationError as e:
            raise ValueError(f"Invalid flashcard payload: {e}") from e

    def render(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Render flashcard for display."""
        return {
            "type": "flashcard",
            "front": payload["front"],
            "back": payload["back"],
            "has_examples": bool(payload.get("examples")),
            "has_hints": bool(payload.get("hints")),
            "has_pronunciation": bool(payload.get("pronunciation")),
        }


class MCQValidator:
    """Validator for multiple choice questions."""

    def validate(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Validate and normalize MCQ payload."""
        try:
            validated = MCQPayload(**payload)
            return validated.model_dump(exclude_none=True)
        except ValidationError as e:
            raise ValueError(f"Invalid MCQ payload: {e}") from e

    def render(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Render MCQ for display."""
        return {
            "type": "mcq",
            "stem": payload["stem"],
            "options": [
                {"id": opt["id"], "text": opt["text"]} for opt in payload["options"]
            ],
            "multiple_select": payload.get("multiple_select", False),
        }


class ClozeValidator:
    """Validator for cloze deletion items."""

    def validate(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Validate and normalize cloze payload."""
        try:
            validated = ClozePayload(**payload)
            return validated.model_dump(exclude_none=True)
        except ValidationError as e:
            raise ValueError(f"Invalid cloze payload: {e}") from e

    def render(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Render cloze for display."""
        return {
            "type": "cloze",
            "text": payload["text"],
            "blank_count": len(payload["blanks"]),
            "has_context": bool(payload.get("context_note")),
        }


class ShortAnswerValidator:
    """Validator for short answer items."""

    def validate(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Validate and normalize short answer payload."""
        try:
            validated = ShortAnswerPayload(**payload)
            return validated.model_dump(exclude_none=True)
        except ValidationError as e:
            raise ValueError(f"Invalid short answer payload: {e}") from e

    def render(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Render short answer for display."""
        return {
            "type": "short_answer",
            "prompt": payload["prompt"],
            "grading_method": payload["grading"]["method"],
            "has_patterns": bool(payload.get("acceptable_patterns")),
        }
