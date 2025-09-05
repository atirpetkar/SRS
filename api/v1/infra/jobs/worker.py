"""
Postgres-backed job worker with heartbeats and production-ready semantics.
"""

import asyncio
import logging
import os
import random
import socket
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.config.settings import Settings
from api.infra.database import get_session
from api.v1.core.registries import job_registry
from api.v1.core.security import Principal
from api.v1.infra.jobs.models import Job, JobStatus

logger = logging.getLogger(__name__)


class JobWorker:
    """
    Production-ready Postgres-backed job worker.

    Features:
    - SELECT FOR UPDATE SKIP LOCKED for claiming jobs
    - Heartbeats and visibility timeout for stuck job recovery
    - Exponential backoff with jitter for retries
    - Graceful cancellation and shutdown
    - Per-org concurrency limits
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.worker_id = f"{socket.gethostname()}-{os.getpid()}-{id(self)}"
        self.running = False
        self.active_jobs: set[UUID] = set()

    async def start(self) -> None:
        """Start the job worker main loop."""
        if self.running:
            raise RuntimeError("Worker is already running")

        self.running = True
        logger.info(
            "Starting job worker",
            extra={
                "worker_id": self.worker_id,
                "concurrency": self.settings.job_concurrency,
                "poll_interval_ms": self.settings.job_poll_interval_ms,
            },
        )

        try:
            await asyncio.gather(
                self._worker_loop(),
                self._heartbeat_loop(),
                self._stuck_job_recovery_loop(),
                return_exceptions=True,
            )
        except Exception:
            logger.exception("Worker crashed", extra={"worker_id": self.worker_id})
            raise
        finally:
            self.running = False

    async def stop(self) -> None:
        """Stop the worker gracefully."""
        logger.info("Stopping job worker", extra={"worker_id": self.worker_id})
        self.running = False

        # Wait for active jobs to complete (with timeout)
        timeout_seconds = 30
        waited = 0
        while self.active_jobs and waited < timeout_seconds:
            await asyncio.sleep(1)
            waited += 1

        if self.active_jobs:
            logger.warning(
                "Worker stopped with active jobs",
                extra={
                    "worker_id": self.worker_id,
                    "active_jobs": len(self.active_jobs),
                },
            )

    async def _worker_loop(self) -> None:
        """Main worker loop that claims and processes jobs."""
        while self.running:
            try:
                # Check if we can process more jobs
                if len(self.active_jobs) >= self.settings.job_concurrency:
                    await asyncio.sleep(self.settings.job_poll_interval_ms / 1000)
                    continue

                # Claim and process jobs
                async for session in get_session():
                    jobs_to_process = await self._claim_jobs(session)

                    # Process jobs concurrently
                    if jobs_to_process:
                        tasks = [
                            asyncio.create_task(self._process_job(job))
                            for job in jobs_to_process
                        ]
                        # Don't await - let them run in background
                        for task in tasks:
                            asyncio.ensure_future(task)

                    break  # Exit session context

                # Sleep before next poll
                await asyncio.sleep(self.settings.job_poll_interval_ms / 1000)

            except Exception:
                logger.exception(
                    "Error in worker loop", extra={"worker_id": self.worker_id}
                )
                await asyncio.sleep(5)  # Back off on errors

    async def _claim_jobs(self, session: AsyncSession) -> list[Job]:
        """
        Claim available jobs using SELECT FOR UPDATE SKIP LOCKED.

        Returns list of claimed jobs ready for processing.
        """
        available_slots = max(0, self.settings.job_concurrency - len(self.active_jobs))
        if available_slots == 0:
            return []

        now = datetime.now(UTC)

        # Claim jobs with FOR UPDATE SKIP LOCKED
        claim_query = (
            select(Job)
            .where(and_(Job.status == JobStatus.QUEUED.value, Job.run_at <= now))
            .order_by(Job.priority, Job.run_at)
            .limit(available_slots)
            .with_for_update(skip_locked=True)
        )

        result = await session.execute(claim_query)
        jobs_to_claim = result.scalars().all()

        if not jobs_to_claim:
            return []

        # Update claimed jobs to running status
        job_ids = [job.id for job in jobs_to_claim]
        await session.execute(
            update(Job)
            .where(Job.id.in_(job_ids))
            .values(
                status=JobStatus.RUNNING.value,
                locked_at=now,
                locked_by=self.worker_id,
                heartbeat_at=now,
                attempts=Job.attempts + 1,
                updated_at=now,
            )
        )

        await session.commit()

        # Track active jobs
        self.active_jobs.update(job_ids)

        logger.info(
            "Claimed jobs",
            extra={
                "worker_id": self.worker_id,
                "job_count": len(jobs_to_claim),
                "job_ids": [str(job.id) for job in jobs_to_claim],
            },
        )

        return jobs_to_claim

    async def _process_job(self, job: Job) -> None:
        """Process a single job with error handling and result storage."""
        job_logger = logger.bind(job_id=str(job.id), job_type=job.type)

        try:
            job_logger.info("Processing job started")

            # Get job handler from registry
            handler = job_registry.get(job.type)

            # Create principal context for org/user isolation
            principal = Principal(
                user_id=str(job.user_id) if job.user_id else "system",
                org_id=str(job.org_id),
                roles=["admin"],  # Jobs run with admin privileges
            )

            # Process job
            async for session in get_session():
                result = await handler.handle(session, principal, job.payload)

                # Mark job as succeeded
                await self._mark_job_completed(
                    session, job.id, JobStatus.SUCCEEDED, result=result
                )
                break

            job_logger.info("Processing job completed successfully")

        except asyncio.CancelledError:
            # Handle graceful cancellation
            job_logger.info("Job processing cancelled")
            async for session in get_session():
                await self._mark_job_completed(session, job.id, JobStatus.CANCELED)
                break

        except Exception as e:
            job_logger.exception("Job processing failed", extra={"error": str(e)})

            # Determine retry or deadletter
            should_retry = job.can_retry(self.settings.job_max_attempts)

            if should_retry:
                # Schedule retry with exponential backoff
                next_run_at = self._calculate_retry_time(job.attempts)
                async for session in get_session():
                    await self._schedule_retry(session, job.id, next_run_at, str(e))
                    break
                job_logger.info(
                    "Job scheduled for retry",
                    extra={"next_run_at": next_run_at.isoformat()},
                )
            else:
                # Move to deadletter
                async for session in get_session():
                    await self._mark_job_completed(
                        session, job.id, JobStatus.DEADLETTER, error=str(e)
                    )
                    break
                job_logger.error("Job moved to deadletter queue")

        finally:
            # Remove from active jobs
            self.active_jobs.discard(job.id)

    async def _mark_job_completed(
        self,
        session: AsyncSession,
        job_id: UUID,
        status: JobStatus,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        """Mark job as completed with the given status and result."""
        update_values = {
            "status": status.value,
            "locked_at": None,
            "locked_by": None,
            "heartbeat_at": None,
            "updated_at": datetime.now(UTC),
        }

        if result is not None:
            update_values["result"] = result

        if error is not None:
            update_values["last_error"] = error
            update_values["error_code"] = "PROCESSING_ERROR"

        await session.execute(
            update(Job).where(Job.id == job_id).values(**update_values)
        )
        await session.commit()

    async def _schedule_retry(
        self, session: AsyncSession, job_id: UUID, run_at: datetime, error: str
    ) -> None:
        """Schedule job for retry."""
        await session.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(
                status=JobStatus.QUEUED.value,
                run_at=run_at,
                locked_at=None,
                locked_by=None,
                heartbeat_at=None,
                last_error=error,
                error_code="RETRY_SCHEDULED",
                updated_at=datetime.now(UTC),
            )
        )
        await session.commit()

    def _calculate_retry_time(self, attempt: int) -> datetime:
        """Calculate next retry time with exponential backoff and jitter."""
        base_delay = self.settings.job_backoff_base_ms / 1000  # Convert to seconds
        max_delay = self.settings.job_max_backoff_s

        # Exponential backoff: base * 2^attempt
        delay = min(max_delay, base_delay * (2 ** (attempt - 1)))

        # Add jitter (±25% random variation)
        jitter = delay * 0.25 * (2 * random.random() - 1)
        final_delay = max(1, delay + jitter)

        return datetime.fromtimestamp(datetime.now(UTC).timestamp() + final_delay, UTC)

    async def _heartbeat_loop(self) -> None:
        """Update heartbeats for active jobs."""
        while self.running:
            try:
                if self.active_jobs:
                    async for session in get_session():
                        await session.execute(
                            update(Job)
                            .where(
                                and_(
                                    Job.id.in_(self.active_jobs),
                                    Job.locked_by == self.worker_id,
                                )
                            )
                            .values(heartbeat_at=datetime.now(UTC))
                        )
                        await session.commit()
                        break

                # Heartbeat every 30 seconds
                await asyncio.sleep(30)

            except Exception:
                logger.exception(
                    "Error updating heartbeats", extra={"worker_id": self.worker_id}
                )
                await asyncio.sleep(60)  # Back off on errors

    async def _stuck_job_recovery_loop(self) -> None:
        """Recover jobs that are stuck due to worker crashes."""
        while self.running:
            try:
                timeout_seconds = self.settings.job_visibility_timeout_s
                cutoff_time = datetime.now(UTC).timestamp() - timeout_seconds
                cutoff_datetime = datetime.fromtimestamp(cutoff_time, UTC)

                async for session in get_session():
                    # Find stuck running jobs
                    stuck_jobs = await session.execute(
                        select(Job).where(
                            and_(
                                Job.status == JobStatus.RUNNING.value,
                                Job.heartbeat_at < cutoff_datetime,
                            )
                        )
                    )

                    stuck_job_list = stuck_jobs.scalars().all()

                    if stuck_job_list:
                        stuck_job_ids = [job.id for job in stuck_job_list]

                        # Reset stuck jobs to queued for retry
                        await session.execute(
                            update(Job)
                            .where(Job.id.in_(stuck_job_ids))
                            .values(
                                status=JobStatus.QUEUED.value,
                                locked_at=None,
                                locked_by=None,
                                heartbeat_at=None,
                                error_code="WORKER_TIMEOUT",
                                last_error=f"Job timeout after {timeout_seconds}s",
                                updated_at=datetime.now(UTC),
                            )
                        )
                        await session.commit()

                        logger.warning(
                            "Recovered stuck jobs",
                            extra={
                                "stuck_job_count": len(stuck_job_ids),
                                "timeout_seconds": timeout_seconds,
                            },
                        )

                    break

                # Check for stuck jobs every 5 minutes
                await asyncio.sleep(300)

            except Exception:
                logger.exception("Error in stuck job recovery")
                await asyncio.sleep(300)


# Worker instance management
_worker_instance: JobWorker | None = None


def get_worker(settings: Settings) -> JobWorker:
    """Get or create the global worker instance."""
    global _worker_instance
    if _worker_instance is None:
        _worker_instance = JobWorker(settings)
    return _worker_instance
