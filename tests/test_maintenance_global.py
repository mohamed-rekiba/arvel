"""ch04 — maintenance mode is wired into the global pipeline. PreventRequestsDuringMaintenance
existed and was documented to return 503 while `arvel down`, but was never added to
global_middleware, so maintenance mode never affected HTTP. use_default_global() fixes it."""

from __future__ import annotations

from typing import Any

import pytest
from litestar.testing import TestClient

import arvel.http.maintenance as maint
from arvel.http import HttpKernel
from arvel.http.maintenance import PreventRequestsDuringMaintenance
from arvel.http.middleware import RequestContextMiddleware
from arvel.routing import Router


async def _ok(request: Any) -> dict[str, str]:
    return {"ok": "1"}


def test_use_default_global_wires_maintenance_early() -> None:
    kernel = HttpKernel().use_default_global()
    # request-id is first (M3, so all logs carry it); maintenance runs right after, before validation
    assert kernel.global_middleware[0] is RequestContextMiddleware
    assert PreventRequestsDuringMaintenance in kernel.global_middleware
    kernel.use_default_global()  # idempotent — no duplicate
    assert kernel.global_middleware.count(PreventRequestsDuringMaintenance) == 1


def test_down_app_returns_503(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _down() -> bool:
        return True

    async def _payload() -> dict[str, Any]:
        return {"message": "Back soon", "retry": 30}

    monkeypatch.setattr(maint, "is_down", _down)
    monkeypatch.setattr(maint, "payload", _payload)
    router = Router()
    router.get("/", _ok)
    kernel = HttpKernel().use_default_global()
    router.apply_to(kernel)
    with TestClient(kernel.build()) as client:
        response = client.get("/")
        assert response.status_code == 503
        assert response.headers.get("Retry-After") == "30"


def test_up_app_passes_through(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _down() -> bool:
        return False

    monkeypatch.setattr(maint, "is_down", _down)
    router = Router()
    router.get("/", _ok)
    kernel = HttpKernel().use_default_global()
    router.apply_to(kernel)
    with TestClient(kernel.build()) as client:
        assert client.get("/").json() == {"ok": "1"}
