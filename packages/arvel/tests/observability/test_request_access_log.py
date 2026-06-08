"""Framework access log emitted by ObservabilityMiddleware when uvicorn access is off."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from arvel.testing.observability import CapturedLogRecord
    from fastapi import FastAPI


def _app(*, log_requests: bool) -> FastAPI:
    from arvel.http.problem_details import ProblemDetailsHandler
    from arvel.observability.middleware import ObservabilityMiddleware
    from fastapi import FastAPI

    app = FastAPI()
    app.add_middleware(ObservabilityMiddleware, log_requests=log_requests)

    async def ok() -> dict[str, str]:
        return {"ok": "true"}

    async def boom() -> dict[str, str]:
        raise RuntimeError("kaboom")

    app.add_api_route("/ok", ok, methods=["GET"])
    app.add_api_route("/boom", boom, methods=["GET"])
    ProblemDetailsHandler().register(app)
    return app


async def _records(app: FastAPI, path: str, body: str = "http.request") -> list[CapturedLogRecord]:
    from arvel.testing.observability import FakeObservability
    from httpx2 import ASGITransport, AsyncClient

    with FakeObservability() as obs:
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as c:
            await c.get(path)
        return [r for r in obs.log_records if r.body == body]


class TestRequestAccessLog:
    @pytest.mark.asyncio
    async def test_logs_request_with_duration_and_status(self) -> None:
        records = await _records(_app(log_requests=True), "/ok")

        assert records, "expected an http.request access log"
        attrs = records[0].attributes
        assert attrs["method"] == "GET"
        assert attrs["path"] == "/ok"
        assert attrs["status"] == 200
        assert isinstance(attrs["duration_ms"], float)
        assert attrs["duration_ms"] >= 0
        assert attrs.get("request_id") is not None

    @pytest.mark.asyncio
    async def test_emits_received_boundary(self) -> None:
        records = await _records(_app(log_requests=True), "/ok", body="request.received")

        assert records, "expected a request.received boundary log"
        attrs = records[0].attributes
        assert attrs["method"] == "GET"
        assert attrs["path"] == "/ok"

    @pytest.mark.asyncio
    async def test_silent_when_disabled(self) -> None:
        assert await _records(_app(log_requests=False), "/ok") == []
        assert await _records(_app(log_requests=False), "/ok", body="request.received") == []

    @pytest.mark.asyncio
    async def test_logs_500_status_on_unhandled_error(self) -> None:
        records = await _records(_app(log_requests=True), "/boom")

        assert records
        assert records[0].attributes["status"] == 500
