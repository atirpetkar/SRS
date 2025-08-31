"""
Registry initialization for quiz module.
Registers grader implementations for all item types.
"""

from api.v1.core.registries import grader_registry
from api.v1.quiz.graders import (
    ClozeGrader,
    FlashcardGrader,
    MCQGrader,
    ShortAnswerGrader,
)


def init_quiz_registries():
    """Initialize quiz-related registries."""
    # Register graders for each item type
    grader_registry.register("mcq", MCQGrader())
    grader_registry.register("cloze", ClozeGrader())
    grader_registry.register("short_answer", ShortAnswerGrader())
    grader_registry.register("flashcard", FlashcardGrader())
