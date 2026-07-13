"""Phase: logging — contextual logging (per-request bound context). Written test-first."""

from __future__ import annotations

from typing import Any

import structlog.contextvars as scv
from litestar.testing import TestClient

from arvel.http import HttpKernel
from arvel.http.middleware import RequestContextMiddleware
from arvel.kernel.logging import LogManager


def test_with_context_binds_to_contextvars() -> None:
    LogManager.clear_context()
    LogManager.with_context(request_id="abc", user_id=7)
    bound = scv.get_contextvars()
    assert bound.get("request_id") == "abc"
    assert bound.get("user_id") == 7
    LogManager.clear_context()
    assert "request_id" not in scv.get_contextvars()


def test_bound_context_is_merged_into_log_events() -> None:
    import structlog

    LogManager.clear_context()
    LogManager.with_context(request_id="r-1")
    try:
        cap = structlog.testing.LogCapture()
        structlog.configure(processors=[scv.merge_contextvars, cap])
        LogManager().info("did a thing")
        assert cap.entries[0]["request_id"] == "r-1"
    finally:
        LogManager.clear_context()


def test_request_middleware_binds_a_request_id() -> None:
    def handler(request: Any) -> dict[str, Any]:
        return {"rid": scv.get_contextvars().get("request_id")}

    kernel = HttpKernel()
    kernel.global_middleware = [RequestContextMiddleware]
    kernel.get("/", handler)
    with TestClient(kernel.build()) as client:
        # explicit incoming id is honoured
        assert client.get("/", headers={"x-request-id": "req-123"}).json() == {"rid": "req-123"}
        # otherwise one is generated (non-empty)
        generated = client.get("/").json()["rid"]
        assert isinstance(generated, str) and len(generated) >= 8


def test_request_id_is_cleared_after_request() -> None:
    LogManager.clear_context()
    kernel = HttpKernel()
    kernel.global_middleware = [RequestContextMiddleware]
    kernel.get("/", lambda request: {"ok": True})
    with TestClient(kernel.build()) as client:
        client.get("/", headers={"x-request-id": "leak-check"})
    # the per-request id must not leak into the surrounding context
    assert "request_id" not in scv.get_contextvars()
