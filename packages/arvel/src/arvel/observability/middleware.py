"""ObservabilityMiddleware — request ID, trace context, and exception logging.

Pure ASGI implementation — avoids Starlette's BaseHTTPMiddleware, which
buffers streaming responses and causes Content-Length mismatches.
"""

from __future__ import annotations

from urllib.parse import parse_qsl

from opentelemetry import trace as otel_trace
from opentelemetry.propagate import extract as otel_extract
from opentelemetry.trace import StatusCode
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from arvel.database.paginator import (
    PaginationRequest,
    reset_pagination_request,
    set_pagination_request,
)
from arvel.observability.context import (
    RequestContext,
    generate_request_id,
    reset_request_context,
    set_request_context,
    validate_request_id,
)

_SERVER_ERROR_THRESHOLD = 500


class ObservabilityMiddleware:
    """Outermost middleware — sets request context, opens span, logs 5xx errors.

    Must be registered before any other middleware so it wraps the full lifecycle.
    """

    def __init__(self, app: ASGIApp, service: str = "arvel") -> None:
        self._app = app
        self._service = service

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        headers_list: list[tuple[bytes, bytes]] = scope.get("headers", [])
        raw_id = ""
        for name, value in headers_list:
            if name.lower() == b"x-request-id":
                raw_id = value.decode("latin-1")
                break

        request_id = validate_request_id(raw_id) or generate_request_id()

        ctx = RequestContext(
            request_id=request_id,
            route=scope.get("path", ""),
            service=self._service,
        )
        token = set_request_context(ctx)

        raw_query = scope.get("query_string", b"")
        pg_token = set_pagination_request(
            PaginationRequest(
                path=scope.get("path", "/"),
                query=dict(parse_qsl(raw_query.decode("latin-1"), keep_blank_values=True)),
            )
        )

        carrier: dict[str, str] = {
            name.decode("latin-1"): value.decode("latin-1") for name, value in headers_list
        }
        parent_ctx = otel_extract(carrier)

        tracer = otel_trace.get_tracer("arvel")
        try:
            with tracer.start_as_current_span("arvel.http.request", context=parent_ctx) as span:
                span.set_attribute("http.method", scope.get("method", "GET"))
                span.set_attribute("http.route", scope.get("path", ""))
                span.set_attribute("request_id", request_id)

                response_status: list[int] = []

                async def send_with_request_id(message: Message) -> None:
                    if message["type"] == "http.response.start":
                        headers = MutableHeaders(scope=message)
                        headers["X-Request-ID"] = request_id
                        response_status.append(message["status"])
                    await send(message)

                try:
                    await self._app(scope, receive, send_with_request_id)
                except Exception as exc:
                    span.set_status(StatusCode.ERROR, str(exc))
                    self._log_5xx(exc, request_id)
                    raise

                if response_status and response_status[0] >= _SERVER_ERROR_THRESHOLD:
                    span.set_status(StatusCode.ERROR, f"HTTP {response_status[0]}")
        finally:
            reset_request_context(token)
            reset_pagination_request(pg_token)

    def _log_5xx(self, exc: BaseException, request_id: str) -> None:
        from arvel.http.exceptions import HttpException
        from arvel.logging.facade import Log

        if isinstance(exc, HttpException) and exc.status_code < _SERVER_ERROR_THRESHOLD:
            return

        Log.error("http.exception", exc=exc, request_id=request_id)


__all__ = ["ObservabilityMiddleware"]
