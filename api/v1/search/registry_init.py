"""
Initialize vectorizer registry for Step 8.

Registers all available vectorizer implementations based on settings.
"""

from api.config.settings import EmbeddingsType, settings
from api.v1.core.registries import vectorizer_registry
from api.v1.search.vectorizers import (
    openai_vectorizer,
    sbert_vectorizer,
    stub_vectorizer,
)


def init_vectorizer_registry():
    """Initialize vectorizer registry with available implementations."""

    # Always register stub vectorizer (no dependencies)
    vectorizer_registry.register("stub", stub_vectorizer)

    # Register sentence-BERT if available
    try:
        import sentence_transformers  # noqa: F401

        vectorizer_registry.register("sbert", sbert_vectorizer)
    except ImportError as e:
        if settings.embeddings == EmbeddingsType.SBERT:
            raise RuntimeError(
                "sentence-transformers not installed but EMBEDDINGS=sbert. "
                "Run: uv pip install sentence-transformers"
            ) from e

    # Register OpenAI if available
    try:
        import openai  # noqa: F401

        vectorizer_registry.register("openai", openai_vectorizer)
    except ImportError as e:
        if settings.embeddings == EmbeddingsType.OPENAI:
            raise RuntimeError(
                "openai package not installed but EMBEDDINGS=openai. "
                "Run: uv pip install openai"
            ) from e

    # Validate configured embedding provider is available
    try:
        vectorizer_registry.get(settings.embeddings.value)
    except KeyError as e:
        available = vectorizer_registry.list()
        raise RuntimeError(
            f"Configured embeddings provider '{settings.embeddings.value}' not available. "
            f"Available providers: {available}"
        ) from e
