"""E1 — uncaught exceptions are reported and rendered as a content-negotiated, debug-gated 500."""

from __future__ import annotations

from typing import Any

from litestar.testing import TestClient

from arvel.http import HttpKernel
from arvel.kernel.application import Application
from arvel.kernel.config import Repository
from arvel.kernel.exceptions import ExceptionHandler
from arvel.routing import Router


async def _boom(request: Any) -> dict[str, Any]:
    raise ValueError("leaky internal detail")


class _LeakyServerError(Exception):
    """A 5xx error carrying a sensitive `.detail` (mimics a litestar HTTPException)."""

    status_code = 500
    detail = "DB dsn postgres://user:p@ss@host/db"


async def _boom_with_detail(request: Any) -> dict[str, Any]:
    raise _LeakyServerError


class _SpyLogger:
    def __init__(self) -> None:
        self.errors: list[tuple[Any, ...]] = []

    def error(self, *args: Any, **kwargs: Any) -> None:
        self.errors.append((args, kwargs))


def _client(*, debug: bool) -> tuple[TestClient[Any], _SpyLogger]:
    logger = _SpyLogger()
    app = Application()
    app.instance("config", Repository({"app": {"debug": debug}}))
    app.instance("exceptions", ExceptionHandler(logger))  # type: ignore[arg-type]
    router = Router()
    router.get("/boom", _boom)
    router.get("/boom-detail", _boom_with_detail)
    kernel = HttpKernel(app)
    router.apply_to(kernel)
    return TestClient(kernel.build()), logger


def test_uncaught_exception_is_reported_and_rendered_500_without_leaking() -> None:
    client, logger = _client(debug=False)
    with client:
        resp = client.get("/boom", headers={"accept": "application/json"})
    assert resp.status_code == 500
    assert resp.json()["message"] == "Server Error"  # generic in production — no detail leak
    assert "leaky internal detail" not in resp.text
    assert logger.errors  # report() logged the unhandled exception (E1)


def test_debug_surfaces_the_real_error() -> None:
    client, _ = _client(debug=True)
    with client:
        resp = client.get("/boom", headers={"accept": "application/json"})
    assert resp.status_code == 500
    assert "ValueError" in resp.json()["message"]


def test_5xx_detail_is_never_leaked_in_production() -> None:
    client, _ = _client(debug=False)
    with client:
        resp = client.get("/boom-detail", headers={"accept": "application/json"})
    assert resp.status_code == 500
    assert resp.json()["message"] == "Server Error"
    assert "postgres" not in resp.text
