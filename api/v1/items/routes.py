from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.config.settings import Settings, SettingsDep
from api.infra.database import SessionDep
from api.v1.core.idempotency import get_idempotency_key, handle_idempotent_request
from api.v1.core.registries import importer_registry, item_type_registry
from api.v1.core.security import Principal, PrincipalDep
from api.v1.items.models import Item, Organization, User
from api.v1.items.schemas import (
    ApprovalRequest,
    ApprovalResult,
    ImportDiagnostic,
    ImportRequest,
    ImportResult,
    ItemCreate,
    ItemFilters,
    ItemList,
    ItemResponse,
    ItemUpdate,
)
from api.v1.items.utils import content_hash
from api.v1.search.embedding_service import EmbeddingService
from api.v1.search.hybrid_search import HybridSearchService

router = APIRouter()

# Module-level dependency instances to avoid B008 violations
_item_filters_dep = Depends()


async def ensure_dev_entities_exist(session: AsyncSession, principal: Principal):
    """Ensure dev organization and user exist in the database."""
    org_uuid = principal.org_uuid
    user_uuid = principal.user_uuid

    # Check if org exists
    org_result = await session.execute(
        select(Organization).where(Organization.id == org_uuid)
    )
    org = org_result.scalar_one_or_none()

    if not org:
        # Create the organization
        org = Organization(
            id=org_uuid, name=principal.org_id, meta={"created_for": "development"}
        )
        session.add(org)

    # Check if user exists
    user_result = await session.execute(select(User).where(User.id == user_uuid))
    user = user_result.scalar_one_or_none()

    if not user:
        # Create the user
        user = User(
            id=user_uuid,
            email=f"{principal.user_id}@dev.local",
            org_id=org_uuid,
            meta={"created_for": "development"},
        )
        session.add(user)

    await session.commit()


async def get_item_by_id(
    item_id: UUID,
    principal: Principal,
    session: AsyncSession,
) -> Item:
    """Get an item by ID, ensuring it belongs to the user's org."""
    result = await session.execute(
        select(Item)
        .where(
            and_(
                Item.id == item_id,
                Item.org_id == principal.org_uuid,
                Item.deleted_at.is_(None),
            )
        )
        .options(selectinload(Item.source))
    )

    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Item not found"
        )

    return item


@router.post("/items", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
async def create_item(
    item_data: ItemCreate,
    principal: Principal = PrincipalDep,
    session: AsyncSession = SessionDep,
):
    """Create a new item."""

    # Ensure dev entities exist
    await ensure_dev_entities_exist(session, principal)

    # Validate payload using the appropriate validator
    try:
        validator = item_type_registry.get(item_data.type)
        validated_payload = validator.validate(item_data.payload)
    except KeyError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown item type: {item_data.type}",
        ) from e
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from e

    # Generate content hash
    hash_value = content_hash(item_data.type, validated_payload)

    # Create the item
    item = Item(
        org_id=principal.org_uuid,
        type=item_data.type,
        payload=validated_payload,
        tags=item_data.tags or [],
        difficulty=item_data.difficulty,
        source_id=item_data.source_id,
        media=item_data.media or {},
        meta=item_data.meta or {},
        content_hash=hash_value,
        created_by=principal.user_id,
        status="draft",
    )

    session.add(item)
    await session.commit()
    await session.refresh(item)

    return ItemResponse.model_validate(item)


@router.get("/items", response_model=ItemList)
async def list_items(
    filters: ItemFilters = _item_filters_dep,
    principal: Principal = PrincipalDep,
    session: AsyncSession = SessionDep,
    settings: Settings = SettingsDep,
):
    """List items with hybrid search, filtering, and pagination."""

    # Ensure dev entities exist
    await ensure_dev_entities_exist(session, principal)

    # Use hybrid search service for enhanced search capabilities
    search_service = HybridSearchService(settings)

    # Convert filters to dict for search service
    filter_dict = {}
    if filters.type:
        filter_dict["type"] = filters.type
    if filters.status:
        filter_dict["status"] = filters.status
    if filters.difficulty:
        filter_dict["difficulty"] = filters.difficulty
    if filters.source_id:
        filter_dict["source_id"] = filters.source_id
    if filters.created_by:
        filter_dict["created_by"] = filters.created_by
    if filters.tags:
        filter_dict["tags"] = filters.tags

    # Perform search
    items, total = await search_service.search_items(
        session=session,
        org_id=principal.org_uuid,
        query=filters.q,
        filters=filter_dict,
        limit=filters.limit,
        offset=filters.offset,
    )

    # Convert to response format
    item_responses = [ItemResponse.model_validate(item) for item in items]

    return ItemList(
        items=item_responses,
        total=total,
        offset=filters.offset,
        limit=filters.limit,
        has_more=filters.offset + len(items) < total,
    )


# Import endpoints - placed here to avoid route conflicts


async def _perform_import(
    import_request: ImportRequest,
    principal: Principal,
    session: AsyncSession,
    settings: Settings,
) -> tuple[dict, int]:
    """Perform the actual import operation."""
    # Ensure dev entities exist
    await ensure_dev_entities_exist(session, principal)

    # Get the appropriate importer
    try:
        importer = importer_registry.get(import_request.format)
    except KeyError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported import format: {import_request.format}",
        ) from e

    # Parse the content
    diagnostics = []
    try:
        parsed_items = importer.parse(import_request.data, diagnostics=diagnostics)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error parsing {import_request.format} content: {str(e)}",
        ) from e

    # Validate and create items
    staged_ids = []
    warnings = []
    total_errors = 0
    org_uuid = principal.org_uuid

    # Check for batch constraints (max 5k items)
    if len(parsed_items) > 5000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot import more than 5000 items in a single batch",
        )

    for parsed_item in parsed_items:
        try:
            # Validate the item type
            if parsed_item.get("type") not in {
                "flashcard",
                "mcq",
                "cloze",
                "short_answer",
            }:
                diagnostics.append(
                    ImportDiagnostic(
                        issue=f"Invalid item type: {parsed_item.get('type')}",
                        severity="error",
                    )
                )
                total_errors += 1
                continue

            # Validate payload using the appropriate validator
            validator = item_type_registry.get(parsed_item["type"])
            validated_payload = validator.validate(parsed_item["payload"])

            # Generate content hash and check for potential duplicates
            hash_value = content_hash(parsed_item["type"], validated_payload)

            # Check for existing items with same hash in same org
            existing_result = await session.execute(
                select(Item).where(
                    and_(
                        Item.org_id == org_uuid,
                        Item.content_hash == hash_value,
                        Item.deleted_at.is_(None),
                    )
                )
            )

            existing_item = existing_result.scalar_one_or_none()
            if existing_item:
                warnings.append(
                    f"Potential duplicate detected for {parsed_item['type']} (existing ID: {existing_item.id})"
                )

            # Additional duplicate detection using embeddings (if available)
            try:
                embedding_service = EmbeddingService(settings)

                # Create a temporary item object for duplicate detection
                temp_item = Item(
                    org_id=org_uuid,
                    type=parsed_item["type"],
                    payload=validated_payload,
                    tags=parsed_item.get("tags", []),
                )
                temp_item.id = None  # Ensure it's not confused with existing item

                # Check for semantic duplicates using embeddings
                similar_items = await embedding_service.detect_duplicates(
                    session, temp_item, threshold=0.90
                )

                for similar_item, similarity in similar_items:
                    warnings.append(
                        f"High similarity ({similarity:.2f}) detected with item {similar_item.id} "
                        f"for {parsed_item['type']}"
                    )

            except Exception:
                # Don't fail import if embedding-based duplicate detection fails
                # This could happen if vectorizer is not available or other issues
                pass

            # Create the item
            item = Item(
                org_id=org_uuid,
                type=parsed_item["type"],
                payload=validated_payload,
                tags=parsed_item.get("tags", []),
                difficulty=parsed_item.get("difficulty"),
                source_id=import_request.source_id,
                media={},  # Will be handled separately in future steps
                meta={
                    **(import_request.metadata or {}),
                    **parsed_item.get("metadata", {}),
                },
                content_hash=hash_value,
                created_by=principal.user_id,
                status="draft",  # Always create as draft for staging
            )

            session.add(item)
            await session.flush()  # Get the ID without committing
            staged_ids.append(item.id)

        except ValueError as e:
            # Validation error
            diagnostics.append(
                ImportDiagnostic(
                    issue=f"Validation error for {parsed_item.get('type', 'unknown')}: {str(e)}",
                    severity="error",
                )
            )
            total_errors += 1
        except Exception as e:
            # Unexpected error
            diagnostics.append(
                ImportDiagnostic(
                    issue=f"Unexpected error for {parsed_item.get('type', 'unknown')}: {str(e)}",
                    severity="error",
                )
            )
            total_errors += 1

    # Commit all successful items
    await session.commit()

    result = ImportResult(
        staged_ids=staged_ids,
        warnings=warnings,
        diagnostics=diagnostics,
        total_parsed=len(parsed_items),
        total_created=len(staged_ids),
        total_errors=total_errors,
    )

    # Return as (dict, status_code) tuple for idempotency wrapper
    return result.model_dump(), 200


@router.post("/items/import", response_model=ImportResult)
async def import_items(
    import_request: ImportRequest,
    principal: Principal = PrincipalDep,
    session: AsyncSession = SessionDep,
    settings: Settings = SettingsDep,
    idempotency_key: str | None = Depends(get_idempotency_key),
):
    """Import items from external content and stage them as drafts."""

    # Handle idempotent request
    response_data, status_code = await handle_idempotent_request(
        session,
        principal,
        "items_import",
        idempotency_key,
        _perform_import,
        import_request,
        principal,
        session,
        settings,
    )

    return ImportResult.model_validate(response_data)


@router.get("/items/staged", response_model=ItemList)
async def list_staged_items(
    filters: ItemFilters = _item_filters_dep,
    principal: Principal = PrincipalDep,
    session: AsyncSession = SessionDep,
    settings: Settings = SettingsDep,
):
    """List items in draft status (staged for approval)."""

    # Force status to 'draft' for staged items
    filters.status = "draft"

    return await list_items(filters, principal, session, settings)


async def _perform_approval(
    approval_request: ApprovalRequest,
    principal: Principal,
    session: AsyncSession,
    settings: Settings,
) -> tuple[dict, int]:
    """Approve staged items by changing their status to published."""

    approved_ids = []
    failed_ids = []
    errors = {}
    org_uuid = principal.org_uuid

    for item_id in approval_request.ids:
        try:
            # Get the item and verify it's in draft status
            result = await session.execute(
                select(Item).where(
                    and_(
                        Item.id == item_id,
                        Item.org_id == org_uuid,
                        Item.status == "draft",
                        Item.deleted_at.is_(None),
                    )
                )
            )

            item = result.scalar_one_or_none()
            if not item:
                failed_ids.append(item_id)
                errors[str(item_id)] = "Item not found or not in draft status"
                continue

            # Approve the item
            item.status = "published"
            approved_ids.append(item_id)

            # Compute embedding for newly published item
            if settings.embeddings_async:
                # Async embedding via job system
                try:
                    from api.v1.core.registries import vectorizer_registry
                    from api.v1.infra.jobs.schemas import JobCreate
                    from api.v1.infra.jobs.service import JobService

                    job_service = JobService(settings)
                    vectorizer = vectorizer_registry.get(settings.embeddings.value)

                    # Generate dedupe key for idempotent job processing
                    dedupe_key = job_service.generate_dedupe_key(
                        "compute_item_embedding",
                        item_id=str(item.id),
                        model_version=vectorizer.get_model_version(),
                    )

                    job_create = JobCreate(
                        type="compute_item_embedding",
                        payload={
                            "item_id": str(item.id),
                            "model_version": vectorizer.get_model_version(),
                            "force_recompute": False,
                        },
                        priority=3,  # Higher priority for item approvals
                        dedupe_key=dedupe_key,
                    )

                    await job_service.enqueue_job(session, job_create, principal)

                except Exception:
                    # Don't fail approval if job enqueueing fails
                    # This ensures the core functionality works even if jobs are unavailable
                    pass
            else:
                # Sync embedding (legacy mode)
                try:
                    embedding_service = EmbeddingService(settings)
                    await embedding_service.compute_embedding_for_item(session, item)
                except Exception:
                    # Don't fail approval if embedding computation fails
                    # This ensures the core functionality works even if embeddings are unavailable
                    pass

        except Exception as e:
            failed_ids.append(item_id)
            errors[str(item_id)] = str(e)

    # Commit all changes
    await session.commit()

    result = ApprovalResult(
        approved_ids=approved_ids, failed_ids=failed_ids, errors=errors
    )

    # Return as (dict, status_code) tuple for idempotency wrapper
    return result.model_dump(), 200


@router.post("/items/approve", response_model=ApprovalResult)
async def approve_items(
    approval_request: ApprovalRequest,
    principal: Principal = PrincipalDep,
    session: AsyncSession = SessionDep,
    settings: Settings = SettingsDep,
    idempotency_key: str | None = Depends(get_idempotency_key),
):
    """Approve staged items by changing their status to published."""

    # Handle idempotent request
    response_data, status_code = await handle_idempotent_request(
        session,
        principal,
        "items_approve",
        idempotency_key,
        _perform_approval,
        approval_request,
        principal,
        session,
        settings,
    )

    return ApprovalResult.model_validate(response_data)


@router.get("/items/{item_id}", response_model=ItemResponse)
async def get_item(
    item_id: UUID,
    principal: Principal = PrincipalDep,
    session: AsyncSession = SessionDep,
):
    """Get a specific item by ID."""
    item = await get_item_by_id(item_id, principal, session)
    return ItemResponse.model_validate(item)


@router.patch("/items/{item_id}", response_model=ItemResponse)
async def update_item(
    item_id: UUID,
    update_data: ItemUpdate,
    principal: Principal = PrincipalDep,
    session: AsyncSession = SessionDep,
):
    """Update an existing item."""
    item = await get_item_by_id(item_id, principal, session)

    # Track if we need to regenerate the content hash
    needs_rehash = False

    # Update payload if provided
    if update_data.payload is not None:
        try:
            validator = item_type_registry.get(item.type)
            validated_payload = validator.validate(update_data.payload)
            item.payload = validated_payload
            needs_rehash = True
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
            ) from e

    # Update other fields
    if update_data.tags is not None:
        item.tags = update_data.tags
        needs_rehash = True

    if update_data.difficulty is not None:
        item.difficulty = update_data.difficulty

    if update_data.media is not None:
        item.media = update_data.media

    if update_data.meta is not None:
        item.meta = update_data.meta

    if update_data.status is not None:
        item.status = update_data.status

    # Regenerate content hash if content changed
    if needs_rehash:
        item.content_hash = content_hash(item.type, item.payload)
        item.version += 1

    await session.commit()
    await session.refresh(item)

    return ItemResponse.model_validate(item)


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: UUID,
    principal: Principal = PrincipalDep,
    session: AsyncSession = SessionDep,
):
    """Soft delete an item."""
    item = await get_item_by_id(item_id, principal, session)

    # Soft delete by setting deleted_at timestamp
    from datetime import datetime

    item.deleted_at = datetime.utcnow()

    await session.commit()


@router.post("/items/{item_id}/render", response_model=dict[str, Any])
async def render_item(
    item_id: UUID,
    principal: Principal = PrincipalDep,
    session: AsyncSession = SessionDep,
):
    """Render an item for display/practice."""
    item = await get_item_by_id(item_id, principal, session)

    try:
        validator = item_type_registry.get(item.type)
        rendered = validator.render(item.payload)
        return rendered
    except KeyError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"No validator found for item type: {item.type}",
        ) from e


@router.get("/items/{item_id}/similar", response_model=list[dict[str, Any]])
async def find_similar_items(
    item_id: UUID,
    threshold: float = 0.85,
    limit: int = 10,
    principal: Principal = PrincipalDep,
    session: AsyncSession = SessionDep,
    settings: Settings = SettingsDep,
):
    """Find items similar to the given item using embeddings."""
    item = await get_item_by_id(item_id, principal, session)

    try:
        search_service = HybridSearchService(settings)
        similar_items = await search_service.find_similar_items(
            session, item, threshold, limit
        )

        return [
            {
                "item": ItemResponse.model_validate(similar_item).model_dump(),
                "similarity_score": float(similarity),
            }
            for similar_item, similarity in similar_items
        ]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error finding similar items: {str(e)}",
        ) from e


@router.post("/items/{item_id}/compute-embedding", response_model=dict[str, Any])
async def compute_item_embedding(
    item_id: UUID,
    force: bool = False,
    principal: Principal = PrincipalDep,
    session: AsyncSession = SessionDep,
    settings: Settings = SettingsDep,
):
    """Manually compute embedding for a specific item."""
    item = await get_item_by_id(item_id, principal, session)

    try:
        embedding_service = EmbeddingService(settings)
        embedding = await embedding_service.compute_embedding_for_item(
            session, item, force_recompute=force
        )

        return {
            "item_id": str(embedding.item_id),
            "model_version": embedding.model_version,
            "embedding_dimension": len(embedding.embedding),
            "created_at": embedding.created_at.isoformat(),
            "metadata": embedding.meta,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error computing embedding: {str(e)}",
        ) from e


@router.get("/items/embedding-stats", response_model=dict[str, Any])
async def get_embedding_stats(
    principal: Principal = PrincipalDep,
    session: AsyncSession = SessionDep,
    settings: Settings = SettingsDep,
):
    """Get statistics about embeddings for the organization."""
    try:
        embedding_service = EmbeddingService(settings)
        stats = await embedding_service.get_embedding_stats(session, principal.org_uuid)
        return stats
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting embedding stats: {str(e)}",
        ) from e
