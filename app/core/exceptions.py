"""Domain exception hierarchy.

Every custom exception carries a stable ``code`` used in the API error envelope
and in structured logs. FastAPI exception handlers (app.main) translate these
into HTTP responses.
"""

from __future__ import annotations

from typing import Any


class JobAgentError(Exception):
    """Base class for all application errors."""

    code: str = "internal_error"
    http_status: int = 500

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ConfigurationError(JobAgentError):
    code = "configuration_error"
    http_status = 500


class DatabaseError(JobAgentError):
    code = "database_error"
    http_status = 503


class CollectorError(JobAgentError):
    """Raised inside a collector. Isolated by the pipeline (bulkhead)."""

    code = "collector_error"
    http_status = 502


class RateLimitError(CollectorError):
    code = "rate_limited"
    http_status = 429


class CircuitOpenError(CollectorError):
    """Raised when a source's circuit breaker is open (failing fast)."""

    code = "circuit_open"
    http_status = 503


class ValidationError(JobAgentError):
    code = "validation_error"
    http_status = 422


class NotFoundError(JobAgentError):
    code = "not_found"
    http_status = 404


class EmbeddingError(JobAgentError):
    code = "embedding_error"
    http_status = 500


class NotificationError(JobAgentError):
    code = "notification_error"
    http_status = 502
