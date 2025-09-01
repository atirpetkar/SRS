"""
Review API routes - FSRS scheduler and review queue endpoints.
"""

from datetime import UTC, datetime
from uuid import NAMESPACE_DNS, UUID, uuid5

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.config.settings import Settings, get_settings
from api.infra.database import get_session
from api.v1.core.exceptions import create_success_response
from api.v1.core.registries import scheduler_registry
from api.v1.core.security import Principal, get_principal
from api.v1.items.models import Item
from api.v1.review.fsrs import fsrs_state_from_db, fsrs_state_to_db_dict
from api.v1.review.models import Review, SchedulerState
from api.v1.review.schemas import (
    QueueItemResponse,
    ReviewQueueResponse,
    ReviewRecordRequest,
    ReviewRecordResponse,
    SchedulerStateResponse,
)

router = APIRouter(prefix="/review", tags=["review"])


def string_to_uuid(text: str) -> UUID:
    """Convert a string to a deterministic UUID using namespace DNS."""
    return uuid5(NAMESPACE_DNS, text)


@router.get("/queue", response_model=dict)
async def get_review_queue(
    limit: int = Query(20, ge=1, le=100),
    mix_new: float = Query(0.2, ge=0.0, le=1.0),
    tags: list[str] = Query(None),
    type: str = Query(None),
    db: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    settings: Settings = Depends(get_settings),
) -> ReviewQueueResponse:
    """Get review queue with due items and new items."""

    now = datetime.now(UTC)
    new_limit = int(limit * mix_new)
    due_limit = limit - new_limit

    # Convert principal IDs to UUIDs
    org_uuid = string_to_uuid(principal.org_id)
    user_uuid = string_to_uuid(principal.user_id)

    # Base query for published items in the user's org
    base_query = (
        select(Item)
        .where(and_(Item.org_id == org_uuid, Item.status == "published"))
        .options(selectinload(Item.organization))
    )

    # Apply filters if provided
    if tags:
        base_query = base_query.where(Item.tags.overlap(tags))
    if type:
        base_query = base_query.where(Item.type == type)

    # Get due items (items with scheduler state that are due)
    due_query = (
        base_query.join(
            SchedulerState,
            and_(
                SchedulerState.item_id == Item.id,
                SchedulerState.user_id == user_uuid,
            ),
        )
        .where(SchedulerState.due_at <= now)
        .order_by(SchedulerState.due_at)
        .limit(due_limit)
    )

    due_result = await db.execute(due_query)
    due_items = due_result.scalars().all()

    # Get new items (published items without scheduler state for this user)
    new_query = (
        base_query.outerjoin(
            SchedulerState,
            and_(
                SchedulerState.item_id == Item.id,
                SchedulerState.user_id == user_uuid,
            ),
        )
        .where(SchedulerState.item_id.is_(None))
        .order_by(Item.created_at.desc())
        .limit(new_limit)
    )

    new_result = await db.execute(new_query)
    new_items = new_result.scalars().all()

    # Get scheduler states for due items to include due_at
    due_states = {}
    if due_items:
        due_ids = [item.id for item in due_items]
        states_query = select(SchedulerState).where(
            and_(
                SchedulerState.item_id.in_(due_ids),
                SchedulerState.user_id == user_uuid,
            )
        )
        states_result = await db.execute(states_query)
        due_states = {state.item_id: state for state in states_result.scalars().all()}

    # Convert to response format
    due_queue = []
    for item in due_items:
        state = due_states.get(item.id)
        due_queue.append(
            QueueItemResponse(
                id=item.id,
                type=item.type,
                render_payload=item.payload,
                due_at=state.due_at if state else None,
                is_new=False,
            )
        )

    new_queue = []
    for item in new_items:
        new_queue.append(
            QueueItemResponse(
                id=item.id,
                type=item.type,
                render_payload=item.payload,
                due_at=None,
                is_new=True,
            )
        )

    queue_response = ReviewQueueResponse(due=due_queue, new=new_queue)
    return create_success_response(queue_response.model_dump())


@router.post("/record", response_model=dict)
async def record_review(
    review_request: ReviewRecordRequest,
    db: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    settings: Settings = Depends(get_settings),
) -> ReviewRecordResponse:
    """Record a review and update scheduler state."""

    # Convert principal IDs to UUIDs
    org_uuid = string_to_uuid(principal.org_id)
    user_uuid = string_to_uuid(principal.user_id)

    # Validate item exists and user has access
    item_query = select(Item).where(
        and_(
            Item.id == review_request.item_id,
            Item.org_id == org_uuid,
            Item.status == "published",
        )
    )
    result = await db.execute(item_query)
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    # Get or create scheduler state
    state_query = select(SchedulerState).where(
        and_(
            SchedulerState.user_id == user_uuid,
            SchedulerState.item_id == review_request.item_id,
        )
    )
    result = await db.execute(state_query)
    db_state = result.scalar_one_or_none()

    # Get scheduler implementation
    scheduler = scheduler_registry.get(settings.scheduler.value)

    if db_state is None:
        # New item - create initial state
        fsrs_state = scheduler.seed(str(user_uuid), str(review_request.item_id))

        # Update state with review
        updated_fsrs_state = scheduler.update(
            fsrs_state,
            review_request.rating,
            review_request.correct,
            review_request.latency_ms or 0,
        )

        # Create new scheduler state record
        new_state = SchedulerState(
            user_id=user_uuid,
            item_id=review_request.item_id,
            **fsrs_state_to_db_dict(updated_fsrs_state),
        )
        db.add(new_state)
        await db.flush()
        await db.refresh(new_state)

        final_state = new_state
    else:
        # Existing item - update state with optimistic locking
        fsrs_state = fsrs_state_from_db(db_state)

        # Update state with review
        updated_fsrs_state = scheduler.update(
            fsrs_state,
            review_request.rating,
            review_request.correct,
            review_request.latency_ms or 0,
        )

        # Update with version checking for optimistic locking
        update_dict = fsrs_state_to_db_dict(updated_fsrs_state)
        update_dict["version"] = db_state.version + 1

        update_query = (
            update(SchedulerState)
            .where(
                and_(
                    SchedulerState.user_id == user_uuid,
                    SchedulerState.item_id == review_request.item_id,
                    SchedulerState.version == db_state.version,  # Optimistic locking
                )
            )
            .values(**update_dict)
        )

        result = await db.execute(update_query)
        if result.rowcount == 0:
            raise HTTPException(
                status_code=409,
                detail="Scheduler state was modified by another request. Please retry.",
            )

        # Fetch updated state
        updated_result = await db.execute(state_query)
        final_state = updated_result.scalar_one()

    # Record the review
    review = Review(
        user_id=user_uuid,
        item_id=review_request.item_id,
        mode=review_request.mode,
        response=review_request.response,
        correct=review_request.correct,
        latency_ms=review_request.latency_ms,
        latency_bucket=_calculate_latency_bucket(review_request.latency_ms),
        ease=review_request.rating,
    )
    db.add(review)

    await db.commit()

    # Calculate interval in days
    interval_days = (final_state.due_at - datetime.now(UTC)).days

    response = ReviewRecordResponse(
        updated_state=SchedulerStateResponse.model_validate(final_state),
        next_due=final_state.due_at,
        interval_days=max(0, interval_days),
    )
    return create_success_response(response.model_dump())


def _calculate_latency_bucket(latency_ms: int | None) -> int | None:
    """Calculate latency bucket for analytics."""
    if latency_ms is None:
        return None

    # Bucket latencies: <1s, 1-3s, 3-10s, 10-30s, 30s+
    if latency_ms < 1000:
        return 1
    elif latency_ms < 3000:
        return 2
    elif latency_ms < 10000:
        return 3
    elif latency_ms < 30000:
        return 4
    else:
        return 5
