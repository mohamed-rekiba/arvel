"""Tests for HTTP response helpers — json_response, redirect, no_content."""

from __future__ import annotations

from starlette.responses import JSONResponse, RedirectResponse, Response

from arvel.http.response import json_response, no_content, redirect


class TestJsonResponse:
    def test_returns_json_response(self) -> None:
        resp = json_response({"key": "value"})
        assert isinstance(resp, JSONResponse)

    def test_default_status_200(self) -> None:
        resp = json_response({"ok": True})
        assert resp.status_code == 200

    def test_custom_status_code(self) -> None:
        resp = json_response({"created": True}, status_code=201)
        assert resp.status_code == 201

    def test_custom_headers(self) -> None:
        resp = json_response({"ok": True}, headers={"X-Custom": "test"})
        assert resp.headers.get("x-custom") == "test"

    def test_body_contains_data(self) -> None:
        resp = json_response({"msg": "hello"})
        assert b"hello" in resp.body


class TestRedirect:
    def test_returns_redirect_response(self) -> None:
        resp = redirect("/new-location")
        assert isinstance(resp, RedirectResponse)

    def test_default_status_307(self) -> None:
        resp = redirect("/new-location")
        assert resp.status_code == 307

    def test_custom_status_code(self) -> None:
        resp = redirect("/new-location", status_code=301)
        assert resp.status_code == 301


class TestNoContent:
    def test_returns_response(self) -> None:
        resp = no_content()
        assert isinstance(resp, Response)

    def test_status_204(self) -> None:
        resp = no_content()
        assert resp.status_code == 204
