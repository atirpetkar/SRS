"""
API routes for content generation (Step 9).

Provides endpoints for generating educational items from text using rule-based methods.
"""

import time
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.config.settings import Settings, SettingsDep
from api.infra.database import SessionDep
from api.v1.core.registries import generator_registry
from api.v1.core.security import Principal, PrincipalDep
from api.v1.gen.schemas import (
    GenerateRequest,
    GenerateResponse,
    GenerationDiagnostics,
    RejectedItem,
)
from api.v1.items.models import Item
from api.v1.items.routes import ensure_dev_entities_exist
from api.v1.items.utils import normalize_tags, validate_difficulty
from api.v1.search.embedding_service import EmbeddingService

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.post("/items/generate", response_model=GenerateResponse)
async def generate_items(
    request: GenerateRequest,
    principal: Principal = PrincipalDep,
    settings: Settings = SettingsDep,
    session: AsyncSession = SessionDep,
) -> GenerateResponse:
    """
    Generate educational items from text using rule-based methods.

    This endpoint creates draft items that can be reviewed and approved later.
    Items are generated offline using deterministic NLP rules without external APIs.

    Args:
        request: Generation request parameters
        principal: Current user context
        settings: Application settings
        session: Database session

    Returns:
        Generated items with diagnostics and quality gate information

    Raises:
        HTTPException: If generation fails or input is invalid
    """
    start_time = time.time()

    try:
        # Validate input - either text or topic must be provided
        if not request.text and not request.topic:
            raise HTTPException(
                status_code=400, detail="Either 'text' or 'topic' must be provided"
            )

        # Use topic as fallback if text is not provided
        input_text = (
            request.text or f"Generate educational content about: {request.topic}"
        )

        # Validate text length
        if len(input_text.strip()) < 50:
            raise HTTPException(
                status_code=400, detail="Input text must be at least 50 characters long"
            )

        # Ensure dev entities exist (for dev mode)
        await ensure_dev_entities_exist(session, principal)

        # Get the generator
        generator = generator_registry.get("basic_rules")

        logger.info(
            "Starting content generation",
            text_length=len(input_text),
            types=request.types,
            count=request.count,
            difficulty=request.difficulty,
            user_id=principal.user_id,
            org_id=principal.org_id,
        )

        # Generate items
        generated_items = generator.generate(
            text=input_text,
            item_types=request.types,
            count=request.count,
            difficulty=request.difficulty,
        )

        # Validate and normalize generated items
        validated_items = []
        rejected_items = []
        warnings = []

        for item_data in generated_items:
            try:
                # Validate difficulty
                if item_data.get("difficulty"):
                    item_data["difficulty"] = validate_difficulty(
                        item_data["difficulty"]
                    )

                # Normalize tags
                item_data["tags"] = normalize_tags(item_data.get("tags", []))

                # Add org context
                item_data["metadata"]["org_id"] = principal.org_id
                item_data["metadata"]["created_by"] = principal.user_id

                validated_items.append(item_data)

            except ValueError as e:
                rejected_items.append(
                    RejectedItem(
                        item=item_data, reason="validation_error", details=str(e)
                    )
                )
                warnings.append(f"Item validation failed: {str(e)}")

        # Check for potential duplicates using embedding similarity
        if settings.embeddings != "stub":
            try:
                embedding_service = EmbeddingService(settings)

                for item_data in validated_items[
                    :5
                ]:  # Check only first 5 for performance
                    # Create temporary item for duplicate check
                    temp_item = Item(
                        org_id=principal.org_uuid,
                        type=item_data["type"],
                        payload=item_data["payload"],
                        tags=item_data["tags"],
                        status="draft",
                    )

                    duplicates = await embedding_service.detect_duplicates(
                        session, temp_item, threshold=0.90
                    )

                    if duplicates:
                        duplicate_ids = [dup[0].id for dup in duplicates]
                        item_data["metadata"]["potential_duplicates"] = duplicate_ids
                        warnings.append(
                            f"Item may be similar to existing items: {duplicate_ids}"
                        )

            except Exception as e:
                logger.warning(
                    "Duplicate detection failed",
                    error=str(e),
                    user_id=principal.user_id,
                )
                warnings.append(
                    "Duplicate detection was skipped due to technical issues"
                )

        # Create draft items in database
        staged_ids = []
        for item_data in validated_items:
            item = Item(
                org_id=principal.org_uuid,
                type=item_data["type"],
                payload=item_data["payload"],
                tags=item_data["tags"],
                difficulty=item_data.get("difficulty"),
                status="draft",  # Generated items start as drafts
                meta=item_data["metadata"],
                created_by=principal.user_id,
            )

            session.add(item)
            await session.flush()  # Get the ID
            staged_ids.append(item.id)

        await session.commit()

        # Build diagnostics
        processing_time = int((time.time() - start_time) * 1000)

        # Extract diagnostics from generator metadata if available
        total_generated = len(generated_items)
        quality_filtered = total_generated - len(validated_items)

        diagnostics = GenerationDiagnostics(
            input_length=len(input_text),
            extracted_keypoints=sum(
                1
                for item in generated_items
                if item.get("metadata", {}).get("generation_method")
                == "keypoint_extraction"
            ),
            extracted_numeric_facts=sum(
                1
                for item in generated_items
                if item.get("metadata", {}).get("generation_method")
                == "numeric_fact_extraction"
            ),
            extracted_sentences=sum(
                1
                for item in generated_items
                if item.get("metadata", {}).get("generation_method")
                == "pos_based_masking"
            ),
            extracted_procedures=sum(
                1
                for item in generated_items
                if item.get("metadata", {}).get("generation_method")
                == "procedure_extraction"
            ),
            total_generated=total_generated,
            quality_filtered=quality_filtered,
            final_count=len(validated_items),
            processing_time_ms=processing_time,
        )

        logger.info(
            "Content generation completed",
            final_count=len(validated_items),
            rejected_count=len(rejected_items),
            warnings_count=len(warnings),
            processing_time_ms=processing_time,
            staged_ids=staged_ids,
            user_id=principal.user_id,
            org_id=principal.org_id,
        )

        return GenerateResponse(
            generated=validated_items,
            rejected=rejected_items,
            diagnostics=diagnostics,
            warnings=warnings,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Content generation failed",
            error=str(e),
            error_type=type(e).__name__,
            user_id=principal.user_id,
            org_id=principal.org_id,
        )
        raise HTTPException(
            status_code=500, detail=f"Content generation failed: {str(e)}"
        ) from e


@router.get("/generators", response_model=list[str])
async def list_generators() -> list[str]:
    """
    List available content generators.

    Returns:
        List of registered generator names
    """
    return generator_registry.list()


@router.get("/generators/{generator_name}/info")
async def get_generator_info(generator_name: str) -> dict[str, Any]:
    """
    Get information about a specific generator.

    Args:
        generator_name: Name of the generator

    Returns:
        Generator information and capabilities

    Raises:
        HTTPException: If generator not found
    """
    try:
        generator_registry.get(generator_name)

        # Basic info - can be extended based on generator capabilities
        info = {
            "name": generator_name,
            "type": "rule_based" if generator_name == "basic_rules" else "unknown",
            "description": (
                "Deterministic rule-based content generator using NLP"
                if generator_name == "basic_rules"
                else "Unknown generator"
            ),
            "supported_item_types": ["flashcard", "mcq", "cloze", "short_answer"],
            "supports_offline_generation": True,
            "requires_external_apis": False,
        }

        return info

    except KeyError as e:
        raise HTTPException(
            status_code=404, detail=f"Generator '{generator_name}' not found"
        ) from e
