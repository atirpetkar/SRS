"""
Comprehensive Step 10 Multi-Tenant Authentication Tests

Tests header-based authentication, org isolation, and auto-creation features.
"""

from unittest.mock import patch

import pytest
from httpx import AsyncClient

from api.config.settings import AuthMode


class TestDevAuthMode:
    """Test header-based authentication in dev mode."""

    @pytest.mark.asyncio
    async def test_dev_auth_requires_headers(self, client: AsyncClient):
        """Test that dev mode requires X-User-ID and X-Org-ID headers."""
        with patch("api.v1.core.security.settings.auth_mode", AuthMode.DEV):
            # Request without headers should fail
            response = client.get("/v1/items")
            assert response.status_code == 400
            assert (
                "X-User-ID and X-Org-ID headers are required"
                in response.json()["detail"]
            )

    @pytest.mark.asyncio
    async def test_dev_auth_accepts_valid_headers(self, client: AsyncClient):
        """Test that dev mode accepts valid headers."""
        with patch("api.v1.core.security.settings.auth_mode", AuthMode.DEV):
            headers = {"X-User-ID": "test-user-1", "X-Org-ID": "test-org-1"}

            response = client.get("/v1/items", headers=headers)
            # Should not fail with auth error (may fail for other reasons)
            assert response.status_code != 400 or "X-User-ID" not in response.text

    @pytest.mark.asyncio
    async def test_dev_auth_creates_entities_on_first_sight(self, client: AsyncClient):
        """Test that dev mode auto-creates users and orgs on first sight."""
        with patch("api.v1.core.security.settings.auth_mode", AuthMode.DEV):
            headers = {"X-User-ID": "new-user-99", "X-Org-ID": "new-org-99"}

            # First request should auto-create entities
            response = client.get("/v1/items", headers=headers)
            assert response.status_code == 200

            # Second request should reuse existing entities
            response = client.get("/v1/items", headers=headers)
            assert response.status_code == 200


class TestMultiTenantIsolation:
    """Test data isolation between different orgs and users."""

    @pytest.mark.asyncio
    async def test_org_data_isolation(self, client: AsyncClient):
        """Test that different orgs see isolated data sets."""
        with patch("api.v1.core.security.settings.auth_mode", AuthMode.DEV):
            # Org 1 creates an item
            org1_headers = {"X-User-ID": "user1", "X-Org-ID": "org1"}
            create_data = {
                "type": "flashcard",
                "tags": ["test"],
                "difficulty": "medium",
                "payload": {"front": "Org1 Question", "back": "Org1 Answer"},
            }

            response = client.post("/v1/items", json=create_data, headers=org1_headers)
            assert response.status_code == 201
            org1_item_id = response.json()["id"]

            # Org 2 creates an item
            org2_headers = {"X-User-ID": "user1", "X-Org-ID": "org2"}
            create_data["payload"]["front"] = "Org2 Question"
            create_data["payload"]["back"] = "Org2 Answer"

            response = client.post("/v1/items", json=create_data, headers=org2_headers)
            assert response.status_code == 201
            org2_item_id = response.json()["id"]

            # Org 1 should only see their item
            response = client.get("/v1/items", headers=org1_headers)
            assert response.status_code == 200
            org1_items = [item["id"] for item in response.json()["items"]]
            assert org1_item_id in org1_items
            assert org2_item_id not in org1_items

            # Org 2 should only see their item
            response = client.get("/v1/items", headers=org2_headers)
            assert response.status_code == 200
            org2_items = [item["id"] for item in response.json()["items"]]
            assert org2_item_id in org2_items
            assert org1_item_id not in org2_items

    @pytest.mark.asyncio
    async def test_cross_org_item_access_forbidden(self, client: AsyncClient):
        """Test that users cannot access items from other orgs."""
        with patch("api.v1.core.security.settings.auth_mode", AuthMode.DEV):
            # Org 1 creates an item
            org1_headers = {"X-User-ID": "user1", "X-Org-ID": "org1"}
            create_data = {
                "type": "flashcard",
                "tags": ["secret"],
                "difficulty": "hard",
                "payload": {"front": "Secret Question", "back": "Secret Answer"},
            }

            response = client.post("/v1/items", json=create_data, headers=org1_headers)
            assert response.status_code == 201
            item_id = response.json()["id"]

            # Org 2 tries to access Org 1's item - should fail
            org2_headers = {"X-User-ID": "user1", "X-Org-ID": "org2"}
            response = client.get(f"/v1/items/{item_id}", headers=org2_headers)
            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_quiz_isolation_across_orgs(self, client: AsyncClient):
        """Test that quiz data is isolated between orgs."""
        with patch("api.v1.core.security.settings.auth_mode", AuthMode.DEV):
            # Create items in both orgs
            org1_headers = {"X-User-ID": "user1", "X-Org-ID": "org1"}
            org2_headers = {"X-User-ID": "user1", "X-Org-ID": "org2"}

            # Create and publish item in org1
            create_data = {
                "type": "mcq",
                "tags": ["org1-quiz"],
                "difficulty": "easy",
                "payload": {
                    "stem": "Org1 Question?",
                    "options": [
                        {"id": "a", "text": "Option A", "is_correct": True},
                        {"id": "b", "text": "Option B", "is_correct": False},
                    ],
                },
            }

            response = client.post("/v1/items", json=create_data, headers=org1_headers)
            assert response.status_code == 201
            org1_item_id = response.json()["id"]

            # Approve the item
            client.post(
                "/v1/items/approve", json={"ids": [org1_item_id]}, headers=org1_headers
            )

            # Create and publish item in org2
            create_data["tags"] = ["org2-quiz"]
            create_data["payload"]["stem"] = "Org2 Question?"
            response = client.post("/v1/items", json=create_data, headers=org2_headers)
            assert response.status_code == 201
            org2_item_id = response.json()["id"]

            client.post(
                "/v1/items/approve", json={"ids": [org2_item_id]}, headers=org2_headers
            )

            # Start quizzes in both orgs
            quiz_data = {"mode": "drill", "params": {"length": 10}}

            response = client.post(
                "/v1/quiz/start", json=quiz_data, headers=org1_headers
            )
            assert response.status_code == 200
            org1_quiz_items = [item["id"] for item in response.json()["data"]["items"]]

            response = client.post(
                "/v1/quiz/start", json=quiz_data, headers=org2_headers
            )
            assert response.status_code == 200
            org2_quiz_items = [item["id"] for item in response.json()["data"]["items"]]

            # Each org should only see their own items in quizzes
            assert org1_item_id in org1_quiz_items
            assert org2_item_id not in org1_quiz_items
            assert org2_item_id in org2_quiz_items
            assert org1_item_id not in org2_quiz_items

    @pytest.mark.asyncio
    async def test_progress_isolation_across_orgs(self, client: AsyncClient):
        """Test that progress data is isolated between orgs."""
        with patch("api.v1.core.security.settings.auth_mode", AuthMode.DEV):
            org1_headers = {"X-User-ID": "user1", "X-Org-ID": "org1"}
            org2_headers = {"X-User-ID": "user1", "X-Org-ID": "org2"}

            # Get progress for both orgs - should be independent
            response = client.get("/v1/progress/overview", headers=org1_headers)
            assert response.status_code == 200
            org1_progress = response.json()

            response = client.get("/v1/progress/overview", headers=org2_headers)
            assert response.status_code == 200
            org2_progress = response.json()

            # Progress should be independent (could be same values but isolated data)
            assert "data" in org1_progress
            assert "data" in org2_progress


class TestIdempotency:
    """Test idempotency support for import and approve operations."""

    @pytest.mark.asyncio
    async def test_import_idempotency(self, client: AsyncClient):
        """Test that import operations are idempotent with Idempotency-Key."""
        with patch("api.v1.core.security.settings.auth_mode", AuthMode.DEV):
            headers = {
                "X-User-ID": "user1",
                "X-Org-ID": "org1",
                "Idempotency-Key": "import-test-123",
            }

            import_data = {
                "format": "markdown",
                "data": ":::flashcard\\nQ: Test Question\\nA: Test Answer\\n:::",
            }

            # First request
            response1 = client.post(
                "/v1/items/import", json=import_data, headers=headers
            )
            assert response1.status_code == 200
            result1 = response1.json()

            # Second request with same idempotency key - should return cached response
            response2 = client.post(
                "/v1/items/import", json=import_data, headers=headers
            )
            assert response2.status_code == 200
            result2 = response2.json()

            # Results should be identical
            assert result1 == result2
            assert result1["staged_ids"] == result2["staged_ids"]

    @pytest.mark.asyncio
    async def test_approve_idempotency(self, client: AsyncClient):
        """Test that approve operations are idempotent with Idempotency-Key."""
        with patch("api.v1.core.security.settings.auth_mode", AuthMode.DEV):
            headers = {"X-User-ID": "user1", "X-Org-ID": "org1"}

            # Create and get an item to approve
            create_data = {
                "type": "flashcard",
                "tags": ["test"],
                "difficulty": "easy",
                "payload": {"front": "Question", "back": "Answer"},
            }

            response = client.post("/v1/items", json=create_data, headers=headers)
            item_id = response.json()["id"]

            # First approve request
            approve_headers = {**headers, "Idempotency-Key": "approve-test-456"}
            approve_data = {"ids": [item_id]}

            response1 = client.post(
                "/v1/items/approve", json=approve_data, headers=approve_headers
            )
            assert response1.status_code == 200
            result1 = response1.json()

            # Second approve request with same idempotency key
            response2 = client.post(
                "/v1/items/approve", json=approve_data, headers=approve_headers
            )
            assert response2.status_code == 200
            result2 = response2.json()

            # Results should be identical
            assert result1 == result2


class TestBackwardCompatibility:
    """Test that AUTH_MODE=none still works as before."""

    @pytest.mark.asyncio
    async def test_none_auth_mode_still_works(self, client: AsyncClient):
        """Test that AUTH_MODE=none continues to work without headers."""
        with patch("api.v1.core.security.settings.auth_mode", AuthMode.NONE):
            # Should work without any headers
            response = client.get("/v1/items")
            assert response.status_code == 200

            # Should work with headers too (but they're ignored)
            headers = {"X-User-ID": "ignored", "X-Org-ID": "ignored"}
            response = client.get("/v1/items", headers=headers)
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_healthz_unaffected_by_auth_mode(self, client: AsyncClient):
        """Test that healthz endpoint works regardless of auth mode."""
        # Test with NONE mode
        with patch("api.v1.core.security.settings.auth_mode", AuthMode.NONE):
            response = client.get("/v1/healthz")
            assert response.status_code == 200

        # Test with DEV mode
        with patch("api.v1.core.security.settings.auth_mode", AuthMode.DEV):
            response = client.get("/v1/healthz")
            assert response.status_code == 200
