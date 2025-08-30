from typing import Any
from uuid import UUID, uuid5, NAMESPACE_DNS

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.infra.database import SessionDep
from api.v1.core.registries import item_type_registry
from api.v1.core.security import Principal, PrincipalDep
from api.v1.items.models import Item, Organization, User
from api.v1.items.schemas import ItemCreate, ItemFilters, ItemList, ItemResponse, ItemUpdate
from api.v1.items.utils import content_hash

router = APIRouter()


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
            id=org_uuid,
            name=principal.org_id,
            meta={"created_for": "development"}
        )
        session.add(org)
    
    # Check if user exists
    user_result = await session.execute(
        select(User).where(User.id == user_uuid)
    )
    user = user_result.scalar_one_or_none()
    
    if not user:
        # Create the user
        user = User(
            id=user_uuid,
            email=f"{principal.user_id}@dev.local",
            org_id=org_uuid,
            meta={"created_for": "development"}
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
                Item.deleted_at.is_(None)
            )
        )
        .options(selectinload(Item.source))
    )
    
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found"
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
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown item type: {item_data.type}"
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    
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
        status="draft"
    )
    
    session.add(item)
    await session.commit()
    await session.refresh(item)
    
    return ItemResponse.model_validate(item)


@router.get("/items", response_model=ItemList)
async def list_items(
    filters: ItemFilters = Depends(),
    principal: Principal = PrincipalDep,
    session: AsyncSession = SessionDep,
):
    """List items with filtering and pagination."""
    
    # Build the base query
    query = select(Item).where(
        and_(
            Item.org_id == string_to_uuid(principal.org_id),
            Item.deleted_at.is_(None)
        )
    )
    
    # Apply filters
    conditions = []
    
    if filters.type:
        conditions.append(Item.type == filters.type)
    
    if filters.status:
        conditions.append(Item.status == filters.status)
    
    if filters.difficulty:
        conditions.append(Item.difficulty == filters.difficulty)
    
    if filters.source_id:
        conditions.append(Item.source_id == filters.source_id)
    
    if filters.created_by:
        conditions.append(Item.created_by == filters.created_by)
    
    if filters.tags:
        # Match items that have ANY of the specified tags
        tag_conditions = [Item.tags.contains([tag]) for tag in filters.tags]
        conditions.append(or_(*tag_conditions))
    
    if conditions:
        query = query.where(and_(*conditions))
    
    # Get total count for pagination
    count_query = select(Item.id).where(query.whereclause)
    count_result = await session.execute(count_query)
    total = len(count_result.all())
    
    # Apply pagination and ordering
    query = query.order_by(Item.created_at.desc()).offset(filters.offset).limit(filters.limit)
    query = query.options(selectinload(Item.source))
    
    # Execute the query
    result = await session.execute(query)
    items = result.scalars().all()
    
    # Convert to response format
    item_responses = [ItemResponse.model_validate(item) for item in items]
    
    return ItemList(
        items=item_responses,
        total=total,
        offset=filters.offset,
        limit=filters.limit,
        has_more=filters.offset + len(items) < total
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
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )
    
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
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"No validator found for item type: {item.type}"
        )