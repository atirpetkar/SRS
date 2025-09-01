from typing import Any
from uuid import NAMESPACE_DNS, UUID, uuid5

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import Text, and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.config.settings import Settings, SettingsDep
from api.infra.database import SessionDep
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

router = APIRouter()

# Module-level dependency instances to avoid B008 violations
_item_filters_dep = Depends()


def string_to_uuid(text: str) -> UUID:
    """Convert a string to a deterministic UUID using namespace DNS."""
    return uuid5(NAMESPACE_DNS, text)


async def ensure_dev_entities_exist(session: AsyncSession, principal: Principal):
    """Ensure dev organization and user exist in the database."""
    org_uuid = string_to_uuid(principal.org_id)
    user_uuid = string_to_uuid(principal.user_id)

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
                Item.org_id == string_to_uuid(principal.org_id),
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
        org_id=string_to_uuid(principal.org_id),
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
    """List items with filtering, search, and pagination."""

    # Determine search method based on environment
    use_tsvector = settings.environment in ("production", "staging")

    # Base conditions that always apply
    base_conditions = [
        Item.org_id == string_to_uuid(principal.org_id),
        Item.deleted_at.is_(None),
    ]

    # Additional filter conditions
    filter_conditions = []

    if filters.type:
        filter_conditions.append(Item.type == filters.type)

    if filters.status:
        filter_conditions.append(Item.status == filters.status)

    if filters.difficulty:
        filter_conditions.append(Item.difficulty == filters.difficulty)

    if filters.source_id:
        filter_conditions.append(Item.source_id == filters.source_id)

    if filters.created_by:
        filter_conditions.append(Item.created_by == filters.created_by)

    if filters.tags:
        # Match items that have ANY of the specified tags
        tag_conditions = [Item.tags.contains([tag]) for tag in filters.tags]
        filter_conditions.append(or_(*tag_conditions))

    # Combine all non-search conditions
    all_conditions = base_conditions + filter_conditions

    # Build query based on search presence
    if filters.q:
        # Search is active - use environment-appropriate method
        if use_tsvector:
            # Production: Use tsvector with text ranking
            search_condition = Item.search_document.op("@@")(
                func.to_tsquery("english", filters.q)
            )
            all_conditions.append(search_condition)

            # Add text rank for ordering
            rank_expr = func.ts_rank_cd(
                Item.search_document, func.to_tsquery("english", filters.q)
            )
            query = select(Item, rank_expr.label("search_rank")).where(
                and_(*all_conditions)
            )

        else:
            # Dev/Test: Use ILIKE fallback on canonical text
            # We'll need to construct the canonical text in SQL or filter after fetch
            # For now, let's use a simple ILIKE on the JSON payload as fallback
            search_text = f"%{filters.q}%"
            search_condition = or_(
                func.cast(Item.payload, Text).ilike(search_text),
                func.array_to_string(Item.tags, " ").ilike(search_text),
                Item.type.ilike(search_text),
            )
            all_conditions.append(search_condition)
            query = select(Item).where(and_(*all_conditions))
    else:
        # No search - standard filtering
        query = select(Item).where(and_(*all_conditions))

    # Get total count for pagination (without limit/offset)
    if filters.q and use_tsvector:
        # For search queries, need to count the search results
        count_query = select(func.count()).select_from(query.subquery())
    else:
        count_query = select(func.count(Item.id)).where(and_(*all_conditions))

    count_result = await session.execute(count_query)
    total = count_result.scalar()

    # Apply ordering
    if filters.q and use_tsvector:
        # Order by text rank (descending) then recency (descending)
        query = query.order_by(text("search_rank DESC"), Item.created_at.desc())
    else:
        # Standard recency ordering
        query = query.order_by(Item.created_at.desc())

    # Apply pagination
    query = query.offset(filters.offset).limit(filters.limit)
    query = query.options(selectinload(Item.source))

    # Execute the query
    result = await session.execute(query)

    if filters.q and use_tsvector:
        # Extract items from the tuple results (Item, search_rank)
        items = [row[0] for row in result.all()]
    else:
        items = result.scalars().all()

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


@router.post("/items/import", response_model=ImportResult)
async def import_items(
    import_request: ImportRequest,
    principal: Principal = PrincipalDep,
    session: AsyncSession = SessionDep,
):
    """Import items from external content and stage them as drafts."""

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
    org_uuid = string_to_uuid(principal.org_id)

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

    return ImportResult(
        staged_ids=staged_ids,
        warnings=warnings,
        diagnostics=diagnostics,
        total_parsed=len(parsed_items),
        total_created=len(staged_ids),
        total_errors=total_errors,
    )


@router.get("/items/staged", response_model=ItemList)
async def list_staged_items(
    filters: ItemFilters = _item_filters_dep,
    principal: Principal = PrincipalDep,
    session: AsyncSession = SessionDep,
):
    """List items in draft status (staged for approval)."""

    # Force status to 'draft' for staged items
    filters.status = "draft"

    return await list_items(filters, principal, session)


@router.post("/items/approve", response_model=ApprovalResult)
async def approve_items(
    approval_request: ApprovalRequest,
    principal: Principal = PrincipalDep,
    session: AsyncSession = SessionDep,
):
    """Approve staged items by changing their status to published."""

    approved_ids = []
    failed_ids = []
    errors = {}
    org_uuid = string_to_uuid(principal.org_id)

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

        except Exception as e:
            failed_ids.append(item_id)
            errors[str(item_id)] = str(e)

    # Commit all changes
    await session.commit()

    return ApprovalResult(
        approved_ids=approved_ids, failed_ids=failed_ids, errors=errors
    )


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
