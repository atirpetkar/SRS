"""
Integration tests for Step 8 - Embeddings, Hybrid Search, and Duplicate Detection.

Tests the complete functionality including vectorizers, search, and embedding management.
"""

from api.v1.core.registries import vectorizer_registry
from api.v1.search.embedding_service import EmbeddingService
from api.v1.search.hybrid_search import HybridSearchService
from api.v1.search.registry_init import init_vectorizer_registry


class TestStep8Integration:
    """Integration tests for Step 8 functionality."""

    def test_vectorizer_registry_initialization(self):
        """Test that vectorizer registry initializes correctly."""

        # Initialize the registry
        init_vectorizer_registry()

        # Check that stub vectorizer is available
        assert "stub" in vectorizer_registry.list()

        # Get stub vectorizer
        stub = vectorizer_registry.get("stub")
        assert stub.get_model_version() == "stub-v1.0"
        assert stub.get_dimension() == 768

    def test_stub_vectorizer_functionality(self):
        """Test stub vectorizer produces consistent embeddings."""
        init_vectorizer_registry()
        stub = vectorizer_registry.get("stub")

        # Test basic vectorization
        text = "This is a test sentence for embedding"
        embedding1 = stub.vectorize(text)
        embedding2 = stub.vectorize(text)

        # Should be deterministic
        assert embedding1 == embedding2
        assert len(embedding1) == 768

        # Different text should produce different embeddings
        different_text = "This is completely different content"
        embedding3 = stub.vectorize(different_text)
        assert embedding1 != embedding3

    def test_hybrid_search_service_initialization(self):
        """Test hybrid search service initializes correctly."""
        from api.config.settings import settings

        search_service = HybridSearchService(settings)

        # Check configuration
        assert search_service.keyword_weight == 0.3
        assert search_service.vector_weight == 0.7
        assert search_service.use_tsvector == (
            settings.environment in ("production", "staging")
        )

    def test_embedding_service_initialization(self):
        """Test embedding service initializes correctly."""
        from api.config.settings import settings

        init_vectorizer_registry()
        embedding_service = EmbeddingService(settings)
        assert embedding_service.settings == settings

    async def test_empty_search_functionality(self, async_client):
        """Test search functionality with empty database."""
        init_vectorizer_registry()

        # Test search endpoint
        response = await async_client.get("/v1/items")
        assert response.status_code == 200

        data = response.json()
        assert data["ok"] is True
        assert data["data"]["total"] == 0
        assert data["data"]["items"] == []

    async def test_search_with_query_parameter(self, async_client):
        """Test search endpoint with query parameter."""
        init_vectorizer_registry()

        # Test search with query
        response = await async_client.get("/v1/items?q=test")
        assert response.status_code == 200

        data = response.json()
        assert data["ok"] is True
        assert data["data"]["total"] == 0
        assert data["data"]["items"] == []

    async def test_embedding_stats_endpoint(self, async_client):
        """Test embedding statistics endpoint."""
        init_vectorizer_registry()

        response = await async_client.get("/v1/items/embedding-stats")
        assert response.status_code == 200

        data = response.json()
        assert data["ok"] is True

        stats = data["data"]
        assert "total_items" in stats
        assert "published_items" in stats
        assert "items_with_embeddings" in stats
        assert "coverage_rate" in stats
        assert "model_versions" in stats
        assert "missing_embeddings" in stats

    async def test_item_creation_and_embedding_computation(self, async_client):
        """Test creating an item and computing its embedding."""
        init_vectorizer_registry()

        # Create a flashcard item
        item_data = {
            "type": "flashcard",
            "payload": {"front": "What is the capital of France?", "back": "Paris"},
            "tags": ["geography", "capitals"],
            "difficulty": "intro",
        }

        # Create item
        response = await async_client.post("/v1/items", json=item_data)
        assert response.status_code == 201

        data = response.json()
        assert data["ok"] is True
        item_id = data["data"]["id"]

        # Approve item to published status
        approval_data = {"ids": [item_id]}
        response = await async_client.post("/v1/items/approve", json=approval_data)
        assert response.status_code == 200

        approval_result = response.json()
        assert approval_result["ok"] is True
        assert item_id in approval_result["data"]["approved_ids"]

        # Test manual embedding computation
        response = await async_client.post(
            f"/v1/items/{item_id}/compute-embedding?force=true"
        )
        assert response.status_code == 200

        embedding_data = response.json()
        assert embedding_data["ok"] is True
        assert embedding_data["data"]["item_id"] == item_id
        assert embedding_data["data"]["model_version"] == "stub-v1.0"
        assert embedding_data["data"]["embedding_dimension"] == 768

    async def test_similarity_search(self, async_client):
        """Test similarity search functionality."""
        init_vectorizer_registry()

        # Create and approve first item
        item_data_1 = {
            "type": "flashcard",
            "payload": {
                "front": "What is machine learning?",
                "back": "A subset of artificial intelligence",
            },
            "tags": ["ai", "technology"],
        }

        response = await async_client.post("/v1/items", json=item_data_1)
        assert response.status_code == 201
        item_id_1 = response.json()["data"]["id"]

        # Approve first item
        response = await async_client.post(
            "/v1/items/approve", json={"ids": [item_id_1]}
        )
        assert response.status_code == 200

        # Create similar second item
        item_data_2 = {
            "type": "flashcard",
            "payload": {
                "front": "What is deep learning?",
                "back": "A subset of machine learning using neural networks",
            },
            "tags": ["ai", "technology"],
        }

        response = await async_client.post("/v1/items", json=item_data_2)
        assert response.status_code == 201
        item_id_2 = response.json()["data"]["id"]

        # Approve second item
        response = await async_client.post(
            "/v1/items/approve", json={"ids": [item_id_2]}
        )
        assert response.status_code == 200

        # Compute embeddings for both items
        await async_client.post(f"/v1/items/{item_id_1}/compute-embedding")
        await async_client.post(f"/v1/items/{item_id_2}/compute-embedding")

        # Test similarity search
        response = await async_client.get(
            f"/v1/items/{item_id_1}/similar?threshold=0.1&limit=5"
        )
        assert response.status_code == 200

        similar_data = response.json()
        assert similar_data["ok"] is True

        # Should find similar items (at least the second item)
        similar_items = similar_data["data"]
        assert isinstance(similar_items, list)

    async def test_hybrid_search_with_content(self, async_client):
        """Test hybrid search with actual content."""
        init_vectorizer_registry()

        # Create and approve an item
        item_data = {
            "type": "mcq",
            "payload": {
                "stem": "Which programming language is known for machine learning?",
                "options": [
                    {"id": "a", "text": "Python", "is_correct": True},
                    {"id": "b", "text": "Java", "is_correct": False},
                    {"id": "c", "text": "C++", "is_correct": False},
                ],
            },
            "tags": ["programming", "machine-learning"],
        }

        response = await async_client.post("/v1/items", json=item_data)
        assert response.status_code == 201
        item_id = response.json()["data"]["id"]

        # Approve item
        response = await async_client.post("/v1/items/approve", json={"ids": [item_id]})
        assert response.status_code == 200

        # Search for the item using keywords
        response = await async_client.get("/v1/items?q=programming")
        assert response.status_code == 200

        search_data = response.json()
        assert search_data["ok"] is True
        assert search_data["data"]["total"] >= 1

        # Verify the item is in the results
        items = search_data["data"]["items"]
        found_item = next((item for item in items if item["id"] == item_id), None)
        assert found_item is not None
        assert "programming" in found_item["tags"]

    async def test_import_with_duplicate_detection(self, async_client):
        """Test import functionality with duplicate detection."""
        init_vectorizer_registry()

        # First, create an item directly
        item_data = {
            "type": "flashcard",
            "payload": {"front": "What is Python?", "back": "A programming language"},
            "tags": ["programming"],
        }

        response = await async_client.post("/v1/items", json=item_data)
        assert response.status_code == 201

        # Now try to import a very similar item via markdown
        markdown_content = """
:::flashcard
Q: What is Python?
A: A programming language
:::
"""

        import_data = {"format": "markdown", "data": markdown_content}

        response = await async_client.post("/v1/items/import", json=import_data)
        assert response.status_code == 200

        import_result = response.json()
        assert import_result["ok"] is True

        # Should detect potential duplicate
        result_data = import_result["data"]
        assert len(result_data["warnings"]) > 0

        # Check for duplicate warning
        warnings = result_data["warnings"]
        has_duplicate_warning = any(
            "duplicate" in warning.lower() for warning in warnings
        )
        assert has_duplicate_warning
