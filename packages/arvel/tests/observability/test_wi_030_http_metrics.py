"""HTTP auto-instrumentation and metrics."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from fastapi import FastAPI


def _make_instrumented_app() -> FastAPI:
    """Create a fresh instrumented FastAPI app.

    Caller must enter FakeObservability BEFORE calling this so the instrumentor
    binds to the in-memory meter provider.
    """
    from fastapi import FastAPI
    from opentelemetry.instrumentation.fastapi import (  # pyright: ignore[reportMissingTypeStubs]
        FastAPIInstrumentor,
    )

    app = FastAPI()
    # Exclude internal routes — mirrors what ObservabilityServiceProvider configures
    FastAPIInstrumentor.instrument_app(app, excluded_urls="/_metrics,/_healthz,/_readyz")

    async def get_user(user_id: int) -> dict[str, int]:
        return {"id": user_id}

    async def metrics() -> dict[str, str]:
        return {"ok": "true"}

    async def healthz() -> dict[str, str]:
        return {"ok": "true"}

    app.add_api_route("/users/{user_id}", get_user, methods=["GET"])
    app.add_api_route("/_metrics", metrics, methods=["GET"])
    app.add_api_route("/_healthz", healthz, methods=["GET"])

    return app


class TestHttpMetrics:
    @pytest.mark.asyncio
    async def test_http_duration_metric_emitted(self) -> None:
        from arvel.testing.observability import FakeObservability
        from httpx import ASGITransport, AsyncClient

        with FakeObservability() as obs:
            app = _make_instrumented_app()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                await c.get("/users/1")

        duration_metrics = [m for m in obs.metrics if m.name == "http.server.duration"]
        assert duration_metrics, "http.server.duration metric not emitted"

    @pytest.mark.asyncio
    async def test_http_metrics_have_route_attribute(self) -> None:
        from arvel.testing.observability import FakeObservability
        from httpx import ASGITransport, AsyncClient

        with FakeObservability() as obs:
            app = _make_instrumented_app()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                await c.get("/users/1")

        duration_metrics = [m for m in obs.metrics if m.name == "http.server.duration"]
        assert any(
            dp.attributes.get("http.target") == "/users/{user_id}"
            for m in duration_metrics
            for dp in m.data.data_points
        )


class TestInternalRouteExclusion:
    @pytest.mark.asyncio
    async def test_metrics_endpoint_not_instrumented(self) -> None:
        from arvel.testing.observability import FakeObservability
        from httpx import ASGITransport, AsyncClient

        with FakeObservability() as obs:
            app = _make_instrumented_app()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                await c.get("/_metrics")

        # No span should be recorded for the /_metrics route
        metrics_spans = [
            s for s in obs.spans if "/_metrics" in (s.attributes.get("http.target", "") or s.name)
        ]
        assert not metrics_spans, "_metrics route must not generate OTel spans"

    @pytest.mark.asyncio
    async def test_healthz_endpoint_not_instrumented(self) -> None:
        from arvel.testing.observability import FakeObservability
        from httpx import ASGITransport, AsyncClient

        with FakeObservability() as obs:
            app = _make_instrumented_app()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                await c.get("/_healthz")

        healthz_spans = [
            s for s in obs.spans if "/_healthz" in (s.attributes.get("http.target", "") or s.name)
        ]
        assert not healthz_spans, "_healthz route must not generate OTel spans"
