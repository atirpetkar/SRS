"""
Job service for enqueueing and managing background jobs.
"""

import hashlib
import logging
import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.config.settings import Settings
from api.v1.core.security import Principal
from api.v1.infra.jobs.models import Job, JobStatus
from api.v1.infra.jobs.schemas import JobCreate, JobEnqueueResponse, JobStatsResponse

logger = logging.getLogger(__name__)


class JobService:
    """Service for managing background jobs."""

    def __init__(self, settings: Settings):
        self.settings = settings

    async def enqueue_job(
        self,
        session: AsyncSession,
        job_create: JobCreate,
        principal: Principal | None = None,
        request_id: str | None = None,
    ) -> JobEnqueueResponse:
        """
        Enqueue a new job with deduplication support.

        Args:
            session: Database session
            job_create: Job creation parameters
            principal: Principal context for org/user isolation
            request_id: Request ID for tracing

        Returns:
            Job enqueue response with job_id and deduplication info
        """
        # Set defaults from principal context
        org_id = principal.org_uuid if principal else None
        user_id = principal.user_uuid if principal else None
        requested_by_user_id = user_id

        if not org_id:
            raise ValueError("org_id is required for job enqueueing")

        # Check for existing job with dedupe key
        deduplicated = False
        if job_create.dedupe_key:
            existing_job = await self._find_existing_job(
                session, job_create.dedupe_key, org_id
            )
            if existing_job:
                logger.info(
                    "Job deduplicated",
                    extra={
                        "job_id": str(existing_job.id),
                        "dedupe_key": job_create.dedupe_key,
                        "type": job_create.type,
                        "org_id": str(org_id),
                    },
                )
                return JobEnqueueResponse(
                    job_id=existing_job.id,
                    status=existing_job.status,
                    deduplicated=True,
                )

        # Create new job
        job = Job(
            id=uuid.uuid4(),
            type=job_create.type,
            org_id=org_id,
            user_id=user_id,
            payload=job_create.payload,
            priority=job_create.priority,
            run_at=job_create.run_at or datetime.now(UTC),
            dedupe_key=job_create.dedupe_key,
            requested_by_user_id=requested_by_user_id,
            request_id=request_id,
        )

        try:
            session.add(job)
            await session.commit()
            await session.refresh(job)

            logger.info(
                "Job enqueued",
                extra={
                    "job_id": str(job.id),
                    "type": job.type,
                    "priority": job.priority,
                    "org_id": str(org_id),
                    "dedupe_key": job_create.dedupe_key,
                },
            )

            return JobEnqueueResponse(
                job_id=job.id, status=job.status, deduplicated=deduplicated
            )

        except IntegrityError as e:
            await session.rollback()
            # Check if this was a dedupe key conflict
            if job_create.dedupe_key and "ix_jobs_dedupe_key_active" in str(e):
                # Race condition - another process enqueued the same job
                existing_job = await self._find_existing_job(
                    session, job_create.dedupe_key, org_id
                )
                if existing_job:
                    return JobEnqueueResponse(
                        job_id=existing_job.id,
                        status=existing_job.status,
                        deduplicated=True,
                    )
            raise

    async def _find_existing_job(
        self, session: AsyncSession, dedupe_key: str, org_id: UUID
    ) -> Job | None:
        """Find existing active job with the same dedupe key."""
        result = await session.execute(
            select(Job)
            .where(
                and_(
                    Job.dedupe_key == dedupe_key,
                    Job.org_id == org_id,
                    Job.status.in_(
                        [
                            JobStatus.QUEUED.value,
                            JobStatus.RUNNING.value,
                            JobStatus.SUCCEEDED.value,
                        ]
                    ),
                )
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_job_by_id(
        self, session: AsyncSession, job_id: UUID, org_id: UUID | None = None
    ) -> Job | None:
        """Get job by ID with optional org scoping."""
        query = select(Job).where(Job.id == job_id)
        if org_id:
            query = query.where(Job.org_id == org_id)

        result = await session.execute(query)
        return result.scalar_one_or_none()

    async def get_job_stats(
        self, session: AsyncSession, org_id: UUID | None = None
    ) -> JobStatsResponse:
        """Get job statistics, optionally scoped to organization."""
        base_filter = Job.org_id == org_id if org_id else True

        # Total jobs
        total_result = await session.execute(
            select(func.count(Job.id)).where(base_filter)
        )
        total_jobs = total_result.scalar() or 0

        # Jobs by status
        status_result = await session.execute(
            select(Job.status, func.count(Job.id))
            .where(base_filter)
            .group_by(Job.status)
        )
        by_status = dict(status_result.all())

        # Jobs by type
        type_result = await session.execute(
            select(Job.type, func.count(Job.id)).where(base_filter).group_by(Job.type)
        )
        by_type = dict(type_result.all())

        # Queue depth (queued + running)
        queue_depth = by_status.get(JobStatus.QUEUED.value, 0) + by_status.get(
            JobStatus.RUNNING.value, 0
        )

        # Failed jobs in last hour
        one_hour_ago = datetime.now(UTC).timestamp() - 3600
        failed_recent_result = await session.execute(
            select(func.count(Job.id)).where(
                and_(
                    base_filter,
                    Job.status == JobStatus.FAILED.value,
                    Job.updated_at >= datetime.fromtimestamp(one_hour_ago, UTC),
                )
            )
        )
        failed_last_hour = failed_recent_result.scalar() or 0

        return JobStatsResponse(
            total_jobs=total_jobs,
            by_status=by_status,
            by_type=by_type,
            queue_depth=queue_depth,
            failed_last_hour=failed_last_hour,
        )

    async def retry_job(
        self, session: AsyncSession, job_id: UUID, org_id: UUID | None = None
    ) -> bool:
        """Retry a failed job by resetting its status to queued."""
        query = (
            update(Job)
            .where(
                and_(
                    Job.id == job_id,
                    Job.status == JobStatus.FAILED.value,
                    Job.org_id == org_id if org_id else True,
                )
            )
            .values(
                status=JobStatus.QUEUED.value,
                locked_at=None,
                locked_by=None,
                heartbeat_at=None,
                run_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )

        result = await session.execute(query)
        await session.commit()

        success = result.rowcount > 0
        if success:
            logger.info(
                "Job retried",
                extra={
                    "job_id": str(job_id),
                    "org_id": str(org_id) if org_id else None,
                },
            )

        return success

    async def cancel_job(
        self, session: AsyncSession, job_id: UUID, org_id: UUID | None = None
    ) -> bool:
        """Cancel a queued or running job."""
        query = (
            update(Job)
            .where(
                and_(
                    Job.id == job_id,
                    Job.status.in_([JobStatus.QUEUED.value, JobStatus.RUNNING.value]),
                    Job.org_id == org_id if org_id else True,
                )
            )
            .values(status=JobStatus.CANCELED.value, updated_at=datetime.now(UTC))
        )

        result = await session.execute(query)
        await session.commit()

        success = result.rowcount > 0
        if success:
            logger.info(
                "Job canceled",
                extra={
                    "job_id": str(job_id),
                    "org_id": str(org_id) if org_id else None,
                },
            )

        return success

    async def cleanup_old_jobs(self, session: AsyncSession) -> int:
        """Clean up old completed jobs based on retention policy."""
        retention_days = self.settings.job_cleanup_after_days
        cutoff_date = datetime.now(UTC).timestamp() - (retention_days * 24 * 3600)
        cutoff_datetime = datetime.fromtimestamp(cutoff_date, UTC)

        # Delete old completed jobs (succeeded, failed, deadletter, canceled)
        delete_query = Job.__table__.delete().where(
            and_(
                Job.status.in_(
                    [
                        JobStatus.SUCCEEDED.value,
                        JobStatus.FAILED.value,
                        JobStatus.DEADLETTER.value,
                        JobStatus.CANCELED.value,
                    ]
                ),
                Job.updated_at < cutoff_datetime,
            )
        )

        result = await session.execute(delete_query)
        deleted_count = result.rowcount
        await session.commit()

        if deleted_count > 0:
            logger.info(
                "Cleaned up old jobs",
                extra={
                    "deleted_count": deleted_count,
                    "retention_days": retention_days,
                },
            )

        return deleted_count

    def generate_dedupe_key(self, job_type: str, **params: Any) -> str:
        """Generate a deterministic deduplication key for a job."""
        # Create a stable hash from job type and parameters
        key_data = f"{job_type}:{sorted(params.items())}"
        return hashlib.sha256(key_data.encode()).hexdigest()[:32]
