"""TelemetryMiddleware — per-request OpenTelemetry: a SERVER span (tracing) and request metrics
(count + duration), each gated independently and a zero-cost passthrough when both are off.

The span opens in ``handle`` (made current, so handler/DB/job spans nest under it) and closes in
``terminate`` — arvel's after-response hook, the only place the normalized response (real status) is
available. Metrics are recorded there too (and on the exception path). W3C context propagation from the
request headers continues an upstream trace. No opentelemetry import happens when telemetry is off.

Per-request state (the span, the context token, the start time) lives in **ContextVars**, not on the
instance — so this middleware is safe to share across concurrent requests: one request's span can
never be closed against another's, even if the HTTP kernel resolves a single shared instance.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

# Duck-types as arvel middleware (handle/terminate) rather than subclassing
# arvel.http.middleware.Middleware — telemetry sits below http in the layered DAG (DR-0026).


@dataclass
class _RequestState:
    """One request's telemetry state — held in a ContextVar so concurrent requests never share it."""

    span: Any = None
    token: Any = None
    trace_on: bool = False
    metrics_on: bool = False
    start: float = 0.0
    method: str = ""


_state: ContextVar[_RequestState | None] = ContextVar("arvel_telemetry_state", default=None)


class TelemetryMiddleware:
    async def handle(self, request: Any, call_next: Any) -> Any:
        import time

        from arvel.telemetry import is_metrics_enabled, is_tracing_enabled

        st = _RequestState(trace_on=is_tracing_enabled(), metrics_on=is_metrics_enabled())
        if not (st.trace_on or st.metrics_on):
            return await call_next(request)
        _state.set(st)

        st.start = time.perf_counter()
        st.method = request.method()
        if st.trace_on:
            from opentelemetry import context as otel_context
            from opentelemetry import trace
            from opentelemetry.propagate import extract
            from opentelemetry.trace import SpanKind

            path = request.path()
            parent = extract(self._carrier(request))  # continue an upstream trace if present
            span = trace.get_tracer("arvel.http").start_span(
                f"{st.method} {path}", context=parent, kind=SpanKind.SERVER
            )
            span.set_attribute("http.request.method", st.method)
            span.set_attribute("url.path", path)
            st.span = span
            st.token = otel_context.attach(trace.set_span_in_context(span))  # make it current
        try:
            return await call_next(request)
        except Exception as exc:
            if st.span is not None:
                from opentelemetry.trace import Status, StatusCode

                st.span.set_status(Status(StatusCode.ERROR))
                st.span.record_exception(exc)
            self._record_metrics(st, 500)
            self._close(st)
            raise

    async def terminate(self, request: Any, response: Any) -> None:
        st = _state.get()
        if st is None or not (st.trace_on or st.metrics_on):
            return
        status = getattr(response, "status_code", None)
        code = status if isinstance(status, int) else 200
        if st.span is not None:
            from opentelemetry.trace import Status, StatusCode

            st.span.set_attribute("http.response.status_code", code)
            if code >= 500:
                st.span.set_status(Status(StatusCode.ERROR))
        self._record_metrics(st, code)
        self._close(st)

    @staticmethod
    def _record_metrics(st: _RequestState, status: int) -> None:
        if not st.metrics_on:
            return
        import time

        from arvel.telemetry import meter

        duration = time.perf_counter() - st.start
        attributes = {"http.request.method": st.method, "http.response.status_code": status}
        instruments = meter("arvel.http")
        instruments.create_counter(
            "http.server.request.count", unit="{request}", description="HTTP requests handled"
        ).add(1, attributes)
        instruments.create_histogram(
            "http.server.request.duration", unit="s", description="HTTP server request duration"
        ).record(duration, attributes)

    @staticmethod
    def _close(st: _RequestState) -> None:
        from opentelemetry import context as otel_context

        if st.token is not None:
            otel_context.detach(st.token)
            st.token = None
        if st.span is not None:
            st.span.end()
            st.span = None

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
