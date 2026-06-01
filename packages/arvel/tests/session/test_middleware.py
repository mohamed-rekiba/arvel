"""Tests for StartSession middleware."""

from __future__ import annotations

from typing import cast

import httpx
from arvel.session import SessionData
from arvel.session.middleware import StartSession
from arvel.session.stores.array import ArraySessionStore
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route
from starlette.testclient import TestClient


def make_app(store: ArraySessionStore) -> Starlette:
    async def handler(request: Request) -> Response:
        session: SessionData = request.state.session
        value = session.get("counter", default=0)
        session.put("counter", int(value) + 1)
        return Response(str(value))

    middleware = [Middleware(StartSession, store=store, lifetime=120)]
    return Starlette(routes=[Route("/", handler)], middleware=middleware)


class TestStartSessionMiddleware:
    def test_session_attached_to_request_state(self) -> None:
        store = ArraySessionStore(lifetime=120)
        app = make_app(store)
        client = cast("httpx.Client", TestClient(app, raise_server_exceptions=True))
        response = client.get("/")
        assert response.status_code == 200

    def test_session_persists_across_requests(self) -> None:
        store = ArraySessionStore(lifetime=120)
        app = make_app(store)
        client = cast("httpx.Client", TestClient(app, raise_server_exceptions=True))
        r1 = client.get("/")
        r2 = client.get("/")
        assert r1.text == "0"
        assert r2.text == "1"

    def test_session_cookie_set_in_response(self) -> None:
        store = ArraySessionStore(lifetime=120)
        app = make_app(store)
        client = cast("httpx.Client", TestClient(app, raise_server_exceptions=True))
        response = client.get("/")
        assert "arvel_session" in response.cookies or "Set-Cookie" in response.headers

    def test_accessing_session_without_middleware_raises(self) -> None:
        """Accessing request.state.session without StartSession gives a clear error."""

        async def handler(request: Request) -> Response:
            _ = request.state.session
            return Response("ok")

        from starlette.routing import Route

        app = Starlette(routes=[Route("/", handler)])
        client = cast("httpx.Client", TestClient(app, raise_server_exceptions=False))
        response = client.get("/")
        assert response.status_code == 500
