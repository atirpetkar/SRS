from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from api.config.logging import setup_logging
from api.config.settings import settings
from api.v1.core.exceptions import (
    LearningOSException,
    RequestContextMiddleware,
    general_exception_handler,
    http_exception_handler,
    learning_os_exception_handler,
)
from api.v1.core.registries import (
    generator_registry,
    grader_registry,
    importer_registry,
    item_type_registry,
    scheduler_registry,
    vectorizer_registry,
)
from api.v1.healthz import router as health_router


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    # Initialize structured logging
    setup_logging()

    # Create FastAPI app with API versioning from day 1
    app = FastAPI(
        title=settings.app_name,
        description="Content-agnostic practice loop with SRS scheduling",
        version=settings.version,
        debug=settings.debug,
        # All endpoints will be under /v1/ prefix
        openapi_url="/v1/openapi.json" if settings.debug else None,
        docs_url="/v1/docs" if settings.debug else None,
        redoc_url="/v1/redoc" if settings.debug else None,
    )

    # Add middleware
    app.add_middleware(RequestContextMiddleware)

    # Add CORS middleware for development
    if settings.debug:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Add exception handlers
    app.add_exception_handler(LearningOSException, learning_os_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)

    # Include routers with /v1 prefix
    app.include_router(health_router, prefix="/v1", tags=["health"])

    # Freeze registries in non-development environments to prevent runtime modifications
    if settings.environment != "development":
        item_type_registry.freeze()
        grader_registry.freeze()
        scheduler_registry.freeze()
        importer_registry.freeze()
        generator_registry.freeze()
        vectorizer_registry.freeze()

    return app


# Create the app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        workers=1 if settings.debug else settings.workers,
    )
