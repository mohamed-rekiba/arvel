"""response() / redirect() helpers — builders and session-flash redirects."""

from __future__ import annotations

from typing import Any

from arvel.http import back, redirect, response, to_route
from arvel.http.responses import Redirect
from arvel.session import SessionData
from starlette.requests import Request


def _request(
    *,
    headers: dict[str, str] | None = None,
    session: SessionData | None = None,
) -> Request:
    raw_headers = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    state: dict[str, Any] = {}
    if session is not None:
        state["session"] = session
    scope: dict[str, Any] = {"type": "http", "headers": raw_headers, "state": state}
    return Request(scope)


class TestResponseFactory:
    def test_json(self) -> None:
        resp = response().json({"ok": True}, status=201)
        assert resp.status_code == 201
        assert resp.body == b'{"ok":true}'

    def test_text(self) -> None:
        resp = response().text("hello", status=200)
        assert resp.status_code == 200
        assert resp.body == b"hello"
        assert resp.media_type == "text/plain"

    def test_make_with_bytes_and_headers(self) -> None:
        resp = response().make(b"raw", status=200, headers={"X-Test": "1"})
        assert resp.body == b"raw"
        assert resp.headers["x-test"] == "1"

    def test_no_content(self) -> None:
        resp = response().no_content()
        assert resp.status_code == 204
        assert resp.body == b""

    def test_response_returns_singleton(self) -> None:
        assert response() is response()


class TestRedirect:
    def test_redirect_sets_location_and_status(self) -> None:
        resp = redirect("/dashboard")
        assert isinstance(resp, Redirect)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/dashboard"

    def test_redirect_custom_status(self) -> None:
        resp = redirect("/dashboard", status=301)
        assert resp.status_code == 301

    def test_with_flashes_into_session(self) -> None:
        session = SessionData({"_session_id": "abc"})
        req = _request(session=session)
        result = redirect("/home").with_(req, status="Saved!", count=3)
        assert isinstance(result, Redirect)  # chainable, returns self
        # Flash is readable on the NEXT request after finalize.
        session.finalize_flash()
        assert session.get("status") == "Saved!"
        assert session.get("count") == 3

    def test_with_no_session_is_noop(self) -> None:
        req = _request()  # no session middleware
        result = redirect("/home").with_(req, status="ignored")
        assert result.status_code == 302  # didn't raise


class TestBack:
    def test_back_uses_referer(self) -> None:
        req = _request(headers={"Referer": "/previous"})
        resp = back(req)
        assert resp.headers["location"] == "/previous"

    def test_back_falls_back_when_no_referer(self) -> None:
        req = _request()
        resp = back(req, fallback="/start")
        assert resp.headers["location"] == "/start"


class TestToRoute:
    def test_to_route_generates_url_from_named_route(self) -> None:
        from arvel.routing import Route, Router

        Router.reset_singleton()

        @Route.get("/users/{id}", name="users.show")
        async def show(id: int) -> dict[str, int]:
            return {"id": id}

        assert callable(show)
        resp = to_route("users.show", id=7)
        assert isinstance(resp, Redirect)
        assert resp.headers["location"] == "/users/7"
        assert resp.status_code == 302
