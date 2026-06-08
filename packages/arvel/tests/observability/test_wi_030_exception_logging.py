"""Automatic exception logging."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from fastapi import FastAPI


@pytest.fixture
def exception_app() -> FastAPI:
    from arvel.http.exceptions import HttpException
    from arvel.observability.middleware import ObservabilityMiddleware
    from fastapi import FastAPI

    app = FastAPI()
    app.add_middleware(ObservabilityMiddleware)

    async def server_error() -> dict[str, str]:
        raise RuntimeError("unexpected boom")

    async def not_found_route() -> dict[str, str]:
        raise HttpException(status_code=404, message="not found")

    async def ok() -> dict[str, str]:
        return {"ok": "true"}

    app.add_api_route("/500", server_error, methods=["GET"])
    app.add_api_route("/404", not_found_route, methods=["GET"])
    app.add_api_route("/ok", ok, methods=["GET"])

    from arvel.http.problem_details import ProblemDetailsHandler

    ProblemDetailsHandler().register(app)

    return app


class TestExceptionLogging:
    @pytest.mark.asyncio
    async def test_5xx_exception_logged_at_error_level(self, exception_app: FastAPI) -> None:
        from arvel.testing.observability import FakeObservability
        from httpx2 import ASGITransport, AsyncClient

        with FakeObservability() as obs:
            async with AsyncClient(
                transport=ASGITransport(app=exception_app, raise_app_exceptions=False),
                base_url="http://test",
            ) as c:
                await c.get("/500")

        error_logs = [r for r in obs.log_records if r.body == "http.exception"]
        assert error_logs, "No http.exception log record for 5xx response"
        record = error_logs[0]
        assert record.attributes.get("exception.type") is not None

    @pytest.mark.asyncio
    async def test_5xx_span_marked_error(self, exception_app: FastAPI) -> None:
        from arvel.testing.observability import FakeObservability
        from httpx2 import ASGITransport, AsyncClient
        from opentelemetry.trace import StatusCode

        with FakeObservability() as obs:
            async with AsyncClient(
                transport=ASGITransport(app=exception_app, raise_app_exceptions=False),
                base_url="http://test",
            ) as c:
                await c.get("/500")

        http_spans = [s for s in obs.spans if s.name == "arvel.http.request"]
        assert http_spans
        span = http_spans[0]
        assert span.status.status_code == StatusCode.ERROR

    @pytest.mark.asyncio
    async def test_4xx_exception_not_logged_at_error_level(self, exception_app: FastAPI) -> None:
        from arvel.testing.observability import FakeObservability
        from httpx2 import ASGITransport, AsyncClient

        with FakeObservability() as obs:
            async with AsyncClient(
                transport=ASGITransport(app=exception_app, raise_app_exceptions=False),
                base_url="http://test",
            ) as c:
                await c.get("/404")

        error_logs = [
            r
            for r in obs.log_records
            if r.body == "http.exception" and r.severity_number.value >= 17  # ERROR = 17
        ]
        assert not error_logs, "4xx HttpException must not be logged at ERROR level"

    @pytest.mark.asyncio
    async def test_5xx_log_contains_request_id(self, exception_app: FastAPI) -> None:
        from arvel.testing.observability import FakeObservability
        from httpx2 import ASGITransport, AsyncClient

        with FakeObservability() as obs:
            async with AsyncClient(
                transport=ASGITransport(app=exception_app, raise_app_exceptions=False),
                base_url="http://test",
            ) as c:
                await c.get("/500")

        error_logs = [r for r in obs.log_records if r.body == "http.exception"]
        assert error_logs
        assert error_logs[0].attributes.get("request_id") is not None

    @pytest.mark.asyncio
    async def test_5xx_exception_log_has_traceback(self, exception_app: FastAPI) -> None:
        from arvel.testing.observability import FakeObservability
        from httpx2 import ASGITransport, AsyncClient

        with FakeObservability() as obs:
            async with AsyncClient(
                transport=ASGITransport(app=exception_app, raise_app_exceptions=False),
                base_url="http://test",
            ) as c:
                await c.get("/500")

        error_logs = [r for r in obs.log_records if r.body == "http.exception"]
        assert error_logs
        assert error_logs[0].attributes.get("exception.stacktrace") is not None
