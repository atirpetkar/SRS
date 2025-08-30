import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from api.config.logging import get_logger

logger = get_logger(__name__)


class LearningOSException(Exception):
    """Base exception for Learning OS application."""

    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: dict[str, Any] | None = None,
    ):
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class ValidationError(LearningOSException):
    """Raised when input validation fails."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message, status.HTTP_422_UNPROCESSABLE_ENTITY, details)


class NotFoundError(LearningOSException):
    """Raised when a resource is not found."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message, status.HTTP_404_NOT_FOUND, details)


class UnauthorizedError(LearningOSException):
    """Raised when authentication fails."""

    def __init__(
        self, message: str = "Unauthorized", details: dict[str, Any] | None = None
    ):
        super().__init__(message, status.HTTP_401_UNAUTHORIZED, details)


class ForbiddenError(LearningOSException):
    """Raised when access is forbidden."""

    def __init__(
        self, message: str = "Forbidden", details: dict[str, Any] | None = None
    ):
        super().__init__(message, status.HTTP_403_FORBIDDEN, details)


def create_error_response(
    status_code: int,
    message: str,
    details: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Create standardized error response envelope."""
    return {
        "ok": False,
        "error": {
            "message": message,
            "code": status_code,
            "details": details or {},
        },
        "request_id": request_id,
        "timestamp": datetime.now(UTC).isoformat(),
    }


def create_success_response(
    data: Any, message: str | None = None, request_id: str | None = None
) -> dict[str, Any]:
    """Create standardized success response envelope."""
    return {
        "ok": True,
        "data": data,
        "message": message,
        "request_id": request_id,
        "timestamp": datetime.now(UTC).isoformat(),
    }


async def learning_os_exception_handler(
    request: Request, exc: LearningOSException
) -> JSONResponse:
    """Handle Learning OS specific exceptions."""
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))

    logger.error(
        "Application exception",
        exception=exc.__class__.__name__,
        message=exc.message,
        status_code=exc.status_code,
        details=exc.details,
        request_id=request_id,
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=create_error_response(
            status_code=exc.status_code,
            message=exc.message,
            details=exc.details,
            request_id=request_id,
        ),
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle FastAPI HTTP exceptions."""
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))

    logger.warning(
        "HTTP exception",
        status_code=exc.status_code,
        detail=exc.detail,
        request_id=request_id,
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=create_error_response(
            status_code=exc.status_code,
            message=str(exc.detail),
            request_id=request_id,
        ),
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions."""
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))

    logger.error(
        "Unhandled exception",
        exception=exc.__class__.__name__,
        message=str(exc),
        request_id=request_id,
        exc_info=True,
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=create_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Internal server error",
            request_id=request_id,
        ),
    )


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Middleware to add request context and correlation IDs."""

    async def dispatch(self, request: Request, call_next):
        # Generate correlation ID for request tracking
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        # Add to log context
        from api.config.logging import add_request_context

        add_request_context(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )

        response = await call_next(request)

        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id

        return response
