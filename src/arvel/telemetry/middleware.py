"""TelemetryMiddleware — per-request OpenTelemetry: a SERVER span (tracing) and request metrics
(count + duration), each gated independently and a zero-cost passthrough when both are off.

The span opens in ``handle`` (made current, so handler/DB/job spans nest under it) and closes in
``terminate`` — arvel's after-response hook, the only place the normalized response (real status) is
available. Metrics are recorded there too (and on the exception path). W3C context propagation from the
request headers continues an upstream trace. No opentelemetry import happens when telemetry is off.
"""

from __future__ import annotations

from typing import Any

from arvel.http.middleware import Middleware


class TelemetryMiddleware(Middleware):
    _span: Any = None
    _token: Any = None
    _trace_on: bool = False
    _metrics_on: bool = False
    _start: float = 0.0
    _method: str = ""

    async def handle(self, request: Any, call_next: Any) -> Any:
        import time

        from arvel.telemetry import is_metrics_enabled, is_tracing_enabled

        self._trace_on = is_tracing_enabled()
        self._metrics_on = is_metrics_enabled()
        if not (self._trace_on or self._metrics_on):
            return await call_next(request)

        self._start = time.perf_counter()
        self._method = request.method()
        if self._trace_on:
            from opentelemetry import context as otel_context
            from opentelemetry import trace
            from opentelemetry.propagate import extract
            from opentelemetry.trace import SpanKind

            path = request.path()
            parent = extract(self._carrier(request))  # continue an upstream trace if present
            span = trace.get_tracer("arvel.http").start_span(
                f"{self._method} {path}", context=parent, kind=SpanKind.SERVER
            )
            span.set_attribute("http.request.method", self._method)
            span.set_attribute("url.path", path)
            self._span = span
            self._token = otel_context.attach(trace.set_span_in_context(span))  # make it current
        try:
            return await call_next(request)
        except Exception as exc:
            if self._span is not None:
                from opentelemetry.trace import Status, StatusCode

                self._span.set_status(Status(StatusCode.ERROR))
                self._span.record_exception(exc)
            self._record_metrics(500)
            self._close()
            raise

    async def terminate(self, request: Any, response: Any) -> None:
        if not (self._trace_on or self._metrics_on):
            return
        status = getattr(response, "status_code", None)
        code = status if isinstance(status, int) else 200
        if self._span is not None:
            from opentelemetry.trace import Status, StatusCode

            self._span.set_attribute("http.response.status_code", code)
            if code >= 500:
                self._span.set_status(Status(StatusCode.ERROR))
        self._record_metrics(code)
        self._close()

    def _record_metrics(self, status: int) -> None:
        if not self._metrics_on:
            return
        import time

        from arvel.telemetry import meter

        duration = time.perf_counter() - self._start
        attributes = {"http.request.method": self._method, "http.response.status_code": status}
        instruments = meter("arvel.http")
        instruments.create_counter(
            "http.server.request.count", unit="{request}", description="HTTP requests handled"
        ).add(1, attributes)
        instruments.create_histogram(
            "http.server.request.duration", unit="s", description="HTTP server request duration"
        ).record(duration, attributes)

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
