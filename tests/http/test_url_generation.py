"""Tests for URL generation and signed routes — Story 7.

FR-070: url_for() generates paths from named routes
FR-071: signed_url() generates HMAC-SHA256 signed URLs
FR-072: Signature validation (valid, expired, tampered)
FR-073: SignedRouteMiddleware rejects invalid signatures
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from arvel.http.exceptions import InvalidSignatureError, RouteRegistrationError
from arvel.http.provider import _wrap_specific_route
from arvel.http.router import Router
from arvel.http.signed import SignedRouteMiddleware
from arvel.http.url import UrlGenerator

APP_KEY = "test-secret-key-for-signing-32chars!"


@pytest.fixture
def router_with_routes() -> Router:
    router = Router()

    async def list_users():
        return {"users": []}

    async def show_user(id: int):  # noqa: A002
        return {"id": id}

    async def verify_email(id: int):  # noqa: A002
        return {"verified": True}

    router.get("/users", list_users, name="users.index")
    router.get("/users/{id}", show_user, name="users.show")
    router.get("/verify/{id}", verify_email, name="verify.email")
    return router


@pytest.fixture
def url_gen(router_with_routes: Router) -> UrlGenerator:
    return UrlGenerator(
        router_with_routes,
        app_key=APP_KEY,
        base_url="https://app.example.com",
    )


class TestUrlFor:
    """FR-070: URL generation from named routes."""

    def test_url_for_simple_path(self, url_gen: UrlGenerator) -> None:
        url = url_gen.url_for("users.index")
        assert url == "https://app.example.com/users"

    def test_url_for_with_params(self, url_gen: UrlGenerator) -> None:
        url = url_gen.url_for("users.show", id=42)
        assert url == "https://app.example.com/users/42"

    def test_url_for_without_base_url(self, router_with_routes: Router) -> None:
        gen = UrlGenerator(router_with_routes)
        url = gen.url_for("users.index")
        assert url == "/users"

    def test_url_for_unknown_route_raises(self, url_gen: UrlGenerator) -> None:
        with pytest.raises(RouteRegistrationError, match="No route named 'nonexistent'"):
            url_gen.url_for("nonexistent")

    def test_url_for_missing_param_raises(self, url_gen: UrlGenerator) -> None:
        with pytest.raises(RouteRegistrationError, match="Missing parameter"):
            url_gen.url_for("users.show")


class TestRouterUrlFor:
    """URL generation on the Router directly."""

    def test_router_url_for(self, router_with_routes: Router) -> None:
        path = router_with_routes.url_for("users.show", id=42)
        assert path == "/users/42"

    def test_router_url_for_simple(self, router_with_routes: Router) -> None:
        path = router_with_routes.url_for("users.index")
        assert path == "/users"


class TestSignedUrl:
    """FR-071: Signed URL generation."""

    def test_signed_url_contains_signature(self, url_gen: UrlGenerator) -> None:
        url = url_gen.signed_url("users.show", id=42)
        assert "signature=" in url

    def test_signed_url_with_expiry(self, url_gen: UrlGenerator) -> None:
        url = url_gen.signed_url("verify.email", expires=3600, id=1)
        assert "expires=" in url
        assert "signature=" in url

    def test_signed_url_without_app_key_raises(self, router_with_routes: Router) -> None:
        gen = UrlGenerator(router_with_routes, app_key="")
        with pytest.raises(ValueError, match="app_key is required"):
            gen.signed_url("users.index")

    def test_signed_url_has_base_url(self, url_gen: UrlGenerator) -> None:
        url = url_gen.signed_url("users.index")
        assert url.startswith("https://app.example.com/users?")


class TestSignatureValidation:
    """FR-072: Signature validation."""

    def test_valid_signature_passes(self, url_gen: UrlGenerator) -> None:
        url = url_gen.signed_url("users.show", id=42)
        assert url_gen.validate_signature(url) is True

    def test_valid_signature_with_expiry_passes(self, url_gen: UrlGenerator) -> None:
        url = url_gen.signed_url("verify.email", expires=3600, id=1)
        assert url_gen.validate_signature(url) is True

    def test_expired_signature_raises(self, url_gen: UrlGenerator) -> None:
        with patch("arvel.http.url.time") as mock_time:
            mock_time.time.return_value = 1000.0
            url = url_gen.signed_url("users.show", expires=60, id=42)

        with patch("arvel.http.url.time") as mock_time:
            mock_time.time.return_value = 2000.0
            with pytest.raises(InvalidSignatureError, match="expired"):
                url_gen.validate_signature(url)

    def test_tampered_signature_raises(self, url_gen: UrlGenerator) -> None:
        url = url_gen.signed_url("users.show", id=42)
        tampered = url.replace("signature=", "signature=tampered")
        with pytest.raises(InvalidSignatureError, match="Invalid signature"):
            url_gen.validate_signature(tampered)

    def test_missing_signature_raises(self, url_gen: UrlGenerator) -> None:
        with pytest.raises(InvalidSignatureError, match="Missing signature"):
            url_gen.validate_signature("https://app.example.com/users/42")

    def test_tampered_path_with_valid_sig_format_raises(self, url_gen: UrlGenerator) -> None:
        url = url_gen.signed_url("users.show", id=42)
        tampered = url.replace("/users/42", "/users/99")
        with pytest.raises(InvalidSignatureError, match="Invalid signature"):
            url_gen.validate_signature(tampered)


class TestSignedRouteMiddleware:
    """FR-073: SignedRouteMiddleware rejects invalid signatures."""

    def _build_signed_app(self, url_gen: UrlGenerator) -> FastAPI:
        """Build a FastAPI app with signed route middleware on /users/{id}."""
        from functools import partial

        app = FastAPI()

        async def show_user(id: int):  # noqa: A002
            return {"id": id}

        app.add_api_route("/users/{id}", show_user, methods=["GET"], name="users.show")

        bound_cls = partial(SignedRouteMiddleware, url_generator=url_gen)
        _wrap_specific_route(app.routes[-1], [bound_cls])

        return app

    def test_valid_signed_request_passes(self, router_with_routes: Router) -> None:
        url_gen = UrlGenerator(router_with_routes, app_key=APP_KEY)
        signed = url_gen.signed_url("users.show", id=42)

        app = self._build_signed_app(url_gen)

        client = TestClient(app, raise_server_exceptions=False)
        query = signed.split("?", 1)[1]
        response = client.get(f"/users/42?{query}")
        assert response.status_code == 200

    def test_unsigned_request_returns_403(self, router_with_routes: Router) -> None:
        url_gen = UrlGenerator(router_with_routes, app_key=APP_KEY)

        app = self._build_signed_app(url_gen)

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/users/42")
        assert response.status_code == 403
        body = response.json()
        assert body["status"] == 403

    def test_tampered_request_returns_403(self, router_with_routes: Router) -> None:
        url_gen = UrlGenerator(router_with_routes, app_key=APP_KEY)
        signed = url_gen.signed_url("users.show", id=42)

        app = self._build_signed_app(url_gen)

        client = TestClient(app, raise_server_exceptions=False)
        query = signed.split("?", 1)[1]
        tampered_query = query.replace("signature=", "signature=bad")
        response = client.get(f"/users/42?{tampered_query}")
        assert response.status_code == 403
