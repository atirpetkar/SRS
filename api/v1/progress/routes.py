"""
Progress API routes - analytics and forecasting endpoints.

This module implements read-only analytics endpoints for user progress tracking.
Uses raw SQL queries for complex aggregations and PostgreSQL-specific operations,
following the design principle of using the right tool for each purpose:
- CRUD operations: SQLAlchemy ORM (Steps 1-5)
- Analytics queries: Raw SQL (Step 6)

See DESIGN_DECISIONS.md for detailed rationale.
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.config.settings import Settings, get_settings
from api.infra.database import get_session
from api.v1.core.exceptions import create_success_response
from api.v1.core.security import Principal, get_principal
from api.v1.progress.schemas import (
    ForecastDay,
    ForecastResponse,
    ProgressOverviewResponse,
    WeakAreaItem,
    WeakAreasResponse,
)

router = APIRouter(prefix="/progress", tags=["progress"])


@router.get("/overview", response_model=dict)
async def get_progress_overview(
    db: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    settings: Settings = Depends(get_settings),
) -> ProgressOverviewResponse:
    """
    Get progress overview with 7-day metrics and user totals.

    Provides comprehensive analytics including:
    - Recent activity: attempts, accuracy, and latency over last 7 days
    - Progress tracking: current streak and item completion statistics
    - All metrics are org-scoped for multi-tenant security

    Returns:
        ProgressOverviewResponse: Aggregated metrics for user dashboard

    Performance: Optimized queries targeting <1s response time
    """

    now = datetime.now(UTC)
    seven_days_ago = now - timedelta(days=7)

    # Get 7-day review metrics
    # Uses CASE WHEN for conditional aggregation - standard SQL pattern
    # JOIN ensures org-scoping security through items table
    review_metrics_query = text(
        """
        SELECT
            COUNT(*) as attempts,
            COALESCE(AVG(CASE WHEN correct = true THEN 1.0 ELSE 0.0 END), 0.0) as accuracy,
            AVG(latency_ms) as avg_latency
        FROM reviews r
        JOIN items i ON r.item_id = i.id
        WHERE r.user_id = :user_id
          AND i.org_id = :org_id
          AND r.ts >= :seven_days_ago
          AND r.ts <= :now
    """
    )

    result = await db.execute(
        review_metrics_query,
        {
            "user_id": principal.user_id,
            "org_id": str(principal.org_id),
            "seven_days_ago": seven_days_ago,
            "now": now,
        },
    )
    metrics = result.fetchone()

    attempts_7d = metrics.attempts if metrics else 0
    accuracy_7d = float(metrics.accuracy) if metrics and metrics.accuracy else 0.0
    avg_latency_ms_7d = (
        float(metrics.avg_latency) if metrics and metrics.avg_latency else None
    )

    # Calculate streak days (consecutive days with reviews)
    # Uses CTE with window functions - PostgreSQL-specific but necessary for complex logic
    # This query calculates consecutive review days from today backwards
    streak_query = text(
        """
        WITH daily_reviews AS (
            SELECT DISTINCT DATE(r.ts AT TIME ZONE 'UTC') as review_date
            FROM reviews r
            JOIN items i ON r.item_id = i.id
            WHERE r.user_id = :user_id
              AND i.org_id = :org_id
            ORDER BY review_date DESC
        ),
        streak_calc AS (
            SELECT review_date,
                   ROW_NUMBER() OVER (ORDER BY review_date DESC) as rn,
                   review_date + INTERVAL '1 day' * ROW_NUMBER() OVER (ORDER BY review_date DESC) as expected_date
            FROM daily_reviews
        )
        SELECT COUNT(*) as streak_days
        FROM streak_calc
        WHERE expected_date = CAST(:today AS date) + INTERVAL '1 day' * rn
    """
    )

    result = await db.execute(
        streak_query,
        {
            "user_id": principal.user_id,
            "org_id": str(principal.org_id),
            "today": now.date(),
        },
    )
    streak_result = result.fetchone()
    streak_days = streak_result.streak_days if streak_result else 0

    # Get total items and reviewed items
    # LEFT JOIN to include items without reviews in total count
    # Uses CASE WHEN with DISTINCT for accurate reviewed items count
    totals_query = text(
        """
        SELECT
            COUNT(DISTINCT i.id) as total_items,
            COUNT(DISTINCT CASE WHEN ss.item_id IS NOT NULL THEN i.id END) as reviewed_items
        FROM items i
        LEFT JOIN scheduler_state ss ON i.id = ss.item_id AND ss.user_id = :user_id
        WHERE i.org_id = :org_id AND i.status = 'published'
    """
    )

    result = await db.execute(
        totals_query,
        {"user_id": principal.user_id, "org_id": str(principal.org_id)},
    )
    totals = result.fetchone()

    total_items = totals.total_items if totals else 0
    reviewed_items = totals.reviewed_items if totals else 0

    response = ProgressOverviewResponse(
        attempts_7d=attempts_7d,
        accuracy_7d=accuracy_7d,
        avg_latency_ms_7d=avg_latency_ms_7d,
        streak_days=streak_days,
        total_items=total_items,
        reviewed_items=reviewed_items,
    )

    return create_success_response(response.model_dump())


@router.get("/weak_areas", response_model=dict)
async def get_weak_areas(
    top: int = Query(5, ge=1, le=20, description="Number of weak areas to return"),
    db: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    settings: Settings = Depends(get_settings),
) -> WeakAreasResponse:
    """
    Analyze weak performance areas by tags, types, and difficulty levels.

    Identifies areas where user accuracy is lowest, helping prioritize study focus.
    Uses statistical aggregation with minimum attempt thresholds to ensure reliability.

    Args:
        top: Maximum number of weak areas to return per category (1-20)

    Returns:
        WeakAreasResponse: Weak areas ranked by accuracy (lowest first)

    Note: Requires minimum 3 attempts per category for statistical significance
    """

    # Weak areas by tags
    # Uses PostgreSQL unnest() function - cannot be ported to ORM
    # Analyzes individual tags from ARRAY column for granular insights
    tags_query = text(
        """
        SELECT
            unnest(i.tags) as tag_name,
            COUNT(r.*) as attempts,
            COALESCE(AVG(CASE WHEN r.correct = true THEN 1.0 ELSE 0.0 END), 0.0) as accuracy
        FROM reviews r
        JOIN items i ON r.item_id = i.id
        WHERE r.user_id = :user_id
          AND i.org_id = :org_id
          AND array_length(i.tags, 1) > 0
        GROUP BY tag_name
        HAVING COUNT(r.*) >= 3
        ORDER BY accuracy ASC, attempts DESC
        LIMIT :top
    """
    )

    result = await db.execute(
        tags_query,
        {
            "user_id": principal.user_id,
            "org_id": str(principal.org_id),
            "top": top,
        },
    )
    tag_results = result.fetchall()

    tags_weak = [
        WeakAreaItem(
            name=row.tag_name,
            accuracy=float(row.accuracy),
            attempts=row.attempts,
        )
        for row in tag_results
    ]

    # Weak areas by item type
    # Standard aggregation query - could be converted to ORM but kept consistent
    # Groups by item.type for analysis across flashcard, mcq, cloze, etc.
    types_query = text(
        """
        SELECT
            i.type as type_name,
            COUNT(r.*) as attempts,
            COALESCE(AVG(CASE WHEN r.correct = true THEN 1.0 ELSE 0.0 END), 0.0) as accuracy
        FROM reviews r
        JOIN items i ON r.item_id = i.id
        WHERE r.user_id = :user_id
          AND i.org_id = :org_id
        GROUP BY i.type
        HAVING COUNT(r.*) >= 3
        ORDER BY accuracy ASC, attempts DESC
        LIMIT :top
    """
    )

    result = await db.execute(
        types_query,
        {
            "user_id": principal.user_id,
            "org_id": str(principal.org_id),
            "top": top,
        },
    )
    type_results = result.fetchall()

    types_weak = [
        WeakAreaItem(
            name=row.type_name,
            accuracy=float(row.accuracy),
            attempts=row.attempts,
        )
        for row in type_results
    ]

    # Weak areas by difficulty
    # Uses COALESCE to handle NULL difficulty values as 'unspecified'
    # Analyzes performance across intro/core/stretch difficulty levels
    difficulty_query = text(
        """
        SELECT
            COALESCE(i.difficulty, 'unspecified') as difficulty_name,
            COUNT(r.*) as attempts,
            COALESCE(AVG(CASE WHEN r.correct = true THEN 1.0 ELSE 0.0 END), 0.0) as accuracy
        FROM reviews r
        JOIN items i ON r.item_id = i.id
        WHERE r.user_id = :user_id
          AND i.org_id = :org_id
        GROUP BY COALESCE(i.difficulty, 'unspecified')
        HAVING COUNT(r.*) >= 3
        ORDER BY accuracy ASC, attempts DESC
        LIMIT :top
    """
    )

    result = await db.execute(
        difficulty_query,
        {
            "user_id": principal.user_id,
            "org_id": str(principal.org_id),
            "top": top,
        },
    )
    difficulty_results = result.fetchall()

    difficulty_weak = [
        WeakAreaItem(
            name=row.difficulty_name,
            accuracy=float(row.accuracy),
            attempts=row.attempts,
        )
        for row in difficulty_results
    ]

    response = WeakAreasResponse(
        tags=tags_weak,
        types=types_weak,
        difficulty=difficulty_weak,
    )

    return create_success_response(response.model_dump())


@router.get("/forecast", response_model=dict)
async def get_forecast(
    days: int = Query(7, ge=1, le=30, description="Number of days to forecast"),
    db: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    settings: Settings = Depends(get_settings),
) -> ForecastResponse:
    """
    Forecast workload by predicting due items over the next N days.

    Analyzes FSRS scheduler state to predict review workload, enabling:
    - Daily study planning and time allocation
    - Workload balancing across time periods
    - Proactive scheduling for high-volume days

    Args:
        days: Number of days to forecast (1-30)

    Returns:
        ForecastResponse: Daily due item counts with zero-padding for empty days

    Note: Based on current scheduler state - actual workload may vary with reviews
    """

    now = datetime.now(UTC)
    end_date = now + timedelta(days=days)

    # Get due items grouped by date
    # Uses PostgreSQL DATE() function with timezone conversion
    # Groups scheduler state by date for daily workload prediction
    forecast_query = text(
        """
        SELECT
            DATE(ss.due_at AT TIME ZONE 'UTC') as due_date,
            COUNT(*) as due_count
        FROM scheduler_state ss
        JOIN items i ON ss.item_id = i.id
        WHERE ss.user_id = :user_id
          AND i.org_id = :org_id
          AND i.status = 'published'
          AND ss.due_at >= :now
          AND ss.due_at < :end_date
        GROUP BY DATE(ss.due_at AT TIME ZONE 'UTC')
        ORDER BY due_date
    """
    )

    result = await db.execute(
        forecast_query,
        {
            "user_id": principal.user_id,
            "org_id": str(principal.org_id),
            "now": now,
            "end_date": end_date,
        },
    )
    forecast_results = result.fetchall()

    # Create complete forecast with zero counts for days without due items
    # Ensures consistent response format with explicit zero values for empty days
    forecast_by_day = []
    current_date = now.date()
    forecast_dict = {row.due_date: row.due_count for row in forecast_results}

    for i in range(days):
        forecast_date = current_date + timedelta(days=i)
        due_count = forecast_dict.get(forecast_date, 0)
        forecast_by_day.append(ForecastDay(date=forecast_date, due_count=due_count))

    response = ForecastResponse(by_day=forecast_by_day)
    return create_success_response(response.model_dump())
