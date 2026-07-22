"""ASGI middleware.

``CorrelationIdMiddleware`` establishes a correlation id for every request:
it honours an inbound ``X-Correlation-ID`` header (so callers/tracing systems
can stitch requests together) or mints a fresh one, binds it to the context so
all logs during the request carry it, and echoes it back on the response.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware

from app.core.context import bind_correlation_id, new_id, reset_correlation_id
from app.metrics.names import API_REQUESTS

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from starlette.requests import Request
    from starlette.responses import Response

CORRELATION_HEADER = "X-Correlation-ID"


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Bind a correlation id to the request context, count the request, echo the id."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        correlation_id = request.headers.get(CORRELATION_HEADER) or new_id("req_")
        token = bind_correlation_id(correlation_id)
        try:
            container = getattr(request.app.state, "container", None)
            if container is not None:
                container.metrics.increment(API_REQUESTS)
            response = await call_next(request)
        finally:
            reset_correlation_id(token)
        response.headers[CORRELATION_HEADER] = correlation_id
        return response
