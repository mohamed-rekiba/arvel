"""Tests for LocaleMiddleware — Accept-Language parsing and ContextVar lifecycle."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from arvel.i18n.middleware import LocaleMiddleware, get_request_locale

if TYPE_CHECKING:
    from starlette.requests import Request


def _locale_endpoint(request: Request) -> JSONResponse:
    return JSONResponse({"locale": get_request_locale()})


@pytest.fixture
def app() -> Starlette:
    application = Starlette(routes=[Route("/locale", _locale_endpoint)])
    application.add_middleware(LocaleMiddleware, default_locale="en")
    return application


@pytest.fixture
def client(app: Starlette) -> TestClient:
    return TestClient(app)


class TestLocaleMiddleware:
    def test_default_locale_when_no_header(self, client: TestClient) -> None:
        resp = client.get("/locale")
        assert resp.json()["locale"] == "en"

    def test_parses_accept_language(self, client: TestClient) -> None:
        resp = client.get("/locale", headers={"Accept-Language": "fr-FR, en;q=0.9"})
        assert resp.json()["locale"] == "fr"

    def test_parses_simple_language(self, client: TestClient) -> None:
        resp = client.get("/locale", headers={"Accept-Language": "de"})
        assert resp.json()["locale"] == "de"

    def test_strips_region_subtag(self, client: TestClient) -> None:
        resp = client.get("/locale", headers={"Accept-Language": "en-US"})
        assert resp.json()["locale"] == "en"

    def test_empty_header_uses_default(self, client: TestClient) -> None:
        resp = client.get("/locale", headers={"Accept-Language": ""})
        assert resp.json()["locale"] == "en"


class TestGetRequestLocale:
    def test_returns_default_when_not_set(self) -> None:
        assert get_request_locale() == "en"
