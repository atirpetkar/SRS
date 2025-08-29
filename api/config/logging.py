import logging
import sys
from typing import Any

import structlog

from .settings import settings


def setup_logging() -> None:
    """Configure structured logging with structlog."""

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.log_level),
    )

    # Configure structlog
    structlog.configure(
        processors=[
            # Add correlation IDs and timestamps
            structlog.contextvars.merge_contextvars,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            # Add caller information in development
            (
                structlog.processors.CallsiteParameterAdder(
                    parameters=[structlog.processors.CallsiteParameter.FUNC_NAME]
                )
                if settings.debug
                else structlog.processors.CallsiteParameterAdder(parameters=[])
            ),
            # JSON formatting for production, pretty printing for development
            (
                structlog.dev.ConsoleRenderer()
                if settings.debug
                else structlog.processors.JSONRenderer()
            ),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level)
        ),
        logger_factory=structlog.WriteLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = __name__) -> structlog.BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)


def add_request_context(request_id: str, **context: Any) -> None:
    """Add request-specific context to all log messages."""
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id, **context)
