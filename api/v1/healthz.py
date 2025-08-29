from fastapi import APIRouter
from pydantic import BaseModel

from api.config.settings import settings
from api.v1.core.exceptions import create_success_response

router = APIRouter()


class HealthResponse(BaseModel):
    ok: bool
    version: str
    environment: str


@router.get("/healthz", response_model=dict)
async def health_check():
    """Health check endpoint to verify service is running."""
    return create_success_response(
        data={
            "ok": True,
            "version": settings.version,
            "environment": settings.environment,
        }
    )
