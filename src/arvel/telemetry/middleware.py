"""TelemetryMiddleware — wraps every request in an OpenTelemetry SERVER span.

Registered as a framework-default global middleware (outermost, so the span covers the whole request).
It's a zero-cost passthrough when tracing is off — ``is_tracing_enabled()`` is checked first and no
opentelemetry import happens. When on, it continues any upstream trace (W3C context propagation from the
request headers) so a request is one distributed trace across services.

The span opens in ``handle`` (made current, so handler/DB/job spans nest under it) and closes in
``terminate`` — arvel's after-response hook — which is the only place the *normalized* response (and its
real status code) is available. A handler that raises ends the span with an error in ``handle`` itself
(``terminate`` isn't run on the exception path).
"""

from __future__ import annotations

from typing import Any

from arvel.http.middleware import Middleware


class TelemetryMiddleware(Middleware):
    _span: Any = None
    _token: Any = None

    async def handle(self, request: Any, call_next: Any) -> Any:
        from arvel.telemetry import is_tracing_enabled

        if not is_tracing_enabled():
            return await call_next(request)

        from opentelemetry import context as otel_context
        from opentelemetry import trace
        from opentelemetry.propagate import extract
        from opentelemetry.trace import SpanKind, Status, StatusCode

        method, path = request.method(), request.path()
        parent = extract(self._carrier(request))  # continue an upstream trace if present
        span = trace.get_tracer("arvel.http").start_span(
            f"{method} {path}", context=parent, kind=SpanKind.SERVER
        )
        span.set_attribute("http.request.method", method)
        span.set_attribute("url.path", path)
        self._span = span
        self._token = otel_context.attach(trace.set_span_in_context(span))  # make it current
        try:
            return await call_next(request)
        except Exception as exc:
            span.set_status(Status(StatusCode.ERROR))
            span.record_exception(exc)
            self._close()
            raise

    async def terminate(self, request: Any, response: Any) -> None:
        if self._span is None:
            return
        from opentelemetry.trace import Status, StatusCode

        status = getattr(response, "status_code", None)
        if isinstance(status, int):
            self._span.set_attribute("http.response.status_code", status)
            if status >= 500:
                self._span.set_status(Status(StatusCode.ERROR))
        self._close()

    def _close(self) -> None:
        from opentelemetry import context as otel_context

        if self._token is not None:
            otel_context.detach(self._token)
            self._token = None
        if self._span is not None:
            self._span.end()
            self._span = None

    @staticmethod
    def _carrier(request: Any) -> dict[str, str]:
        """Incoming request headers as a propagation carrier (lower-cased keys)."""
        headers = getattr(getattr(request, "raw", None), "headers", None)
        if headers is None:
            return {}
        try:
            return {str(k).lower(): str(v) for k, v in dict(headers).items()}
        except Exception:
            return {}
