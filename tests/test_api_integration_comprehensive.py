"""
Comprehensive API integration tests for all endpoints (Steps 1-9).

This test suite validates the complete API surface with realistic data flows,
ensuring all 21+ endpoints work correctly with proper error handling.
"""

from httpx import AsyncClient


class TestComprehensiveAPIIntegration:
    """
    Complete integration test suite covering all API endpoints from Steps 1-9.
    """

    # Test data for various item types
    SAMPLE_ITEMS = {
        "flashcard": {
            "type": "flashcard",
            "payload": {
                "front": "What is the capital of France?",
                "back": "Paris",
                "hints": ["It's known as the City of Light"],
                "examples": ["The Eiffel Tower is located here"],
            },
            "tags": ["geography", "capitals"],
            "difficulty": "intro",
        },
        "mcq": {
            "type": "mcq",
            "payload": {
                "stem": "Which of the following is the largest planet?",
                "options": [
                    {
                        "id": "a",
                        "text": "Mars",
                        "is_correct": False,
                        "rationale": "Mars is smaller than Earth",
                    },
                    {
                        "id": "b",
                        "text": "Jupiter",
                        "is_correct": True,
                        "rationale": "Jupiter is the largest planet",
                    },
                    {
                        "id": "c",
                        "text": "Venus",
                        "is_correct": False,
                        "rationale": "Venus is similar in size to Earth",
                    },
                    {
                        "id": "d",
                        "text": "Saturn",
                        "is_correct": False,
                        "rationale": "Saturn is smaller than Jupiter",
                    },
                ],
            },
            "tags": ["astronomy", "planets"],
            "difficulty": "core",
        },
        "cloze": {
            "type": "cloze",
            "payload": {
                "text": "The process of photosynthesis converts [[sunlight]] into [[energy]] for plants.",
                "blanks": [
                    {
                        "id": "1",
                        "answers": ["sunlight", "light"],
                        "case_sensitive": False,
                    },
                    {
                        "id": "2",
                        "answers": ["energy", "glucose"],
                        "case_sensitive": False,
                    },
                ],
                "context_note": "This is a fundamental biological process",
            },
            "tags": ["biology", "photosynthesis"],
            "difficulty": "core",
        },
        "short_answer": {
            "type": "short_answer",
            "payload": {
                "prompt": "What is the speed of light in vacuum?",
                "expected": {"value": "299792458", "unit": "m/s"},
                "acceptable_patterns": ["^299[,.]?792[,.]?458.*", "^3[.]?00?.*10.*8.*"],
            },
            "tags": ["physics", "constants"],
            "difficulty": "stretch",
        },
    }

    MARKDOWN_IMPORT_DATA = """
:::flashcard
Q: What is DNA?
A: Deoxyribonucleic acid, the molecule that carries genetic information
HINT: It's in the nucleus of cells
:::

:::mcq
STEM: Which base is NOT found in DNA?
A) Adenine
B) Thymine
C) Guanine
*D) Uracil
:::

:::cloze
TEXT: The structure of DNA was discovered by [[Watson]] and [[Crick]] in [[1953]].
:::
"""

    GENERATION_TEXT = """
Photosynthesis is the fundamental biological process by which plants convert sunlight into usable energy. This process occurs in specialized organelles called chloroplasts, which contain the green pigment chlorophyll. The overall equation for photosynthesis is 6CO2 + 6H2O + light energy → C6H12O6 + 6O2.

The process consists of two main stages: light-dependent reactions and the Calvin cycle. Light-dependent reactions occur in the thylakoid membranes where chlorophyll absorbs light energy at wavelengths around 680 nanometers and 700 nanometers. Water molecules are split during this process, releasing oxygen as a byproduct.

The Calvin cycle takes place in the stroma and uses the ATP and NADPH produced in the light reactions to fix carbon dioxide into glucose. This process requires approximately 18 ATP molecules and 12 NADPH molecules to produce one glucose molecule. The optimal temperature for photosynthesis is typically between 20-35 degrees Celsius, while light saturation occurs at around 2000 micromoles per square meter per second.

Photosynthetic efficiency varies among different plant species. C3 plants like wheat and rice have an efficiency of about 3-4%, while C4 plants like corn and sugarcane can achieve 4-5% efficiency. CAM plants like cacti and succulents have adapted to arid environments by opening their stomata at night to minimize water loss.

Environmental factors significantly affect photosynthetic rates. Carbon dioxide concentration plays a crucial role, with current atmospheric levels of 420 parts per million often being limiting. Temperature extremes below 0°C or above 45°C can denature enzymes involved in the process. Light intensity below 50 micromoles per square meter per second severely limits the rate of photosynthesis.
"""

    # Step 1: Health Endpoint Tests
    async def test_health_endpoint(self, async_client: AsyncClient):
        """Test the health endpoint returns proper status."""
        response = await async_client.get("/v1/healthz")
        assert response.status_code == 200

        data = response.json()
        assert data["ok"] is True
        assert "version" in data
        assert "environment" in data

    # Step 2: Items CRUD Tests
    async def test_create_items_all_types(self, async_client: AsyncClient):
        """Test creating items of all supported types."""
        created_items = []

        for item_type, item_data in self.SAMPLE_ITEMS.items():
            response = await async_client.post("/v1/items", json=item_data)
            assert (
                response.status_code == 201
            ), f"Failed to create {item_type}: {response.text}"

            item = response.json()
            assert item["data"]["type"] == item_type
            assert item["data"]["status"] == "draft"
            assert item["data"]["payload"] == item_data["payload"]
            assert item["data"]["tags"] == item_data["tags"]

            created_items.append(item["data"])

        return created_items

    async def test_list_items_with_filters(self, async_client: AsyncClient):
        """Test item listing with various filters."""
        # First create some items
        await self.test_create_items_all_types(async_client)

        # Test basic listing
        response = await async_client.get("/v1/items")
        assert response.status_code == 200
        items = response.json()
        assert len(items["data"]["items"]) >= 4

        # Test type filtering
        response = await async_client.get("/v1/items?type=flashcard")
        assert response.status_code == 200
        items = response.json()
        assert all(item["type"] == "flashcard" for item in items["data"]["items"])

        # Test tag filtering
        response = await async_client.get("/v1/items?tags=geography")
        assert response.status_code == 200
        items = response.json()
        assert all("geography" in item["tags"] for item in items["data"]["items"])

        # Test difficulty filtering
        response = await async_client.get("/v1/items?difficulty=core")
        assert response.status_code == 200
        items = response.json()
        assert all(item["difficulty"] == "core" for item in items["data"]["items"])

    async def test_item_search_functionality(self, async_client: AsyncClient):
        """Test search functionality (Step 7)."""
        # Create items first
        await self.test_create_items_all_types(async_client)

        # Test keyword search
        response = await async_client.get("/v1/items?q=Paris")
        assert response.status_code == 200
        items = response.json()
        assert len(items["data"]["items"]) >= 1

        # Test search with no results
        response = await async_client.get("/v1/items?q=nonexistentterm12345")
        assert response.status_code == 200
        items = response.json()
        assert len(items["data"]["items"]) == 0

    async def test_individual_item_operations(self, async_client: AsyncClient):
        """Test individual item CRUD operations."""
        # Create an item
        flashcard_data = self.SAMPLE_ITEMS["flashcard"]
        create_response = await async_client.post("/v1/items", json=flashcard_data)
        assert create_response.status_code == 201

        item_id = create_response.json()["data"]["id"]

        # Get individual item
        response = await async_client.get(f"/v1/items/{item_id}")
        assert response.status_code == 200
        item = response.json()
        assert item["data"]["id"] == item_id

        # Update item
        update_data = {"tags": ["updated", "geography"]}
        response = await async_client.patch(f"/v1/items/{item_id}", json=update_data)
        assert response.status_code == 200
        updated_item = response.json()
        assert "updated" in updated_item["data"]["tags"]

        # Test item rendering
        response = await async_client.post(f"/v1/items/{item_id}/render")
        assert response.status_code == 200
        render_data = response.json()
        assert "data" in render_data

        # Delete item (soft delete)
        response = await async_client.delete(f"/v1/items/{item_id}")
        assert response.status_code == 204

        # Verify item is soft-deleted
        response = await async_client.get(f"/v1/items/{item_id}")
        assert response.status_code == 404

    # Step 3: Import System Tests
    async def test_markdown_import_workflow(self, async_client: AsyncClient):
        """Test the complete markdown import workflow."""
        # Import markdown
        import_data = {"format": "markdown", "data": self.MARKDOWN_IMPORT_DATA}

        response = await async_client.post("/v1/items/import", json=import_data)
        assert response.status_code == 200

        result = response.json()["data"]
        assert len(result["staged_ids"]) == 3
        assert len(result["warnings"]) == 0

        staged_ids = result["staged_ids"]

        # Check staged items
        response = await async_client.get("/v1/items/staged")
        assert response.status_code == 200
        staged = response.json()
        assert len(staged["data"]["items"]) >= 3

        # Approve some items
        approval_data = {"ids": staged_ids[:2]}
        response = await async_client.post("/v1/items/approve", json=approval_data)
        assert response.status_code == 200

        approval_result = response.json()["data"]
        assert len(approval_result["approved"]) == 2
        assert len(approval_result["skipped"]) == 0

        return staged_ids

    # Step 4: Review System Tests
    async def test_review_queue_functionality(self, async_client: AsyncClient):
        """Test the review queue and recording system."""
        # First import and approve some items
        staged_ids = await self.test_markdown_import_workflow(async_client)

        # Get review queue
        response = await async_client.get("/v1/queue")
        assert response.status_code == 200

        queue = response.json()["data"]
        assert "new" in queue
        assert "due" in queue
        assert len(queue["new"]) >= 2  # Items we approved

        # Record a review for a new item
        if queue["new"]:
            item_id = queue["new"][0]["id"]
            review_data = {
                "item_id": item_id,
                "rating": 3,  # Good
                "correct": True,
                "latency_ms": 2500,
                "mode": "review",
            }

            response = await async_client.post("/v1/record", json=review_data)
            assert response.status_code == 200

            result = response.json()["data"]
            assert "updated_state" in result
            assert result["updated_state"]["reps"] == 1

    # Step 5: Quiz System Tests
    async def test_quiz_complete_workflow(self, async_client: AsyncClient):
        """Test the complete quiz workflow."""
        # Ensure we have approved items
        await self.test_markdown_import_workflow(async_client)

        # Start a drill quiz
        quiz_params = {
            "mode": "drill",
            "params": {"length": 3, "tags": ["biology"], "time_limit_s": 300},
        }

        response = await async_client.post("/v1/quiz/start", json=quiz_params)
        assert response.status_code == 200

        quiz_data = response.json()["data"]
        quiz_id = quiz_data["quiz_id"]
        items = quiz_data["items"]

        assert len(items) <= 3
        assert quiz_id is not None

        # Submit answers for quiz items
        for item in items:
            if item["type"] == "mcq":
                submit_data = {
                    "quiz_id": quiz_id,
                    "item_id": item["id"],
                    "response": {"selected_options": ["d"]},  # Uracil is not in DNA
                }
            elif item["type"] == "flashcard":
                submit_data = {
                    "quiz_id": quiz_id,
                    "item_id": item["id"],
                    "response": {"rating": 4},
                }
            else:  # cloze or others
                submit_data = {
                    "quiz_id": quiz_id,
                    "item_id": item["id"],
                    "response": {"answers": {"1": "Watson", "2": "Crick", "3": "1953"}},
                }

            response = await async_client.post("/v1/quiz/submit", json=submit_data)
            assert response.status_code == 200

        # Finish the quiz
        finish_data = {"quiz_id": quiz_id}
        response = await async_client.post("/v1/quiz/finish", json=finish_data)
        assert response.status_code == 200

        result = response.json()["data"]
        assert "score" in result
        assert "breakdown" in result

        return quiz_id

    # Step 6: Progress Analytics Tests
    async def test_progress_analytics(self, async_client: AsyncClient):
        """Test progress analytics endpoints."""
        # Generate some activity first
        await self.test_review_queue_functionality(async_client)
        await self.test_quiz_complete_workflow(async_client)

        # Test overview
        response = await async_client.get("/v1/progress/overview")
        assert response.status_code == 200

        overview = response.json()["data"]
        expected_keys = [
            "attempts_7d",
            "accuracy_7d",
            "avg_latency_ms_7d",
            "streak_days",
            "total_items",
            "reviewed_items",
        ]
        for key in expected_keys:
            assert key in overview

        # Test weak areas
        response = await async_client.get("/v1/progress/weak_areas?top=5")
        assert response.status_code == 200

        weak_areas = response.json()["data"]
        assert "tags" in weak_areas
        assert "types" in weak_areas
        assert "difficulty" in weak_areas

        # Test forecast
        response = await async_client.get("/v1/progress/forecast?days=7")
        assert response.status_code == 200

        forecast = response.json()["data"]
        assert "by_day" in forecast
        assert len(forecast["by_day"]) == 7

    # Step 8: Embeddings and Similar Items Tests
    async def test_embeddings_and_similarity(self, async_client: AsyncClient):
        """Test embeddings and similarity functionality."""
        # Create some similar items
        items = await self.test_create_items_all_types(async_client)
        item_id = items[0]["id"]

        # Test compute embedding
        response = await async_client.post(f"/v1/items/{item_id}/compute-embedding")
        assert response.status_code == 200

        result = response.json()["data"]
        assert "embedding_created" in result

        # Test similar items
        response = await async_client.get(f"/v1/items/{item_id}/similar")
        assert response.status_code == 200

        similar = response.json()["data"]
        assert isinstance(similar, list)

        # Test embedding stats
        response = await async_client.get("/v1/items/embedding-stats")
        assert response.status_code == 200

        stats = response.json()["data"]
        assert "total_items" in stats
        assert "items_with_embeddings" in stats

    # Step 9: Content Generation Tests
    async def test_content_generation(self, async_client: AsyncClient):
        """Test content generation functionality."""
        # List available generators
        response = await async_client.get("/v1/generators")
        assert response.status_code == 200

        generators = response.json()["data"]
        assert "basic_rules" in generators

        # Get generator info
        response = await async_client.get("/v1/generators/basic_rules/info")
        assert response.status_code == 200

        info = response.json()["data"]
        assert info["name"] == "basic_rules"
        assert info["type"] == "rule_based"

        # Generate content
        generation_request = {
            "text": self.GENERATION_TEXT,
            "types": ["flashcard", "mcq", "cloze"],
            "count": 10,
            "difficulty": "core",
        }

        response = await async_client.post(
            "/v1/items/generate", json=generation_request
        )
        assert response.status_code == 200

        result = response.json()["data"]
        assert "generated" in result
        assert "rejected" in result
        assert "diagnostics" in result
        assert "warnings" in result

        # Should generate multiple items
        assert len(result["generated"]) >= 5
        assert result["diagnostics"]["final_count"] >= 5

        # Items should be diverse types
        generated_types = {item["type"] for item in result["generated"]}
        assert len(generated_types) >= 2

    # Error Handling and Edge Cases
    async def test_error_handling(self, async_client: AsyncClient):
        """Test proper error handling across endpoints."""
        # Test 404s
        response = await async_client.get("/v1/items/nonexistent-id")
        assert response.status_code == 404

        # Test invalid item creation
        invalid_item = {"type": "invalid_type", "payload": {}}
        response = await async_client.post("/v1/items", json=invalid_item)
        assert response.status_code == 400

        # Test invalid import data
        response = await async_client.post(
            "/v1/items/import", json={"format": "markdown", "data": ""}
        )
        assert response.status_code == 400

        # Test invalid generation request
        response = await async_client.post(
            "/v1/items/generate", json={"count": 1000}
        )  # No text/topic
        assert response.status_code == 400

    # Performance Tests
    async def test_performance_requirements(self, async_client: AsyncClient):
        """Test that endpoints meet performance requirements."""
        import time

        # Set up some data
        await self.test_review_queue_functionality(async_client)

        # Test analytics endpoints are under 1 second
        start_time = time.time()
        response = await async_client.get("/v1/progress/overview")
        duration = time.time() - start_time

        assert response.status_code == 200
        assert duration < 1.0, f"Overview took {duration:.2f}s, should be <1s"

        # Test forecast endpoint
        start_time = time.time()
        response = await async_client.get("/v1/progress/forecast?days=30")
        duration = time.time() - start_time

        assert response.status_code == 200
        assert duration < 1.0, f"Forecast took {duration:.2f}s, should be <1s"
