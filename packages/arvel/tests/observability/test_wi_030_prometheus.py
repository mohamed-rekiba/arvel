"""Prometheus metrics endpoint."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from fastapi import FastAPI


@pytest.fixture
def metrics_app() -> FastAPI:
    from arvel.observability.metrics_route import add_metrics_route
    from fastapi import FastAPI

    app = FastAPI()
    add_metrics_route(app, allowed_cidrs=["0.0.0.0/0"])  # open for tests
    return app


@pytest.fixture
def restricted_app() -> FastAPI:
    from arvel.observability.metrics_route import add_metrics_route
    from fastapi import FastAPI

    app = FastAPI()
    add_metrics_route(app, allowed_cidrs=["192.0.2.0/24"])  # test net only
    return app


class TestPrometheusEndpointImport:
    def test_metrics_route_importable(self) -> None:
        from arvel.observability.metrics_route import add_metrics_route

        _ = add_metrics_route


class TestPrometheusEndpointResponse:
    @pytest.mark.asyncio
    async def test_metrics_endpoint_returns_200(self, metrics_app: FastAPI) -> None:
        from httpx2 import ASGITransport, AsyncClient

        async with AsyncClient(
            transport=ASGITransport(app=metrics_app), base_url="http://test"
        ) as c:
            resp = await c.get("/_metrics")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_metrics_content_type_is_prometheus(self, metrics_app: FastAPI) -> None:
        from httpx2 import ASGITransport, AsyncClient

        async with AsyncClient(
            transport=ASGITransport(app=metrics_app), base_url="http://test"
        ) as c:
            resp = await c.get("/_metrics")
        content_type = resp.headers.get("content-type", "")
        assert "text/plain" in content_type

    @pytest.mark.asyncio
    async def test_metrics_body_is_valid_prometheus_format(self, metrics_app: FastAPI) -> None:
        from httpx2 import ASGITransport, AsyncClient

        async with AsyncClient(
            transport=ASGITransport(app=metrics_app), base_url="http://test"
        ) as c:
            resp = await c.get("/_metrics")
        # Prometheus text format starts with # HELP or # TYPE lines
        body = resp.text
        assert "#" in body or body.strip() == "", f"Invalid Prometheus format: {body[:200]}"


class TestMetricsCidrGuard:
    @pytest.mark.asyncio
    async def test_metrics_forbidden_for_disallowed_ip(self, restricted_app: FastAPI) -> None:
        from httpx2 import ASGITransport, AsyncClient

        # 10.0.0.1 is not in 192.0.2.0/24
        async with AsyncClient(
            transport=ASGITransport(app=restricted_app),
            base_url="http://test",
            headers={"X-Forwarded-For": "10.0.0.1"},
        ) as c:
            resp = await c.get("/_metrics")
        assert resp.status_code == 403


class TestMetricsDisabledByDefault:
    def test_metrics_disabled_by_default_in_config(self) -> None:
        from arvel.observability.config import ObservabilityConfig

        config = ObservabilityConfig()
        assert config.metrics_enabled is False
