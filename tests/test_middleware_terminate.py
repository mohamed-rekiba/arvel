"""C4 — terminable middleware: terminate(request, response) runs after the response is built."""

from __future__ import annotations

from typing import Any

from litestar.testing import TestClient

from arvel.http import HttpKernel
from arvel.http.middleware import Middleware
from arvel.http.response import Response

EVENTS: list[str] = []


class Terminable(Middleware):
    async def handle(self, request: Any, call_next: Any) -> Any:
        EVENTS.append("handle")
        return await call_next(request)

    async def terminate(self, request: Any, response: Any) -> None:
        # runs after the response is built, and can see it
        EVENTS.append(f"terminate:{response.status_code}")


def _handler(request: Any) -> Response:
    EVENTS.append("handler")
    return Response({"ok": True}, status=201)


def test_terminate_runs_after_response() -> None:
    EVENTS.clear()
    kernel = HttpKernel()
    kernel.global_middleware = [Terminable]
    kernel.get("/", _handler)
    with TestClient(kernel.build()) as client:
        assert client.get("/").status_code == 201
    assert EVENTS == ["handle", "handler", "terminate:201"]


def test_plain_middleware_without_terminate_override_is_fine() -> None:
    EVENTS.clear()

    class Plain(Middleware):
        async def handle(self, request: Any, call_next: Any) -> Any:
            return await call_next(request)

    kernel = HttpKernel()
    kernel.global_middleware = [Plain]
    kernel.get("/", _handler)
    with TestClient(kernel.build()) as client:
        assert client.get("/").status_code == 201  # base no-op terminate → no error


def test_session_cookie_emitted_on_success_but_not_on_handler_error() -> None:
    """L2 fail-closed: terminate (which sets the cookie) is skipped when the handler raises."""
    from arvel.http.middleware import StartSession

    def ok(_request: Any) -> Response:
        return Response({"ok": True})

    def boom(_request: Any) -> Response:
        raise RuntimeError("boom")

    kernel = HttpKernel()
    kernel.global_middleware = [StartSession]
    kernel.get("/ok", ok)
    kernel.get("/boom", boom)
    app = kernel.build()

    with TestClient(app) as c1:  # fresh client → no cookie → success issues one
        success = c1.get("/ok")
    with TestClient(app, raise_server_exceptions=False) as c2:  # fresh client → handler raises
        errored = c2.get("/boom")

    assert any("session" in c.lower() for c in success.headers.get_list("set-cookie"))
    assert errored.status_code >= 500
    assert not any("session" in c.lower() for c in errored.headers.get_list("set-cookie"))
