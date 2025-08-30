"""Initialize item type validators in the registry."""

from api.v1.core.registries import item_type_registry
from api.v1.items.validators import (
    FlashcardValidator,
    MCQValidator,
    ClozeValidator,
    ShortAnswerValidator,
)


def register_item_validators():
    """Register all item type validators with the ItemTypeRegistry."""
    item_type_registry.register("flashcard", FlashcardValidator())
    item_type_registry.register("mcq", MCQValidator())
    item_type_registry.register("cloze", ClozeValidator())
    item_type_registry.register("short_answer", ShortAnswerValidator())