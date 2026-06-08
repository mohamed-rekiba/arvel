"""/_health endpoint aggregating BaseService checks."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import cast

import httpx2 as httpx
import pytest
from arvel.application import Application
from arvel.services import BaseService, HealthResult, HealthStatus
from fastapi.testclient import TestClient

pytest.importorskip("fastapi")


class _Static(BaseService):
    def __init__(self, name: str, result: HealthResult) -> None:
        self.name = name
        self._result = result

    async def health_check(self) -> HealthResult:
        return self._result


def _app(tmp_path: Path) -> Application:
    return Application.configure(tmp_path).with_environment("testing").with_providers([]).create()


def test_all_healthy_returns_200(tmp_path: Path) -> None:
    app = _app(tmp_path)
    app.register_service(_Static("db", HealthResult(HealthStatus.healthy)))
    app.register_service(_Static("cache", HealthResult(HealthStatus.healthy)))

    with cast("httpx.Client", TestClient(app.into_asgi())) as client:
        response = client.get("/_health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["checks"]["db"]["status"] == "healthy"
    assert body["checks"]["cache"]["status"] == "healthy"


def test_any_unhealthy_returns_503(tmp_path: Path) -> None:
    app = _app(tmp_path)
    app.register_service(_Static("db", HealthResult(HealthStatus.healthy)))
    app.register_service(_Static("queue", HealthResult(HealthStatus.unhealthy, "no connection")))

    with cast("httpx.Client", TestClient(app.into_asgi())) as client:
        response = client.get("/_health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unhealthy"
    assert body["checks"]["queue"]["detail"] == "no connection"


def test_degraded_returns_200(tmp_path: Path) -> None:
    app = _app(tmp_path)
    app.register_service(_Static("cache", HealthResult(HealthStatus.degraded, "slow")))

    with cast("httpx.Client", TestClient(app.into_asgi())) as client:
        response = client.get("/_health")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"


def test_raising_check_reported_unhealthy(tmp_path: Path) -> None:
    class _Boom(BaseService):
        name = "boom"

        async def health_check(self) -> HealthResult:
            raise RuntimeError("kaput")

    app = _app(tmp_path)
    app.register_service(_Boom())

    with cast("httpx.Client", TestClient(app.into_asgi())) as client:
        response = client.get("/_health")

    assert response.status_code == 503
    assert response.json()["checks"]["boom"]["status"] == "unhealthy"


def test_checks_run_concurrently(tmp_path: Path) -> None:
    # Two services that hand off to each other: only succeeds if run concurrently.
    a_ready = asyncio.Event()
    b_ready = asyncio.Event()

    class _A(BaseService):
        name = "a"

        async def health_check(self) -> HealthResult:
            a_ready.set()
            await asyncio.wait_for(b_ready.wait(), timeout=2.0)
            return HealthResult(HealthStatus.healthy)

    class _B(BaseService):
        name = "b"

        async def health_check(self) -> HealthResult:
            b_ready.set()
            await asyncio.wait_for(a_ready.wait(), timeout=2.0)
            return HealthResult(HealthStatus.healthy)

    app = _app(tmp_path)
    app.register_service(_A())
    app.register_service(_B())

    with cast("httpx.Client", TestClient(app.into_asgi())) as client:
        response = client.get("/_health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_timeout_reported_as_unhealthy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import arvel.health as health_mod

    monkeypatch.setattr(health_mod, "_CHECK_TIMEOUT_SECONDS", 0.05)

    class _Slow(BaseService):
        name = "slow"

        async def health_check(self) -> HealthResult:
            await asyncio.sleep(0.5)
            return HealthResult(HealthStatus.healthy)

    app = _app(tmp_path)
    app.register_service(_Slow())

    with cast("httpx.Client", TestClient(app.into_asgi())) as client:
        response = client.get("/_health")

    assert response.status_code == 503
    assert response.json()["checks"]["slow"]["detail"] == "timeout"


def test_cidr_restriction_returns_403(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HEALTH_ALLOWED_CIDRS", "10.0.0.0/8")
    app = _app(tmp_path)
    app.register_service(_Static("db", HealthResult(HealthStatus.healthy)))

    with cast("httpx.Client", TestClient(app.into_asgi())) as client:
        response = client.get("/_health", headers={"X-Forwarded-For": "8.8.8.8"})

    assert response.status_code == 403


def test_forwarded_header_cannot_spoof_cidr_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # XFF claims an allowlisted IP, but the peer isn't a trusted proxy — the guard
    # must use the real peer and reject. Without the fix this returned 200.
    monkeypatch.setenv("HEALTH_ALLOWED_CIDRS", "10.0.0.0/8")
    app = _app(tmp_path)
    app.register_service(_Static("db", HealthResult(HealthStatus.healthy)))

    with cast("httpx.Client", TestClient(app.into_asgi())) as client:
        response = client.get("/_health", headers={"X-Forwarded-For": "10.0.0.1"})

    assert response.status_code == 403
