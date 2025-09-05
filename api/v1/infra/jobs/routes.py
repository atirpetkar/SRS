"""
Job management API endpoints for Step 11.

Provides admin endpoints for job enqueueing, monitoring, and management.
"""

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config.settings import Settings, SettingsDep
from api.infra.database import get_session
from api.v1.core.exceptions import create_success_response
from api.v1.core.security import Principal, PrincipalDep
from api.v1.infra.jobs.models import Job, JobStatus
from api.v1.infra.jobs.schemas import (
    JobActionRequest,
    JobActionResponse,
    JobCreate,
    JobEnqueueRequest,
    JobListResponse,
    JobResponse,
)
from api.v1.infra.jobs.service import JobService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", response_model=dict)
async def enqueue_job(
    job_request: JobEnqueueRequest,
    principal: Principal = PrincipalDep,
    session: AsyncSession = Depends(get_session),
    settings: Settings = SettingsDep,
) -> dict[str, Any]:
    """Enqueue a new background job."""

    job_service = JobService(settings)
    job_create = JobCreate(
        type=job_request.type,
        payload=job_request.payload,
        priority=job_request.priority,
        run_at=job_request.run_at,
        dedupe_key=job_request.dedupe_key,
    )

    try:
        result = await job_service.enqueue_job(session, job_create, principal)

        logger.info(
            "Job enqueued via API",
            extra={
                "job_id": str(result.job_id),
                "type": job_request.type,
                "org_id": str(principal.org_uuid),
                "deduplicated": result.deduplicated,
            },
        )

        return create_success_response(data=result.model_dump())

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Failed to enqueue job", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail="Failed to enqueue job")


@router.get("", response_model=dict)
async def list_jobs(
    status: list[JobStatus] | None = Query(
        default=None, description="Filter by status"
    ),
    type: str | None = Query(default=None, description="Filter by job type"),
    limit: int = Query(default=50, ge=1, le=1000, description="Maximum results"),
    offset: int = Query(default=0, ge=0, description="Results offset"),
    principal: Principal = PrincipalDep,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """List jobs with filtering and pagination."""

    # Build query with org isolation
    base_query = select(Job).where(Job.org_id == principal.org_uuid)

    if status:
        status_values = [s.value for s in status]
        base_query = base_query.where(Job.status.in_(status_values))

    if type:
        base_query = base_query.where(Job.type == type)

    # Order by creation time (newest first)
    base_query = base_query.order_by(desc(Job.created_at))

    # Get total count
    count_query = select(func.count()).select_from(base_query.subquery())
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    # Get jobs with pagination
    jobs_query = base_query.offset(offset).limit(limit)
    jobs_result = await session.execute(jobs_query)
    jobs = jobs_result.scalars().all()

    # Convert to response objects
    job_responses = []
    for job in jobs:
        job_data = JobResponse.model_validate(job)
        job_data.progress_percentage = job.get_progress_percentage()
        job_responses.append(job_data)

    response_data = JobListResponse(
        jobs=job_responses,
        total=total,
        limit=limit,
        offset=offset,
    )

    return create_success_response(data=response_data.model_dump())


@router.get("/{job_id}", response_model=dict)
async def get_job(
    job_id: UUID,
    principal: Principal = PrincipalDep,
    session: AsyncSession = Depends(get_session),
    settings: Settings = SettingsDep,
) -> dict[str, Any]:
    """Get a specific job by ID."""

    job_service = JobService(settings)
    job = await job_service.get_job_by_id(session, job_id, principal.org_uuid)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job_data = JobResponse.model_validate(job)
    job_data.progress_percentage = job.get_progress_percentage()

    return create_success_response(data=job_data.model_dump())


@router.get("/stats/overview", response_model=dict)
async def get_job_stats(
    principal: Principal = PrincipalDep,
    session: AsyncSession = Depends(get_session),
    settings: Settings = SettingsDep,
) -> dict[str, Any]:
    """Get job statistics for the organization."""

    job_service = JobService(settings)
    stats = await job_service.get_job_stats(session, principal.org_uuid)

    return create_success_response(data=stats.model_dump())


@router.post("/{job_id}/retry", response_model=dict)
async def retry_job(
    job_id: UUID,
    principal: Principal = PrincipalDep,
    session: AsyncSession = Depends(get_session),
    settings: Settings = SettingsDep,
) -> dict[str, Any]:
    """Retry a failed job."""

    job_service = JobService(settings)
    success = await job_service.retry_job(session, job_id, principal.org_uuid)

    if not success:
        raise HTTPException(
            status_code=404, detail="Job not found or not eligible for retry"
        )

    logger.info(
        "Job retried via API",
        extra={
            "job_id": str(job_id),
            "org_id": str(principal.org_uuid),
            "user_id": principal.user_id,
        },
    )

    return create_success_response(data={"success": True, "job_id": str(job_id)})


@router.post("/{job_id}/cancel", response_model=dict)
async def cancel_job(
    job_id: UUID,
    principal: Principal = PrincipalDep,
    session: AsyncSession = Depends(get_session),
    settings: Settings = SettingsDep,
) -> dict[str, Any]:
    """Cancel a queued or running job."""

    job_service = JobService(settings)
    success = await job_service.cancel_job(session, job_id, principal.org_uuid)

    if not success:
        raise HTTPException(
            status_code=404, detail="Job not found or not eligible for cancellation"
        )

    logger.info(
        "Job canceled via API",
        extra={
            "job_id": str(job_id),
            "org_id": str(principal.org_uuid),
            "user_id": principal.user_id,
        },
    )

    return create_success_response(data={"success": True, "job_id": str(job_id)})


@router.post("/batch/retry", response_model=dict)
async def retry_jobs_batch(
    request: JobActionRequest,
    principal: Principal = PrincipalDep,
    session: AsyncSession = Depends(get_session),
    settings: Settings = SettingsDep,
) -> dict[str, Any]:
    """Retry multiple jobs in batch."""

    job_service = JobService(settings)
    success_ids = []
    failed_ids = []
    errors = {}

    for job_id in request.job_ids:
        try:
            success = await job_service.retry_job(session, job_id, principal.org_uuid)
            if success:
                success_ids.append(job_id)
            else:
                failed_ids.append(job_id)
                errors[str(job_id)] = "Job not found or not eligible for retry"
        except Exception as e:
            failed_ids.append(job_id)
            errors[str(job_id)] = str(e)

    logger.info(
        "Batch job retry via API",
        extra={
            "success_count": len(success_ids),
            "failed_count": len(failed_ids),
            "org_id": str(principal.org_uuid),
        },
    )

    response = JobActionResponse(
        success_ids=success_ids, failed_ids=failed_ids, errors=errors
    )

    return create_success_response(data=response.model_dump())


@router.post("/batch/cancel", response_model=dict)
async def cancel_jobs_batch(
    request: JobActionRequest,
    principal: Principal = PrincipalDep,
    session: AsyncSession = Depends(get_session),
    settings: Settings = SettingsDep,
) -> dict[str, Any]:
    """Cancel multiple jobs in batch."""

    job_service = JobService(settings)
    success_ids = []
    failed_ids = []
    errors = {}

    for job_id in request.job_ids:
        try:
            success = await job_service.cancel_job(session, job_id, principal.org_uuid)
            if success:
                success_ids.append(job_id)
            else:
                failed_ids.append(job_id)
                errors[str(job_id)] = "Job not found or not eligible for cancellation"
        except Exception as e:
            failed_ids.append(job_id)
            errors[str(job_id)] = str(e)

    logger.info(
        "Batch job cancel via API",
        extra={
            "success_count": len(success_ids),
            "failed_count": len(failed_ids),
            "org_id": str(principal.org_uuid),
        },
    )

    response = JobActionResponse(
        success_ids=success_ids, failed_ids=failed_ids, errors=errors
    )

    return create_success_response(data=response.model_dump())


# Embedding-specific convenience endpoints


@router.post("/embeddings/rebuild", response_model=dict)
async def rebuild_embeddings(
    force: bool = Query(
        default=False, description="Force recompute existing embeddings"
    ),
    principal: Principal = PrincipalDep,
    session: AsyncSession = Depends(get_session),
    settings: Settings = SettingsDep,
) -> dict[str, Any]:
    """Enqueue a job to rebuild all embeddings for the organization."""

    job_service = JobService(settings)

    # Generate dedupe key for org-scoped embedding rebuild
    dedupe_key = job_service.generate_dedupe_key(
        "compute_embeddings_batch",
        org_id=str(principal.org_uuid),
        force_recompute=force,
    )

    job_create = JobCreate(
        type="compute_embeddings_batch",
        payload={
            "org_id": str(principal.org_uuid),
            "force_recompute": force,
            "batch_size": 100,
        },
        priority=6,  # Lower priority for batch operations
        dedupe_key=dedupe_key,
    )

    try:
        result = await job_service.enqueue_job(session, job_create, principal)

        logger.info(
            "Embedding rebuild job enqueued",
            extra={
                "job_id": str(result.job_id),
                "org_id": str(principal.org_uuid),
                "force_recompute": force,
                "deduplicated": result.deduplicated,
            },
        )

        return create_success_response(data=result.model_dump())

    except Exception as e:
        logger.exception(
            "Failed to enqueue embedding rebuild job", extra={"error": str(e)}
        )
        raise HTTPException(
            status_code=500, detail="Failed to enqueue embedding rebuild job"
        )
