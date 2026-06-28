"""C4a — two-tier middleware pipeline (global → group), order + short-circuit."""

from __future__ import annotations

from typing import Any

from litestar.testing import TestClient

from arvel.http import HttpKernel
from arvel.http.middleware import Middleware
from arvel.http.response import Response

ORDER: list[str] = []


class M1(Middleware):
    async def handle(self, request: Any, call_next: Any) -> Any:
        ORDER.append("m1-before")
        result = await call_next(request)
        ORDER.append("m1-after")
        return result


class M2(Middleware):
    async def handle(self, request: Any, call_next: Any) -> Any:
        ORDER.append("m2-before")
        result = await call_next(request)
        ORDER.append("m2-after")
        return result


class Block(Middleware):
    async def handle(self, request: Any, call_next: Any) -> Any:
        return Response("blocked", status=403)


def _handler(request: Any) -> dict[str, bool]:
    ORDER.append("handler")
    return {"ok": True}


def test_pipeline_runs_in_onion_order() -> None:
    ORDER.clear()
    kernel = HttpKernel()
    kernel.global_middleware = [M1, M2]
    kernel.get("/", _handler)
    with TestClient(kernel.build()) as client:
        assert client.get("/").json() == {"ok": True}
    assert ORDER == ["m1-before", "m2-before", "handler", "m2-after", "m1-after"]


def test_middleware_can_short_circuit() -> None:
    ORDER.clear()
    kernel = HttpKernel()
    kernel.global_middleware = [Block]
    kernel.get("/", _handler)
    with TestClient(kernel.build()) as client:
        response = client.get("/")
    assert response.status_code == 403
    assert response.text == "blocked"
    assert "handler" not in ORDER  # destination never reached


def test_group_middleware_only_applies_to_its_group() -> None:
    ORDER.clear()
    kernel = HttpKernel()
    kernel.groups["api"] = [M2]
    kernel.get("/web", _handler, group="web")
    kernel.get("/api", _handler, group="api")
    with TestClient(kernel.build()) as client:
        client.get("/web")
        assert "m2-before" not in ORDER
        ORDER.clear()
        client.get("/api")
        assert "m2-before" in ORDER
