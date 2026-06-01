"""lifecycle regression suite.

Locks the bootstrap contract: provider ordering, middleware composition,
request-id propagation, reverse-order shutdown, and exception logging. These
guard against silent breakage when the provider chain or ASGI stack changes.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from arvel.application import Application
from arvel.services import BaseService, HealthResult, HealthStatus
from arvel.testing.observability import FakeObservability
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _index(names: list[str], needle: str) -> int:
    return next(i for i, n in enumerate(names) if n == needle)


def test_provider_chain_order(tmp_path: Path) -> None:
    app = Application.configure(tmp_path).with_environment("testing").with_providers([]).create()
    names = [type(provider).__name__ for provider in app.iter_providers()]

    assert (
        _index(names, "ConfigServiceProvider")
        < _index(names, "LogServiceProvider")
        < _index(names, "ContextServiceProvider")
        < _index(names, "ObservabilityServiceProvider")
        < _index(names, "DatabaseServiceProvider")
        < _index(names, "HttpServiceProvider")
    )


def test_middleware_composition_order(tmp_path: Path) -> None:
    app = Application.configure(tmp_path).with_environment("testing").with_providers([]).create()
    fa = app.into_asgi()

    names = [getattr(mw.cls, "__name__", type(mw.cls).__name__) for mw in fa.user_middleware]

    assert (
        _index(names, "ObservabilityMiddleware")
        < _index(names, "ContextMiddleware")
        < _index(names, "ArvelScopeMiddleware")
    )


def test_request_id_in_headers_and_logs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Disable the SDK so the provider doesn't swap the global logger out from
    # under FakeObservability; request-id binding still runs.
    monkeypatch.setenv("OTEL_SDK_DISABLED", "1")
    app = Application.configure(tmp_path).with_environment("testing").with_providers([]).create()
    fa = app.into_asgi()

    @fa.get("/ping")
    async def _ping() -> dict[str, str]:
        from arvel.facades import Log

        Log.info("ping.handled")
        return {"ok": "yes"}

    del _ping  # registered via decorator; drop local binding
    with FakeObservability() as obs, TestClient(fa) as client:
        response = client.get("/ping")

    assert "x-request-id" in {k.lower() for k in response.headers}
    records = [r for r in obs.log_records if r.body == "ping.handled"]
    assert records
    assert "request_id" in records[0].attributes


async def test_shutdown_disconnects_in_reverse_order(tmp_path: Path) -> None:
    log: list[str] = []

    class _Recorder(BaseService):
        def __init__(self, name: str) -> None:
            self.name = name

        async def disconnect(self) -> None:
            log.append(self.name)

        async def health_check(self) -> HealthResult:
            return HealthResult(HealthStatus.healthy)

    app = Application.configure(tmp_path).with_environment("testing").with_providers([]).create()
    app.register_service(_Recorder("first"))
    app.register_service(_Recorder("second"))

    await app.boot()
    await app.shutdown()

    assert log == ["second", "first"]


def test_unhandled_exception_logs_and_hides_trace() -> None:
    from arvel.http.exceptions import HttpExceptionHandler

    fa = FastAPI()
    HttpExceptionHandler().register(fa)

    @fa.get("/explode")
    async def _explode() -> dict[str, str]:
        raise RuntimeError("secret internals")

    del _explode  # registered via decorator; drop local binding
    client = TestClient(fa, raise_server_exceptions=False)
    with FakeObservability() as obs:
        response = client.get("/explode")

    assert response.status_code == 500
    assert "secret internals" not in response.text
    assert "Traceback" not in response.text
    assert any(r.body == "http.unhandled_exception" for r in obs.log_records)
