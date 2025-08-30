from uuid import uuid4

from fastapi.testclient import TestClient


class TestItems:
    """Test suite for item CRUD operations."""

    def test_create_flashcard_item(self, client: TestClient):
        """Test creating a valid flashcard item."""
        payload = {
            "type": "flashcard",
            "payload": {
                "front": "What is the capital of France?",
                "back": "Paris",
                "hints": ["It's a city of love"],
                "examples": ["Paris is known for the Eiffel Tower"],
            },
            "tags": ["geography", "capitals"],
            "difficulty": "intro",
        }

        response = client.post("/v1/items", json=payload)
        assert response.status_code == 201

        data = response.json()
        assert data["type"] == "flashcard"
        assert data["payload"]["front"] == "What is the capital of France?"
        assert data["payload"]["back"] == "Paris"
        assert data["tags"] == ["capitals", "geography"]  # Should be sorted
        assert data["difficulty"] == "intro"
        assert data["status"] == "draft"
        assert data["content_hash"] is not None
        assert data["org_id"] is not None  # UUID generated from DEV_ORG

    def test_create_mcq_item(self, client: TestClient):
        """Test creating a valid MCQ item."""
        payload = {
            "type": "mcq",
            "payload": {
                "stem": "Which planet is closest to the Sun?",
                "options": [
                    {"id": "a", "text": "Venus", "is_correct": False},
                    {
                        "id": "b",
                        "text": "Mercury",
                        "is_correct": True,
                        "rationale": "Mercury is indeed closest",
                    },
                    {"id": "c", "text": "Earth", "is_correct": False},
                    {"id": "d", "text": "Mars", "is_correct": False},
                ],
            },
            "tags": ["astronomy", "planets"],
        }

        response = client.post("/v1/items", json=payload)
        assert response.status_code == 201

        data = response.json()
        assert data["type"] == "mcq"
        assert len(data["payload"]["options"]) == 4
        assert data["payload"]["stem"] == "Which planet is closest to the Sun?"

    def test_create_cloze_item(self, client: TestClient):
        """Test creating a valid cloze deletion item."""
        payload = {
            "type": "cloze",
            "payload": {
                "text": "The capital of {{c1::France}} is {{c2::Paris}}.",
                "blanks": [
                    {
                        "id": "c1",
                        "answers": ["France"],
                        "alt_answers": ["france"],
                        "case_sensitive": False,
                    },
                    {"id": "c2", "answers": ["Paris"], "case_sensitive": False},
                ],
                "context_note": "European geography",
            },
            "tags": ["geography"],
        }

        response = client.post("/v1/items", json=payload)
        assert response.status_code == 201

        data = response.json()
        assert data["type"] == "cloze"
        assert len(data["payload"]["blanks"]) == 2

    def test_create_short_answer_item(self, client: TestClient):
        """Test creating a valid short answer item."""
        payload = {
            "type": "short_answer",
            "payload": {
                "prompt": "What is 2 + 2?",
                "expected": {"value": "4"},
                "acceptable_patterns": ["^4$", "^four$"],
                "grading": {"method": "regex"},
            },
        }

        response = client.post("/v1/items", json=payload)
        assert response.status_code == 201

        data = response.json()
        assert data["type"] == "short_answer"
        assert data["payload"]["prompt"] == "What is 2 + 2?"

    def test_create_item_invalid_type(self, client: TestClient):
        """Test creating an item with invalid type."""
        payload = {"type": "invalid_type", "payload": {"test": "data"}}

        response = client.post("/v1/items", json=payload)
        assert response.status_code == 422  # Pydantic validation error
        # Check that the error mentions the invalid type
        error_detail = response.json()["detail"]
        assert any("invalid_type" in str(error).lower() for error in error_detail)

    def test_create_item_invalid_payload(self, client: TestClient):
        """Test creating an item with invalid payload."""
        payload = {
            "type": "flashcard",
            "payload": {"front": "", "back": "answer"},  # Invalid: empty string
        }

        response = client.post("/v1/items", json=payload)
        assert response.status_code == 400

    def test_list_items_empty(self, client: TestClient):
        """Test listing items when none exist."""
        response = client.get("/v1/items")
        assert response.status_code == 200

        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["has_more"] is False

    def test_list_items_with_filters(self, client: TestClient):
        """Test listing items with various filters."""
        # Create some test items
        client.post(
            "/v1/items",
            json={
                "type": "flashcard",
                "payload": {"front": "Q1", "back": "A1"},
                "tags": ["test", "math"],
                "difficulty": "intro",
            },
        )

        client.post(
            "/v1/items",
            json={
                "type": "mcq",
                "payload": {
                    "stem": "Question 2",
                    "options": [
                        {"id": "a", "text": "Option A", "is_correct": True},
                        {"id": "b", "text": "Option B", "is_correct": False},
                    ],
                },
                "tags": ["test", "science"],
                "difficulty": "core",
            },
        )

        # Test filter by type
        response = client.get("/v1/items?type=flashcard")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["type"] == "flashcard"

        # Test filter by tags
        response = client.get("/v1/items?tags=math")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1

        # Test filter by difficulty
        response = client.get("/v1/items?difficulty=core")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["difficulty"] == "core"

    def test_get_item_by_id(self, client: TestClient):
        """Test retrieving a specific item by ID."""
        # Create an item first
        create_response = client.post(
            "/v1/items",
            json={
                "type": "flashcard",
                "payload": {"front": "Test Question", "back": "Test Answer"},
            },
        )
        item_id = create_response.json()["id"]

        # Get the item
        response = client.get(f"/v1/items/{item_id}")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == item_id
        assert data["type"] == "flashcard"

    def test_get_nonexistent_item(self, client: TestClient):
        """Test retrieving a non-existent item."""
        fake_id = str(uuid4())
        response = client.get(f"/v1/items/{fake_id}")
        assert response.status_code == 404

    def test_update_item(self, client: TestClient):
        """Test updating an existing item."""
        # Create an item first
        create_response = client.post(
            "/v1/items",
            json={
                "type": "flashcard",
                "payload": {"front": "Original Question", "back": "Original Answer"},
                "tags": ["original"],
                "difficulty": "intro",
            },
        )
        item_id = create_response.json()["id"]
        original_version = create_response.json()["version"]

        # Update the item
        update_data = {
            "payload": {"front": "Updated Question", "back": "Updated Answer"},
            "tags": ["updated", "modified"],
            "difficulty": "core",
            "status": "published",
        }

        response = client.patch(f"/v1/items/{item_id}", json=update_data)
        assert response.status_code == 200

        data = response.json()
        assert data["payload"]["front"] == "Updated Question"
        assert data["tags"] == ["modified", "updated"]  # Sorted
        assert data["difficulty"] == "core"
        assert data["status"] == "published"
        assert data["version"] > original_version  # Version should increment

    def test_delete_item(self, client: TestClient):
        """Test soft deleting an item."""
        # Create an item first
        create_response = client.post(
            "/v1/items",
            json={
                "type": "flashcard",
                "payload": {"front": "To Delete", "back": "Will be deleted"},
            },
        )
        item_id = create_response.json()["id"]

        # Delete the item
        response = client.delete(f"/v1/items/{item_id}")
        assert response.status_code == 204

        # Verify it's no longer accessible
        response = client.get(f"/v1/items/{item_id}")
        assert response.status_code == 404

    def test_render_item(self, client: TestClient):
        """Test rendering an item for display."""
        # Create an item first
        create_response = client.post(
            "/v1/items",
            json={
                "type": "flashcard",
                "payload": {
                    "front": "Render Test",
                    "back": "Rendered Answer",
                    "examples": ["Example 1"],
                },
            },
        )
        item_id = create_response.json()["id"]

        # Render the item
        response = client.post(f"/v1/items/{item_id}/render")
        assert response.status_code == 200

        data = response.json()
        assert data["type"] == "flashcard"
        assert data["front"] == "Render Test"
        assert data["back"] == "Rendered Answer"
        assert data["has_examples"] is True

    def test_org_isolation(self, client: TestClient):
        """Test that items are isolated by organization."""
        # This test assumes we can somehow change the org context
        # For now, it just verifies that all created items belong to DEV_ORG

        # Create an item
        response = client.post(
            "/v1/items",
            json={
                "type": "flashcard",
                "payload": {"front": "Org Test", "back": "Answer"},
            },
        )

        data = response.json()
        assert data["org_id"] is not None  # UUID generated from DEV_ORG
        dev_org_uuid = data["org_id"]

        # List items should only return items from the same org
        response = client.get("/v1/items")
        items = response.json()["items"]

        for item in items:
            assert item["org_id"] == dev_org_uuid

    def test_content_hash_generation(self, client: TestClient):
        """Test that content hashes are generated correctly."""
        payload1 = {
            "type": "flashcard",
            "payload": {"front": "Question", "back": "Answer"},
            "tags": ["test"],
        }

        payload2 = {
            "type": "flashcard",
            "payload": {"front": "Question", "back": "Answer"},
            "tags": ["different"],  # Different tags but same content
        }

        # Create two items
        response1 = client.post("/v1/items", json=payload1)
        response2 = client.post("/v1/items", json=payload2)

        data1 = response1.json()
        data2 = response2.json()

        # Should have the same content hash (tags don't affect content hash)
        assert data1["content_hash"] == data2["content_hash"]

        # But different IDs
        assert data1["id"] != data2["id"]
