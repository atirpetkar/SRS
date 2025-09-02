"""
Security and data isolation tests.

These tests verify that:
1. All data access is properly org-scoped
2. Users cannot access data from other organizations
3. Cross-org access returns appropriate errors
4. Principal-based security works correctly
"""

import pytest

from api.v1.core.security import Principal


class TestSecurityAndDataIsolation:
    """Test security and data isolation across organizations."""

    # Test data for two different organizations
    ORG_A_DATA = {
        "items": [
            {
                "type": "flashcard",
                "payload": {"front": "Org A Question 1", "back": "Org A Answer 1"},
                "tags": ["org-a", "test"],
                "difficulty": "intro",
            },
            {
                "type": "mcq",
                "payload": {
                    "stem": "Org A MCQ Question",
                    "options": [
                        {"id": "a", "text": "Wrong A", "is_correct": False},
                        {"id": "b", "text": "Correct A", "is_correct": True},
                    ],
                },
                "tags": ["org-a", "mcq"],
                "difficulty": "core",
            },
        ],
        "markdown": """
:::flashcard
Q: Org A specific question
A: Org A specific answer
:::

:::cloze
TEXT: This is [[Org A]] content for [[testing]].
:::
""",
    }

    ORG_B_DATA = {
        "items": [
            {
                "type": "flashcard",
                "payload": {"front": "Org B Question 1", "back": "Org B Answer 1"},
                "tags": ["org-b", "test"],
                "difficulty": "intro",
            },
            {
                "type": "short_answer",
                "payload": {
                    "prompt": "Org B specific calculation",
                    "expected": {"value": "42", "unit": "units"},
                    "acceptable_patterns": ["42.*"],
                },
                "tags": ["org-b", "math"],
                "difficulty": "stretch",
            },
        ],
        "markdown": """
:::flashcard
Q: Org B specific question  
A: Org B specific answer
:::

:::mcq
STEM: Org B MCQ question
*A) Correct B
B) Wrong B
:::
""",
    }

    @pytest.fixture
    def org_a_client(self, app):
        """Create a client authenticated as Org A user."""
        from fastapi.testclient import TestClient

        from api.v1.core.security import get_principal

        def get_org_a_principal():
            return Principal(
                user_id="user_a_123",
                org_id="org_a_456",
                roles=["admin"],
                email="user_a@orga.com",
            )

        app.dependency_overrides[get_principal] = get_org_a_principal

        with TestClient(app) as client:
            yield client

    @pytest.fixture
    def org_b_client(self, app):
        """Create a client authenticated as Org B user."""
        from fastapi.testclient import TestClient

        from api.v1.core.security import get_principal

        def get_org_b_principal():
            return Principal(
                user_id="user_b_789",
                org_id="org_b_012",
                roles=["admin"],
                email="user_b@orgb.com",
            )

        app.dependency_overrides[get_principal] = get_org_b_principal

        with TestClient(app) as client:
            yield client

    async def test_item_creation_isolation(self, org_a_client, org_b_client):
        """Test that items are created with correct org isolation."""

        # Org A creates items
        org_a_items = []
        for item_data in self.ORG_A_DATA["items"]:
            response = org_a_client.post("/v1/items", json=item_data)
            assert response.status_code == 201

            item = response.json()["data"]
            org_a_items.append(item["id"])

            # Verify org context is correctly set (this would be done by the API)
            assert item["tags"] == item_data["tags"]

        # Org B creates items
        org_b_items = []
        for item_data in self.ORG_B_DATA["items"]:
            response = org_b_client.post("/v1/items", json=item_data)
            assert response.status_code == 201

            item = response.json()["data"]
            org_b_items.append(item["id"])

        # Org A should only see their items
        response = org_a_client.get("/v1/items")
        assert response.status_code == 200

        org_a_visible_items = response.json()["data"]["items"]
        org_a_visible_ids = {item["id"] for item in org_a_visible_items}

        # Verify Org A sees their items but not Org B's
        for item_id in org_a_items:
            assert item_id in org_a_visible_ids

        for item_id in org_b_items:
            assert item_id not in org_a_visible_ids

        # Org B should only see their items
        response = org_b_client.get("/v1/items")
        assert response.status_code == 200

        org_b_visible_items = response.json()["data"]["items"]
        org_b_visible_ids = {item["id"] for item in org_b_visible_items}

        # Verify Org B sees their items but not Org A's
        for item_id in org_b_items:
            assert item_id in org_b_visible_ids

        for item_id in org_a_items:
            assert item_id not in org_b_visible_ids

    async def test_cross_org_item_access_denied(self, org_a_client, org_b_client):
        """Test that cross-org direct item access is denied."""

        # Org A creates an item
        item_data = self.ORG_A_DATA["items"][0]
        response = org_a_client.post("/v1/items", json=item_data)
        assert response.status_code == 201

        org_a_item_id = response.json()["data"]["id"]

        # Org A can access their own item
        response = org_a_client.get(f"/v1/items/{org_a_item_id}")
        assert response.status_code == 200

        # Org B cannot access Org A's item
        response = org_b_client.get(f"/v1/items/{org_a_item_id}")
        assert response.status_code == 404  # Should appear as if item doesn't exist

        # Org B cannot modify Org A's item
        update_data = {"tags": ["hacked"]}
        response = org_b_client.patch(f"/v1/items/{org_a_item_id}", json=update_data)
        assert response.status_code == 404

        # Org B cannot delete Org A's item
        response = org_b_client.delete(f"/v1/items/{org_a_item_id}")
        assert response.status_code == 404

    async def test_import_and_staging_isolation(self, org_a_client, org_b_client):
        """Test that import/staging operations are org-isolated."""

        # Org A imports content
        import_data_a = {"format": "markdown", "data": self.ORG_A_DATA["markdown"]}

        response = org_a_client.post("/v1/items/import", json=import_data_a)
        assert response.status_code == 200

        org_a_staged = response.json()["data"]["staged_ids"]

        # Org B imports content
        import_data_b = {"format": "markdown", "data": self.ORG_B_DATA["markdown"]}

        response = org_b_client.post("/v1/items/import", json=import_data_b)
        assert response.status_code == 200

        org_b_staged = response.json()["data"]["staged_ids"]

        # Org A should only see their staged items
        response = org_a_client.get("/v1/items/staged")
        assert response.status_code == 200

        org_a_staged_items = response.json()["data"]["items"]
        org_a_staged_ids = {item["id"] for item in org_a_staged_items}

        for staged_id in org_a_staged:
            assert staged_id in org_a_staged_ids

        for staged_id in org_b_staged:
            assert staged_id not in org_a_staged_ids

        # Org B should only see their staged items
        response = org_b_client.get("/v1/items/staged")
        assert response.status_code == 200

        org_b_staged_items = response.json()["data"]["items"]
        org_b_staged_ids = {item["id"] for item in org_b_staged_items}

        for staged_id in org_b_staged:
            assert staged_id in org_b_staged_ids

        for staged_id in org_a_staged:
            assert staged_id not in org_b_staged_ids

    async def test_cross_org_approval_denied(self, org_a_client, org_b_client):
        """Test that users cannot approve items from other orgs."""

        # Org A imports and gets staged items
        import_data = {"format": "markdown", "data": self.ORG_A_DATA["markdown"]}

        response = org_a_client.post("/v1/items/import", json=import_data)
        assert response.status_code == 200

        org_a_staged = response.json()["data"]["staged_ids"]

        # Org B tries to approve Org A's staged items
        approval_data = {"ids": org_a_staged}
        response = org_b_client.post("/v1/items/approve", json=approval_data)
        assert response.status_code == 200

        result = response.json()["data"]
        # Should skip all items as they belong to different org
        assert len(result["approved"]) == 0
        assert len(result["skipped"]) == len(org_a_staged)

    async def test_review_queue_isolation(self, org_a_client, org_b_client):
        """Test that review queues are org-specific."""

        # Setup: Create and approve items for both orgs
        # Org A setup
        for item_data in self.ORG_A_DATA["items"]:
            response = org_a_client.post("/v1/items", json=item_data)
            assert response.status_code == 201

        # Approve Org A items
        response = org_a_client.get("/v1/items?status=draft")
        assert response.status_code == 200

        org_a_drafts = response.json()["data"]["items"]
        if org_a_drafts:
            approval_data = {"ids": [item["id"] for item in org_a_drafts]}
            response = org_a_client.post("/v1/items/approve", json=approval_data)
            assert response.status_code == 200

        # Org B setup
        for item_data in self.ORG_B_DATA["items"]:
            response = org_b_client.post("/v1/items", json=item_data)
            assert response.status_code == 201

        # Approve Org B items
        response = org_b_client.get("/v1/items?status=draft")
        assert response.status_code == 200

        org_b_drafts = response.json()["data"]["items"]
        if org_b_drafts:
            approval_data = {"ids": [item["id"] for item in org_b_drafts]}
            response = org_b_client.post("/v1/items/approve", json=approval_data)
            assert response.status_code == 200

        # Check review queues are isolated
        response = org_a_client.get("/v1/queue")
        assert response.status_code == 200

        org_a_queue = response.json()["data"]
        org_a_item_ids = {item["id"] for item in org_a_queue.get("new", [])}

        response = org_b_client.get("/v1/queue")
        assert response.status_code == 200

        org_b_queue = response.json()["data"]
        org_b_item_ids = {item["id"] for item in org_b_queue.get("new", [])}

        # Verify no overlap in queue items
        assert len(org_a_item_ids.intersection(org_b_item_ids)) == 0

    async def test_cross_org_review_recording_denied(self, org_a_client, org_b_client):
        """Test that users cannot record reviews for items from other orgs."""

        # Org A creates and approves an item
        item_data = self.ORG_A_DATA["items"][0]
        response = org_a_client.post("/v1/items", json=item_data)
        assert response.status_code == 201

        item_id = response.json()["data"]["id"]

        approval_data = {"ids": [item_id]}
        response = org_a_client.post("/v1/items/approve", json=approval_data)
        assert response.status_code == 200

        # Org A can record review for their item
        review_data = {
            "item_id": item_id,
            "rating": 3,
            "correct": True,
            "latency_ms": 2000,
            "mode": "review",
        }

        response = org_a_client.post("/v1/record", json=review_data)
        assert response.status_code == 200

        # Org B cannot record review for Org A's item
        response = org_b_client.post("/v1/record", json=review_data)
        assert response.status_code == 404  # Item not found in their org

    async def test_quiz_system_isolation(self, org_a_client, org_b_client):
        """Test that quiz systems are org-isolated."""

        # Setup approved items for both orgs
        # Org A
        for item_data in self.ORG_A_DATA["items"]:
            response = org_a_client.post("/v1/items", json=item_data)
            assert response.status_code == 201

        response = org_a_client.get("/v1/items?status=draft")
        org_a_drafts = response.json()["data"]["items"]
        if org_a_drafts:
            approval_data = {"ids": [item["id"] for item in org_a_drafts]}
            org_a_client.post("/v1/items/approve", json=approval_data)

        # Org B
        for item_data in self.ORG_B_DATA["items"]:
            response = org_b_client.post("/v1/items", json=item_data)
            assert response.status_code == 201

        response = org_b_client.get("/v1/items?status=draft")
        org_b_drafts = response.json()["data"]["items"]
        if org_b_drafts:
            approval_data = {"ids": [item["id"] for item in org_b_drafts]}
            org_b_client.post("/v1/items/approve", json=approval_data)

        # Org A starts a quiz
        quiz_params = {"mode": "drill", "params": {"length": 2, "tags": ["test"]}}

        response = org_a_client.post("/v1/quiz/start", json=quiz_params)
        assert response.status_code == 200

        org_a_quiz = response.json()["data"]
        org_a_quiz_id = org_a_quiz["quiz_id"]
        org_a_quiz_items = {item["id"] for item in org_a_quiz["items"]}

        # Org B starts a quiz
        response = org_b_client.post("/v1/quiz/start", json=quiz_params)
        assert response.status_code == 200

        org_b_quiz = response.json()["data"]
        org_b_quiz_items = {item["id"] for item in org_b_quiz["items"]}

        # Verify quiz items are org-specific
        assert len(org_a_quiz_items.intersection(org_b_quiz_items)) == 0

        # Org B cannot access Org A's quiz
        response = org_b_client.post("/v1/quiz/finish", json={"quiz_id": org_a_quiz_id})
        assert response.status_code == 404

    async def test_progress_analytics_isolation(self, org_a_client, org_b_client):
        """Test that progress analytics are org-isolated."""

        # Create some activity for Org A
        item_data = self.ORG_A_DATA["items"][0]
        response = org_a_client.post("/v1/items", json=item_data)
        assert response.status_code == 201

        item_id = response.json()["data"]["id"]

        # Approve and review
        approval_data = {"ids": [item_id]}
        org_a_client.post("/v1/items/approve", json=approval_data)

        review_data = {
            "item_id": item_id,
            "rating": 4,
            "correct": True,
            "latency_ms": 1500,
            "mode": "review",
        }

        org_a_client.post("/v1/record", json=review_data)

        # Get Org A analytics
        response = org_a_client.get("/v1/progress/overview")
        assert response.status_code == 200

        org_a_progress = response.json()["data"]

        # Get Org B analytics (should be different/empty)
        response = org_b_client.get("/v1/progress/overview")
        assert response.status_code == 200

        org_b_progress = response.json()["data"]

        # Org A should have activity, Org B should not
        assert org_a_progress["attempts_7d"] >= 1
        assert org_b_progress["attempts_7d"] == 0
        assert org_a_progress["total_items"] >= 1
        assert org_b_progress["total_items"] == 0

    async def test_content_generation_isolation(self, org_a_client, org_b_client):
        """Test that content generation is org-isolated."""

        generation_text = """
        Test content for generation. This should create items that belong to 
        the organization of the user making the request. The photosynthesis 
        process converts sunlight into energy at 680 nanometers wavelength.
        Temperature of 25 degrees Celsius is optimal for this process.
        """

        # Org A generates content
        generation_request = {
            "text": generation_text,
            "types": ["flashcard", "mcq"],
            "count": 5,
            "difficulty": "core",
        }

        response = org_a_client.post("/v1/items/generate", json=generation_request)
        assert response.status_code == 200

        org_a_generation = response.json()["data"]

        # Org B generates content
        response = org_b_client.post("/v1/items/generate", json=generation_request)
        assert response.status_code == 200

        org_b_generation = response.json()["data"]

        # Check that generated items are in correct org's draft area
        response = org_a_client.get("/v1/items?status=draft")
        org_a_drafts = {item["id"] for item in response.json()["data"]["items"]}

        response = org_b_client.get("/v1/items?status=draft")
        org_b_drafts = {item["id"] for item in response.json()["data"]["items"]}

        # Should have no overlap
        assert len(org_a_drafts.intersection(org_b_drafts)) == 0

    async def test_search_isolation(self, org_a_client, org_b_client):
        """Test that search results are org-scoped."""

        # Create org-specific content with shared keywords
        org_a_item = {
            "type": "flashcard",
            "payload": {
                "front": "Shared keyword: photosynthesis in Org A",
                "back": "Org A answer",
            },
            "tags": ["biology", "org-a"],
            "difficulty": "intro",
        }

        org_b_item = {
            "type": "flashcard",
            "payload": {
                "front": "Shared keyword: photosynthesis in Org B",
                "back": "Org B answer",
            },
            "tags": ["biology", "org-b"],
            "difficulty": "intro",
        }

        # Create and approve items
        response = org_a_client.post("/v1/items", json=org_a_item)
        org_a_id = response.json()["data"]["id"]
        org_a_client.post("/v1/items/approve", json={"ids": [org_a_id]})

        response = org_b_client.post("/v1/items", json=org_b_item)
        org_b_id = response.json()["data"]["id"]
        org_b_client.post("/v1/items/approve", json={"ids": [org_b_id]})

        # Search for shared keyword
        response = org_a_client.get("/v1/items?q=photosynthesis&status=published")
        assert response.status_code == 200

        org_a_search_results = response.json()["data"]["items"]
        org_a_result_ids = {item["id"] for item in org_a_search_results}

        response = org_b_client.get("/v1/items?q=photosynthesis&status=published")
        assert response.status_code == 200

        org_b_search_results = response.json()["data"]["items"]
        org_b_result_ids = {item["id"] for item in org_b_search_results}

        # Each org should only see their own results
        assert org_a_id in org_a_result_ids
        assert org_b_id not in org_a_result_ids

        assert org_b_id in org_b_result_ids
        assert org_a_id not in org_b_result_ids

    async def test_embedding_similarity_isolation(self, org_a_client, org_b_client):
        """Test that embedding similarity searches are org-isolated."""

        # Create similar content in both orgs
        similar_item_a = {
            "type": "flashcard",
            "payload": {
                "front": "What is cellular respiration?",
                "back": "ATP production process",
            },
            "tags": ["biology"],
            "difficulty": "core",
        }

        similar_item_b = {
            "type": "flashcard",
            "payload": {
                "front": "What is cellular respiration?",
                "back": "Energy production in cells",
            },
            "tags": ["biology"],
            "difficulty": "core",
        }

        # Create items
        response = org_a_client.post("/v1/items", json=similar_item_a)
        org_a_item_id = response.json()["data"]["id"]

        response = org_b_client.post("/v1/items", json=similar_item_b)
        org_b_item_id = response.json()["data"]["id"]

        # Compute embeddings
        org_a_client.post(f"/v1/items/{org_a_item_id}/compute-embedding")
        org_b_client.post(f"/v1/items/{org_b_item_id}/compute-embedding")

        # Check similar items - should not cross org boundaries
        response = org_a_client.get(f"/v1/items/{org_a_item_id}/similar")
        assert response.status_code == 200

        org_a_similar = response.json()["data"]
        org_a_similar_ids = {item["id"] for item in org_a_similar}

        # Should not include items from Org B
        assert org_b_item_id not in org_a_similar_ids
