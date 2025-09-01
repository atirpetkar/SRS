"""
Vectorizer implementations for Step 8 - Embeddings.

Supports multiple backends: stub (deterministic), sbert (sentence-transformers), openai.
"""

import hashlib
import math
import os


class StubVectorizer:
    """
    Deterministic hash-based vectorizer for development and testing.

    Generates consistent 768-dimensional vectors from text hashes.
    No external dependencies or API calls required.
    """

    def vectorize(self, text: str) -> list[float]:
        """
        Create deterministic 768-dimensional vector from text hash.

        Uses SHA-256 hash to generate consistent vectors that maintain
        some semantic properties through character-level features.
        """
        # Create hash of normalized text
        normalized_text = text.strip().lower()
        text_hash = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()

        # Convert hex hash to vector of floats
        # Each pair of hex chars becomes a float between -1 and 1
        vector = []
        for i in range(0, len(text_hash), 2):
            hex_pair = text_hash[i : i + 2]
            # Convert to int (0-255) then normalize to [-1, 1]
            value = (int(hex_pair, 16) / 127.5) - 1.0
            vector.append(value)

        # Pad or truncate to exactly 768 dimensions
        while len(vector) < 768:
            # Use text length and position to generate additional values
            pos_val = (len(vector) % 256) / 127.5 - 1.0
            text_val = (len(normalized_text) % 256) / 127.5 - 1.0
            vector.append((pos_val + text_val) / 2.0)

        vector = vector[:768]  # Ensure exactly 768 dimensions

        # L2 normalize the vector for cosine similarity
        norm = math.sqrt(sum(x * x for x in vector))
        if norm > 0:
            vector = [x / norm for x in vector]

        return vector

    def get_dimension(self) -> int:
        """Return vector dimension (768 for compatibility)."""
        return 768

    def get_model_version(self) -> str:
        """Return model version identifier."""
        return "stub-v1.0"


class SentenceBERTVectorizer:
    """
    Sentence-BERT vectorizer using all-MiniLM-L6-v2 model.

    Provides high-quality semantic embeddings with good speed/performance balance.
    Recommended model based on 2024-2025 benchmarks.
    """

    def __init__(self):
        self._model = None
        self._model_name = "all-MiniLM-L6-v2"

    def _get_model(self):
        """Lazy load the sentence-transformers model."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(self._model_name)
            except ImportError as e:
                raise RuntimeError(
                    "sentence-transformers not installed. "
                    "Run: uv pip install sentence-transformers"
                ) from e
        return self._model

    def vectorize(self, text: str) -> list[float]:
        """Generate semantic embedding using SentenceBERT."""
        model = self._get_model()

        # Generate embedding
        embedding = model.encode(
            text, convert_to_tensor=False, normalize_embeddings=True
        )

        # Convert numpy array to list
        return embedding.tolist()

    def get_dimension(self) -> int:
        """Return vector dimension (384 for all-MiniLM-L6-v2)."""
        return 384

    def get_model_version(self) -> str:
        """Return model version identifier."""
        return f"sbert-{self._model_name}-v1.0"


class OpenAIVectorizer:
    """
    OpenAI embeddings vectorizer using text-embedding-3-small.

    High-quality embeddings for production use with API rate limiting
    and cost optimization.
    """

    def __init__(self):
        self._client = None
        self._model_name = "text-embedding-3-small"

    def _get_client(self):
        """Lazy load OpenAI client."""
        if self._client is None:
            try:
                from openai import OpenAI

                api_key = os.environ.get("OPENAI_API_KEY")
                if not api_key:
                    raise ValueError(
                        "OPENAI_API_KEY environment variable required "
                        "for OpenAI vectorizer"
                    )
                self._client = OpenAI(api_key=api_key)
            except ImportError as e:
                raise RuntimeError(
                    "openai package not installed. " "Run: uv pip install openai"
                ) from e
        return self._client

    def vectorize(self, text: str) -> list[float]:
        """Generate embedding using OpenAI API."""
        client = self._get_client()

        try:
            response = client.embeddings.create(
                model=self._model_name, input=text, encoding_format="float"
            )
            return response.data[0].embedding
        except Exception as e:
            raise RuntimeError(f"OpenAI API error: {str(e)}") from e

    def get_dimension(self) -> int:
        """Return vector dimension (1536 for text-embedding-3-small)."""
        return 1536

    def get_model_version(self) -> str:
        """Return model version identifier."""
        return f"openai-{self._model_name}-v1.0"


# Vectorizer instances for registry
stub_vectorizer = StubVectorizer()
sbert_vectorizer = SentenceBERTVectorizer()
openai_vectorizer = OpenAIVectorizer()
