"""Initialize item type validators and importers in registries."""

from api.v1.core.registries import importer_registry, item_type_registry
from api.v1.items.importers import (
    CSVImporter,
    JSONImporter,
    MarkdownImporter,
)
from api.v1.items.validators import (
    ClozeValidator,
    FlashcardValidator,
    MCQValidator,
    ShortAnswerValidator,
)


def register_item_validators():
    """Register all item type validators with the ItemTypeRegistry."""
    item_type_registry.register("flashcard", FlashcardValidator())
    item_type_registry.register("mcq", MCQValidator())
    item_type_registry.register("cloze", ClozeValidator())
    item_type_registry.register("short_answer", ShortAnswerValidator())


def register_importers():
    """Register all importers with the ImporterRegistry."""
    importer_registry.register("markdown", MarkdownImporter())
    importer_registry.register("csv", CSVImporter())
    importer_registry.register("json", JSONImporter())
