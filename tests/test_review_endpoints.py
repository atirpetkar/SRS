"""Tests for review API endpoints."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.items.models import Item
from api.v1.review.models import Review, SchedulerState


class TestReviewQueue:
    """Test review queue endpoint."""

    @pytest.mark.asyncio
    async def test_empty_queue(
        self, async_client: AsyncClient, db_session: AsyncSession
    ):
        """Test review queue when no items exist."""
        response = await async_client.get("/v1/review/queue")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["data"]["due"] == []
        assert data["data"]["new"] == []

    @pytest.mark.asyncio
    async def test_queue_with_new_items(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        sample_org,
        sample_user,
    ):
        """Test review queue with new items (no scheduler state)."""
        # Create some published items
        item1 = Item(
            org_id=sample_org.id,
            type="flashcard",
            payload={"front": "Hello", "back": "Hola"},
            status="published",
        )
        item2 = Item(
            org_id=sample_org.id,
            type="mcq",
            payload={
                "stem": "What is 2+2?",
                "options": [
                    {"id": "a", "text": "3"},
                    {"id": "b", "text": "4", "is_correct": True},
                ],
            },
            status="published",
        )

        db_session.add_all([item1, item2])
        await db_session.commit()
        await db_session.refresh(item1)
        await db_session.refresh(item2)

        response = await async_client.get("/v1/review/queue")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["data"]["new"]) == 2
        assert len(data["data"]["due"]) == 0

        # Check item details
        new_items = data["data"]["new"]
        assert all(item["is_new"] for item in new_items)
        assert all(item["due_at"] is None for item in new_items)

    @pytest.mark.asyncio
    async def test_queue_with_due_items(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        sample_org,
        sample_user,
    ):
        """Test review queue with due items."""
        # Create item
        item = Item(
            org_id=sample_org.id,
            type="flashcard",
            payload={"front": "Test", "back": "Prueba"},
            status="published",
        )
        db_session.add(item)
        await db_session.commit()
        await db_session.refresh(item)

        # Create scheduler state that's due
        past_due = datetime.now(UTC) - timedelta(hours=1)
        state = SchedulerState(
            user_id=str(sample_user.id),
            item_id=item.id,
            difficulty=5.0,
            stability=2.0,
            due_at=past_due,
            last_interval=2,
            reps=1,
            lapses=0,
        )
        db_session.add(state)
        await db_session.commit()

        response = await async_client.get("/v1/review/queue")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["data"]["due"]) == 1
        assert len(data["data"]["new"]) == 0

        due_item = data["data"]["due"][0]
        assert not due_item["is_new"]
        assert due_item["due_at"] is not None

    @pytest.mark.asyncio
    async def test_queue_mixed_items(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        sample_org,
        sample_user,
    ):
        """Test review queue with both due and new items."""
        # Create items
        due_item = Item(
            org_id=sample_org.id,
            type="flashcard",
            payload={"front": "Due", "back": "Vencido"},
            status="published",
        )
        new_item = Item(
            org_id=sample_org.id,
            type="flashcard",
            payload={"front": "New", "back": "Nuevo"},
            status="published",
        )

        db_session.add_all([due_item, new_item])
        await db_session.commit()
        await db_session.refresh(due_item)
        await db_session.refresh(new_item)

        # Create scheduler state for due item
        past_due = datetime.now(UTC) - timedelta(minutes=30)
        state = SchedulerState(
            user_id=str(sample_user.id),
            item_id=due_item.id,
            difficulty=4.0,
            stability=1.5,
            due_at=past_due,
            last_interval=1,
            reps=1,
            lapses=0,
        )
        db_session.add(state)
        await db_session.commit()

        response = await async_client.get("/v1/review/queue?limit=10&mix_new=0.5")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["data"]["due"]) == 1
        assert len(data["data"]["new"]) == 1

    @pytest.mark.asyncio
    async def test_queue_filtering(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        sample_org,
        sample_user,
    ):
        """Test review queue filtering by type and tags."""
        # Create items with different types and tags
        flashcard = Item(
            org_id=sample_org.id,
            type="flashcard",
            tags=["spanish", "basic"],
            payload={"front": "Hello", "back": "Hola"},
            status="published",
        )
        mcq = Item(
            org_id=sample_org.id,
            type="mcq",
            tags=["math", "basic"],
            payload={"stem": "What is 2+2?", "options": []},
            status="published",
        )

        db_session.add_all([flashcard, mcq])
        await db_session.commit()

        # Test type filtering
        response = await async_client.get("/v1/review/queue?type=flashcard")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["data"]["new"]) == 1
        assert data["data"]["new"][0]["type"] == "flashcard"

        # Test tag filtering
        response = await async_client.get("/v1/review/queue?tags=spanish")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["data"]["new"]) == 1
        assert "spanish" in flashcard.tags

    @pytest.mark.asyncio
    async def test_queue_draft_items_excluded(
        self, async_client: AsyncClient, db_session: AsyncSession, sample_org
    ):
        """Test that draft items are excluded from queue."""
        # Create draft item
        draft_item = Item(
            org_id=sample_org.id,
            type="flashcard",
            payload={"front": "Draft", "back": "Borrador"},
            status="draft",
        )
        db_session.add(draft_item)
        await db_session.commit()

        response = await async_client.get("/v1/review/queue")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["data"]["new"]) == 0
        assert len(data["data"]["due"]) == 0


class TestReviewRecording:
    """Test review recording endpoint."""

    @pytest.mark.asyncio
    async def test_record_review_new_item(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        sample_org,
        sample_user,
    ):
        """Test recording review for new item."""
        # Create item
        item = Item(
            org_id=sample_org.id,
            type="flashcard",
            payload={"front": "Test", "back": "Prueba"},
            status="published",
        )
        db_session.add(item)
        await db_session.commit()
        await db_session.refresh(item)

        # Record review
        review_data = {
            "item_id": str(item.id),
            "rating": 3,
            "correct": True,
            "latency_ms": 2500,
            "mode": "review",
            "response": {"selected": "correct"},
        }

        response = await async_client.post("/v1/review/record", json=review_data)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Check response structure
        assert "updated_state" in data["data"]
        assert "next_due" in data["data"]
        assert "interval_days" in data["data"]

        # Check scheduler state was created
        updated_state = data["data"]["updated_state"]
        assert updated_state["user_id"] == str(sample_user.id)
        assert updated_state["item_id"] == str(item.id)
        assert updated_state["reps"] == 1
        assert updated_state["lapses"] == 0
        assert updated_state["difficulty"] > 0
        assert updated_state["stability"] > 0

    @pytest.mark.asyncio
    async def test_record_review_existing_item(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        sample_org,
        sample_user,
    ):
        """Test recording review for item with existing state."""
        # Create item
        item = Item(
            org_id=sample_org.id,
            type="flashcard",
            payload={"front": "Existing", "back": "Existente"},
            status="published",
        )
        db_session.add(item)
        await db_session.commit()
        await db_session.refresh(item)

        # Create existing scheduler state
        initial_state = SchedulerState(
            user_id=str(sample_user.id),
            item_id=item.id,
            difficulty=5.0,
            stability=2.0,
            due_at=datetime.now(UTC) - timedelta(hours=1),
            last_interval=2,
            reps=1,
            lapses=0,
            version=1,
        )
        db_session.add(initial_state)
        await db_session.commit()

        # Record another review
        review_data = {
            "item_id": str(item.id),
            "rating": 4,  # Easy rating
            "correct": True,
            "latency_ms": 1500,
            "mode": "review",
        }

        response = await async_client.post("/v1/review/record", json=review_data)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        updated_state = data["data"]["updated_state"]
        assert updated_state["reps"] == 2  # Incremented
        assert updated_state["lapses"] == 0  # No lapses
        assert updated_state["version"] == 2  # Version incremented

    @pytest.mark.asyncio
    async def test_record_review_lapse(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        sample_org,
        sample_user,
    ):
        """Test recording review with lapse (rating = 1)."""
        # Create item
        item = Item(
            org_id=sample_org.id,
            type="flashcard",
            payload={"front": "Lapse", "back": "Olvido"},
            status="published",
        )
        db_session.add(item)
        await db_session.commit()
        await db_session.refresh(item)

        # Record failing review
        review_data = {
            "item_id": str(item.id),
            "rating": 1,  # Again rating
            "correct": False,
            "latency_ms": 8000,
            "mode": "review",
        }

        response = await async_client.post("/v1/review/record", json=review_data)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        updated_state = data["data"]["updated_state"]
        assert updated_state["reps"] == 1
        assert updated_state["lapses"] == 1
        assert updated_state["last_interval"] == 1  # Short interval after lapse

    @pytest.mark.asyncio
    async def test_record_review_invalid_rating(
        self, async_client: AsyncClient, db_session: AsyncSession, sample_org
    ):
        """Test recording review with invalid rating."""
        # Create item
        item = Item(
            org_id=sample_org.id,
            type="flashcard",
            payload={"front": "Invalid", "back": "Inválido"},
            status="published",
        )
        db_session.add(item)
        await db_session.commit()
        await db_session.refresh(item)

        # Try invalid rating
        review_data = {
            "item_id": str(item.id),
            "rating": 5,  # Invalid rating
            "correct": True,
        }

        response = await async_client.post("/v1/review/record", json=review_data)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

        # Try another invalid rating
        review_data["rating"] = 0
        response = await async_client.post("/v1/review/record", json=review_data)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.asyncio
    async def test_record_review_nonexistent_item(self, async_client: AsyncClient):
        """Test recording review for nonexistent item."""
        review_data = {"item_id": str(uuid4()), "rating": 3, "correct": True}

        response = await async_client.post("/v1/review/record", json=review_data)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_record_review_creates_review_record(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        sample_org,
        sample_user,
    ):
        """Test that recording review creates a review record in database."""
        # Create item
        item = Item(
            org_id=sample_org.id,
            type="flashcard",
            payload={"front": "Record", "back": "Registro"},
            status="published",
        )
        db_session.add(item)
        await db_session.commit()
        await db_session.refresh(item)

        # Record review
        review_data = {
            "item_id": str(item.id),
            "rating": 3,
            "correct": True,
            "latency_ms": 3000,
            "mode": "drill",
            "response": {"answer": "test"},
        }

        response = await async_client.post("/v1/review/record", json=review_data)
        assert response.status_code == status.HTTP_200_OK

        # Check that review record was created
        from sqlalchemy import select

        review_query = select(Review).where(Review.item_id == item.id)
        result = await db_session.execute(review_query)
        review = result.scalar_one()

        assert review.user_id == str(sample_user.id)
        assert review.item_id == item.id
        assert review.ease == 3
        assert review.correct is True
        assert review.latency_ms == 3000
        assert review.mode == "drill"
        assert review.response == {"answer": "test"}
        assert review.latency_bucket == 2  # 1-3s bucket
