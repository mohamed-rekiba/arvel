"""Request context middleware."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from fastapi import FastAPI
    from httpx import AsyncClient


@pytest.fixture
def app() -> FastAPI:
    from arvel.observability.middleware import ObservabilityMiddleware
    from fastapi import FastAPI

    app = FastAPI()
    app.add_middleware(ObservabilityMiddleware)

    async def ping() -> dict[str, str]:
        from arvel.facades import Log

        Log.info("ping.called")
        return {"ok": "true"}

    async def error_route() -> dict[str, str]:
        raise RuntimeError("boom")

    app.add_api_route("/ping", ping, methods=["GET"])
    app.add_api_route("/error", error_route, methods=["GET"])

    return app


@pytest.fixture
def client(app: FastAPI) -> AsyncClient:
    from httpx import ASGITransport, AsyncClient

    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


class TestObservabilityMiddlewareImport:
    def test_middleware_importable(self) -> None:
        from arvel.observability.middleware import ObservabilityMiddleware

        _ = ObservabilityMiddleware


class TestRequestId:
    @pytest.mark.asyncio
    async def test_response_has_x_request_id_header(self, client: AsyncClient) -> None:

        async with client as c:
            resp = await c.get("/ping")
        assert "x-request-id" in resp.headers

    @pytest.mark.asyncio
    async def test_custom_request_id_propagated(self, client: AsyncClient) -> None:

        async with client as c:
            resp = await c.get("/ping", headers={"X-Request-ID": "my-custom-id-123"})
        assert resp.headers["x-request-id"] == "my-custom-id-123"

    @pytest.mark.asyncio
    async def test_unsafe_request_id_rejected(self, client: AsyncClient) -> None:
        from arvel.testing.observability import FakeObservability

        with FakeObservability():
            async with client as c:
                resp = await c.get("/ping", headers={"X-Request-ID": "'; DROP TABLE users; --"})
        # Unsafe value must not be used; a generated safe ID must be set instead
        assert resp.headers.get("x-request-id") != "'; DROP TABLE users; --"


class TestRequestContextOnLogs:
    @pytest.mark.asyncio
    async def test_log_records_carry_request_id(self, client: AsyncClient) -> None:
        from arvel.testing.observability import FakeObservability

        with FakeObservability() as obs:
            async with client as c:
                await c.get("/ping")

        ping_log = next(r for r in obs.log_records if r.body == "ping.called")
        assert ping_log.attributes.get("request_id") is not None

    @pytest.mark.asyncio
    async def test_log_records_carry_trace_and_span_ids(self, client: AsyncClient) -> None:
        from arvel.testing.observability import FakeObservability

        with FakeObservability() as obs:
            async with client as c:
                await c.get("/ping")

        ping_log = next(r for r in obs.log_records if r.body == "ping.called")
        assert ping_log.attributes.get("trace_id") is not None
        assert ping_log.attributes.get("span_id") is not None

    @pytest.mark.asyncio
    async def test_span_opened_per_request(self, client: AsyncClient) -> None:
        from arvel.testing.observability import FakeObservability

        with FakeObservability() as obs:
            async with client as c:
                await c.get("/ping")

        obs.assert_span("arvel.http.request")


class TestTracePropagation:
    @pytest.mark.asyncio
    async def test_w3c_traceparent_propagated_in(self, client: AsyncClient) -> None:
        from arvel.testing.observability import FakeObservability

        traceparent = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
        with FakeObservability() as obs:
            async with client as c:
                await c.get("/ping", headers={"traceparent": traceparent})

        # The opened span should have the parent trace ID from the header
        span = next(s for s in obs.spans if s.name == "arvel.http.request")
        parent_trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
        assert format(span.context.trace_id, "032x") == parent_trace_id


class TestContextIsolation:
    @pytest.mark.asyncio
    async def test_concurrent_requests_have_isolated_context(self, app: FastAPI) -> None:
        from arvel.testing.observability import FakeObservability
        from httpx import ASGITransport, AsyncClient

        # Send two concurrent requests — each should get a different request_id
        with FakeObservability():
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                results = await asyncio.gather(c.get("/ping"), c.get("/ping"))

        request_ids = [r.headers["x-request-id"] for r in results]
        assert request_ids[0] != request_ids[1], "Concurrent requests must have unique request_ids"
