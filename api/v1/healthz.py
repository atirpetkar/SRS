from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from api.config.settings import Settings, SettingsDep
from api.infra.database import get_session
from api.v1.core.exceptions import create_success_response
from api.v1.infra.jobs.models import Job, JobStatus

router = APIRouter()


class DatabaseHealth(BaseModel):
    """Database health status."""

    connected: bool
    response_time_ms: float | None = None
    error: str | None = None


class WorkerHealth(BaseModel):
    """Worker health status."""

    active_workers: int
    last_heartbeat_age_seconds: int | None = None
    stuck_jobs_count: int = 0
    queue_depth: int = 0


class HealthResponse(BaseModel):
    """Enhanced health response with worker and database status."""

    ok: bool
    version: str
    environment: str
    timestamp: str
    database: DatabaseHealth
    worker: WorkerHealth | None = None


@router.get("/healthz", response_model=dict)
async def health_check(
    settings: Settings = SettingsDep, session: AsyncSession = Depends(get_session)
):
    """Enhanced health check endpoint with database and worker status."""

    timestamp = datetime.now(UTC).isoformat()
    overall_ok = True

    # Check database health
    db_health = await _check_database_health(session)
    if not db_health.connected:
        overall_ok = False

    # Check worker health (if job system is enabled)
    worker_health = None
    try:
        worker_health = await _check_worker_health(session, settings)
    except Exception:
        # Worker health check failure doesn't fail overall health
        # but we log it for monitoring
        worker_health = WorkerHealth(
            active_workers=0,
            last_heartbeat_age_seconds=None,
            stuck_jobs_count=0,
            queue_depth=0,
        )

    health_data = {
        "ok": overall_ok,
        "version": settings.version,
        "environment": settings.environment,
        "timestamp": timestamp,
        "database": db_health.model_dump(),
        "worker": worker_health.model_dump() if worker_health else None,
    }

    return create_success_response(data=health_data)


async def _check_database_health(session: AsyncSession) -> DatabaseHealth:
    """Check database connectivity and response time."""
    start_time = datetime.now(UTC)

    try:
        # Simple query to test database connectivity
        await session.execute(text("SELECT 1"))

        end_time = datetime.now(UTC)
        response_time_ms = (end_time - start_time).total_seconds() * 1000

        return DatabaseHealth(
            connected=True, response_time_ms=round(response_time_ms, 2)
        )

    except Exception as e:
        return DatabaseHealth(connected=False, error=str(e))


async def _check_worker_health(
    session: AsyncSession, settings: Settings
) -> WorkerHealth:
    """Check job worker health and queue status."""

    # Count active workers based on recent heartbeats
    heartbeat_threshold = datetime.now(UTC).timestamp() - 300  # 5 minutes
    heartbeat_cutoff = datetime.fromtimestamp(heartbeat_threshold, UTC)

    active_workers_result = await session.execute(
        select(func.count(func.distinct(Job.locked_by))).where(
            Job.status == JobStatus.RUNNING.value, Job.heartbeat_at > heartbeat_cutoff
        )
    )
    active_workers = active_workers_result.scalar() or 0

    # Find most recent heartbeat
    last_heartbeat_result = await session.execute(
        select(func.max(Job.heartbeat_at)).where(
            Job.status == JobStatus.RUNNING.value, Job.heartbeat_at.is_not(None)
        )
    )
    last_heartbeat = last_heartbeat_result.scalar()

    last_heartbeat_age_seconds = None
    if last_heartbeat:
        age_seconds = (datetime.now(UTC) - last_heartbeat).total_seconds()
        last_heartbeat_age_seconds = int(age_seconds)

    # Count stuck jobs (running jobs with old heartbeats)
    stuck_threshold = datetime.now(UTC).timestamp() - settings.job_visibility_timeout_s
    stuck_cutoff = datetime.fromtimestamp(stuck_threshold, UTC)

    stuck_jobs_result = await session.execute(
        select(func.count(Job.id)).where(
            Job.status == JobStatus.RUNNING.value, Job.heartbeat_at < stuck_cutoff
        )
    )
    stuck_jobs_count = stuck_jobs_result.scalar() or 0

    # Calculate queue depth
    queue_depth_result = await session.execute(
        select(func.count(Job.id)).where(
            Job.status.in_([JobStatus.QUEUED.value, JobStatus.RUNNING.value])
        )
    )
    queue_depth = queue_depth_result.scalar() or 0

    return WorkerHealth(
        active_workers=active_workers,
        last_heartbeat_age_seconds=last_heartbeat_age_seconds,
        stuck_jobs_count=stuck_jobs_count,
        queue_depth=queue_depth,
    )
