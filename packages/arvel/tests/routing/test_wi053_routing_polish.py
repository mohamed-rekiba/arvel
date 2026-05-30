"""Failing tests for WI-arvel-053: Routing Security & UX Polish.

Covers Epic 048 stories:

- Story 4 polish: `url()` helper, `RoutingError` for missing params, `absolute=True` on `route()`.
- Story 6 polish: `name_prefix` parameter in `Route.group()`.
- Story 7: `MethodSpoofMiddleware` for HTML form `_method=PUT/PATCH/DELETE`.
- Story 8: `URL.signed_route()`, `Request.has_valid_signature()`, `SignedMiddleware`.

Run BEFORE implementation — every test in this file MUST fail (Red state).
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

# ─────────────────────────── Story 6 polish: name_prefix in Route.group ──────


class TestStory6NamePrefix:
    """`Route.group(name_prefix=...)` should stack route name prefixes the same
    way prefix stacks paths and middleware stacks middlewares."""

    def test_name_prefix_applied_to_inner_named_route(self) -> None:
        from arvel.routing import Route, Router

        Router.reset_singleton()

        with Route.group(name_prefix="admin."):

            @Route.get("/users", name="users.index")
            async def _h() -> dict[str, Any]:
                return {}

            del _h  # registered via @Route.*; drop local binding

        routes = Router.singleton().routes()
        assert any(r.name == "admin.users.index" for r in routes)

    def test_name_prefix_stacks_when_nested(self) -> None:
        from arvel.routing import Route, Router

        Router.reset_singleton()

        with (
            Route.group(name_prefix="admin."),
            Route.group(name_prefix="users."),
        ):

            @Route.get("/users/{id}", name="show")
            async def _h(id: int) -> dict[str, Any]:
                return {}

            del _h  # registered via @Route.*; drop local binding

        routes = Router.singleton().routes()
        assert any(r.name == "admin.users.show" for r in routes)

    def test_name_prefix_does_not_affect_unnamed_routes(self) -> None:
        from arvel.routing import Route, Router

        Router.reset_singleton()

        with Route.group(name_prefix="admin."):

            @Route.get("/dashboard")
            async def _h() -> dict[str, Any]:
                return {}

            del _h  # registered via @Route.*; drop local binding

        routes = Router.singleton().routes()
        target = next(r for r in routes if r.path == "/dashboard")
        assert target.name is None

    def test_name_prefix_combines_with_path_prefix(self) -> None:
        from arvel.routing import Route, Router

        Router.reset_singleton()

        with Route.group(prefix="/api/v1", name_prefix="api."):

            @Route.get("/users", name="users.index")
            async def _h() -> dict[str, Any]:
                return {}

            del _h  # registered via @Route.*; drop local binding

        routes = Router.singleton().routes()
        assert any(r.path == "/api/v1/users" and r.name == "api.users.index" for r in routes)


# ───────────────── Story 4 polish: RoutingError + url() + absolute=True ──────


class TestStory4RoutingErrorAndUrlHelper:
    """`route()` should raise a typed `RoutingError` (not `ValueError`) when a
    required path parameter is missing, and an `url()` helper should resolve
    paths against `APP_URL`."""

    def test_route_helper_raises_routing_error_on_missing_param(self) -> None:
        from arvel.routing import Route, Router, RoutingError
        from arvel.routing import route as route_helper

        Router.reset_singleton()

        @Route.get("/users/{id}", name="users.show")
        async def _h(id: int) -> dict[str, Any]:
            return {}

        del _h  # registered via @Route.*; drop local binding

        with pytest.raises(RoutingError, match="missing parameter 'id'"):
            route_helper("users.show")

    def test_routing_error_is_value_error_subclass_for_back_compat(self) -> None:
        # The exception was previously ValueError; existing callers that catch
        # ValueError should still catch the new RoutingError.
        from arvel.routing import RoutingError

        assert issubclass(RoutingError, ValueError)

    def test_route_helper_supports_absolute_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from arvel.routing import Route, Router
        from arvel.routing import route as route_helper

        Router.reset_singleton()
        monkeypatch.setenv("APP_URL", "https://example.com")

        @Route.get("/posts/{id}", name="posts.show")
        async def _h(id: int) -> dict[str, Any]:
            return {}

        del _h  # registered via @Route.*; drop local binding

        assert route_helper("posts.show", absolute=True, id=7) == "https://example.com/posts/7"

    def test_route_helper_absolute_trims_trailing_slash_on_base(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from arvel.routing import Route, Router
        from arvel.routing import route as route_helper

        Router.reset_singleton()
        monkeypatch.setenv("APP_URL", "https://example.com/")

        @Route.get("/posts", name="posts.index")
        async def _h() -> dict[str, Any]:
            return {}

        del _h  # registered via @Route.*; drop local binding

        assert route_helper("posts.index", absolute=True) == "https://example.com/posts"

    def test_url_helper_returns_absolute_url_for_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from arvel.routing import url

        monkeypatch.setenv("APP_URL", "https://example.com")
        assert url("/posts/3") == "https://example.com/posts/3"

    def test_url_helper_preserves_query_string(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from arvel.routing import url

        monkeypatch.setenv("APP_URL", "https://example.com")
        assert url("/search?q=hello&page=2") == "https://example.com/search?q=hello&page=2"

    def test_url_helper_raises_when_app_url_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from arvel.routing import RoutingError, url

        monkeypatch.delenv("APP_URL", raising=False)
        with pytest.raises(RoutingError, match="APP_URL"):
            url("/posts")


# ───────────────── Story 7: MethodSpoofMiddleware ────────────────────────────


class TestStory7MethodSpoof:
    """`MethodSpoofMiddleware` rewrites POST requests with `_method=PUT|PATCH|
    DELETE` so HTML forms can hit non-POST routes."""

    def test_post_with_method_put_spoofs_to_put(self) -> None:
        from arvel.http.middleware import MethodSpoofMiddleware
        from arvel.routing import Route, Router
        from fastapi import FastAPI, Request
        from starlette.testclient import TestClient

        Router.reset_singleton()

        @Route.put("/items/{id}")
        async def update(id: int, request: Request) -> dict[str, Any]:
            return {"method": request.method, "id": id}

        del update  # registered via @Route.*; drop local binding

        app = FastAPI()
        app.add_middleware(MethodSpoofMiddleware)
        Router.singleton().register_with_app(app)

        client = TestClient(app)
        resp = client.post("/items/5", data={"_method": "PUT", "name": "x"})
        assert resp.status_code == 200
        assert resp.json() == {"method": "PUT", "id": 5}

    def test_post_with_method_delete_spoofs_to_delete(self) -> None:
        from arvel.http.middleware import MethodSpoofMiddleware
        from arvel.routing import Route, Router
        from fastapi import FastAPI
        from starlette.testclient import TestClient

        Router.reset_singleton()

        @Route.delete("/items/{id}")
        async def destroy(id: int) -> dict[str, Any]:
            return {"deleted": id}

        del destroy  # registered via @Route.*; drop local binding

        app = FastAPI()
        app.add_middleware(MethodSpoofMiddleware)
        Router.singleton().register_with_app(app)

        client = TestClient(app)
        resp = client.post("/items/7", data={"_method": "DELETE"})
        assert resp.status_code == 200
        assert resp.json() == {"deleted": 7}

    def test_post_with_method_patch_spoofs_to_patch(self) -> None:
        from arvel.http.middleware import MethodSpoofMiddleware
        from arvel.routing import Route, Router
        from fastapi import FastAPI
        from starlette.testclient import TestClient

        Router.reset_singleton()

        @Route.patch("/items/{id}")
        async def patch_route(id: int) -> dict[str, Any]:
            return {"patched": id}

        del patch_route  # registered via @Route.*; drop local binding

        app = FastAPI()
        app.add_middleware(MethodSpoofMiddleware)
        Router.singleton().register_with_app(app)

        client = TestClient(app)
        resp = client.post("/items/9", data={"_method": "PATCH"})
        assert resp.status_code == 200
        assert resp.json() == {"patched": 9}

    def test_method_spoof_case_insensitive(self) -> None:
        from arvel.http.middleware import MethodSpoofMiddleware
        from arvel.routing import Route, Router
        from fastapi import FastAPI
        from starlette.testclient import TestClient

        Router.reset_singleton()

        @Route.put("/items")
        async def update() -> dict[str, Any]:
            return {"ok": True}

        del update  # registered via @Route.*; drop local binding

        app = FastAPI()
        app.add_middleware(MethodSpoofMiddleware)
        Router.singleton().register_with_app(app)

        client = TestClient(app)
        # Lowercase _method value should still be honoured.
        resp = client.post("/items", data={"_method": "put"})
        assert resp.status_code == 200

    def test_method_spoof_ignored_for_get_requests(self) -> None:
        # Spoofing only applies on POST. GET with `_method=PUT` is left alone.
        from arvel.http.middleware import MethodSpoofMiddleware
        from arvel.routing import Route, Router
        from fastapi import FastAPI
        from starlette.testclient import TestClient

        Router.reset_singleton()

        @Route.get("/items")
        async def index() -> dict[str, Any]:
            return {"verb": "get"}

        del index  # registered via @Route.*; drop local binding

        app = FastAPI()
        app.add_middleware(MethodSpoofMiddleware)
        Router.singleton().register_with_app(app)

        client = TestClient(app)
        # `_method` in the query string should be ignored.
        resp = client.get("/items?_method=PUT")
        assert resp.status_code == 200
        assert resp.json() == {"verb": "get"}

    def test_method_spoof_rejects_invalid_method_value(self) -> None:
        # Anything other than PUT/PATCH/DELETE is ignored — POST stays POST.
        from arvel.http.middleware import MethodSpoofMiddleware
        from arvel.routing import Route, Router
        from fastapi import FastAPI
        from starlette.testclient import TestClient

        Router.reset_singleton()

        @Route.post("/items")
        async def store() -> dict[str, Any]:
            return {"stored": True}

        del store  # registered via @Route.*; drop local binding

        app = FastAPI()
        app.add_middleware(MethodSpoofMiddleware)
        Router.singleton().register_with_app(app)

        client = TestClient(app)
        # `_method=GET` is not a write verb; ignored.
        resp = client.post("/items", data={"_method": "GET"})
        assert resp.status_code == 200
        assert resp.json() == {"stored": True}

    def test_method_spoof_handles_non_form_post_gracefully(self) -> None:
        # JSON POSTs (no form body) must pass through untouched.
        from arvel.http.middleware import MethodSpoofMiddleware
        from arvel.routing import Route, Router
        from fastapi import FastAPI
        from starlette.testclient import TestClient

        Router.reset_singleton()

        @Route.post("/items")
        async def store() -> dict[str, Any]:
            return {"json": True}

        del store  # registered via @Route.*; drop local binding

        app = FastAPI()
        app.add_middleware(MethodSpoofMiddleware)
        Router.singleton().register_with_app(app)

        client = TestClient(app)
        resp = client.post("/items", json={"name": "x"})
        assert resp.status_code == 200
        assert resp.json() == {"json": True}


# ───────────────── Story 8: Signed URLs ──────────────────────────────────────


class TestStory8SignedUrls:
    """Signed URL generation and verification using HMAC-SHA256 over the
    application key."""

    def test_signed_route_appends_signature_query_param(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from arvel.routing import URL, Route, Router

        Router.reset_singleton()
        monkeypatch.setenv("APP_URL", "https://example.com")
        monkeypatch.setenv("APP_KEY", "base64:" + "A" * 44)

        @Route.get("/verify/{user_id}", name="verify-email")
        async def _h(user_id: int) -> dict[str, Any]:
            return {}

        del _h  # registered via @Route.*; drop local binding

        url = URL.signed_route("verify-email", user_id=5)
        parsed = urlparse(url)
        assert parsed.scheme == "https"
        assert parsed.path == "/verify/5"
        qs = parse_qs(parsed.query)
        assert "signature" in qs
        assert qs["signature"][0]  # non-empty

    def test_signed_route_with_expiry_includes_expires_query_param(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from arvel.routing import URL, Route, Router

        Router.reset_singleton()
        monkeypatch.setenv("APP_URL", "https://example.com")
        monkeypatch.setenv("APP_KEY", "base64:" + "A" * 44)

        @Route.get("/verify/{user_id}", name="verify-email")
        async def _h(user_id: int) -> dict[str, Any]:
            return {}

        del _h  # registered via @Route.*; drop local binding

        exp = datetime.now(UTC) + timedelta(hours=1)
        url = URL.signed_route("verify-email", expires_at=exp, user_id=5)
        qs = parse_qs(urlparse(url).query)
        assert "expires" in qs
        assert int(qs["expires"][0]) == int(exp.timestamp())
        assert "signature" in qs

    def test_has_valid_signature_returns_true_for_fresh_url(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from arvel.routing import URL, Route, Router
        from fastapi import FastAPI, Request
        from starlette.testclient import TestClient

        Router.reset_singleton()
        monkeypatch.setenv("APP_URL", "https://example.com")
        monkeypatch.setenv("APP_KEY", "base64:" + "A" * 44)

        @Route.get("/verify/{user_id}", name="verify-email")
        async def verify(user_id: int, request: Request) -> dict[str, Any]:
            return {"valid": URL.has_valid_signature(request)}

        del verify  # registered via @Route.*; drop local binding

        app = FastAPI()
        Router.singleton().register_with_app(app)

        signed = URL.signed_route("verify-email", user_id=5)
        # Drop scheme + host so TestClient hits the right path.
        path_and_query = signed[len("https://example.com") :]

        client = TestClient(app, base_url="https://example.com")
        resp = client.get(path_and_query)
        assert resp.status_code == 200
        assert resp.json() == {"valid": True}

    def test_has_valid_signature_returns_false_for_tampered_url(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from arvel.routing import URL, Route, Router
        from fastapi import FastAPI, Request
        from starlette.testclient import TestClient

        Router.reset_singleton()
        monkeypatch.setenv("APP_URL", "https://example.com")
        monkeypatch.setenv("APP_KEY", "base64:" + "A" * 44)

        @Route.get("/verify/{user_id}", name="verify-email")
        async def verify(user_id: int, request: Request) -> dict[str, Any]:
            return {"valid": URL.has_valid_signature(request)}

        del verify  # registered via @Route.*; drop local binding

        app = FastAPI()
        Router.singleton().register_with_app(app)

        signed = URL.signed_route("verify-email", user_id=5)
        # Swap user_id 5 → 6 to simulate tampering.
        path_and_query = signed[len("https://example.com") :].replace("/verify/5", "/verify/6")

        client = TestClient(app, base_url="https://example.com")
        resp = client.get(path_and_query)
        assert resp.status_code == 200
        assert resp.json() == {"valid": False}

    def test_has_valid_signature_returns_false_after_expiry(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from arvel.routing import URL, Route, Router
        from fastapi import FastAPI, Request
        from starlette.testclient import TestClient

        Router.reset_singleton()
        monkeypatch.setenv("APP_URL", "https://example.com")
        monkeypatch.setenv("APP_KEY", "base64:" + "A" * 44)

        @Route.get("/verify/{user_id}", name="verify-email")
        async def verify(user_id: int, request: Request) -> dict[str, Any]:
            return {"valid": URL.has_valid_signature(request)}

        del verify  # registered via @Route.*; drop local binding

        app = FastAPI()
        Router.singleton().register_with_app(app)

        # Past expiry.
        exp = datetime.now(UTC) - timedelta(hours=1)
        signed = URL.signed_route("verify-email", expires_at=exp, user_id=5)
        path_and_query = signed[len("https://example.com") :]

        client = TestClient(app, base_url="https://example.com")
        resp = client.get(path_and_query)
        assert resp.status_code == 200
        assert resp.json() == {"valid": False}

    def test_signed_middleware_rejects_invalid_signature_with_403(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from arvel.http.middleware import SignedMiddleware
        from arvel.routing import Route, Router
        from fastapi import FastAPI
        from starlette.testclient import TestClient

        Router.reset_singleton()
        monkeypatch.setenv("APP_URL", "https://example.com")
        monkeypatch.setenv("APP_KEY", "base64:" + "A" * 44)

        with Route.group(middleware=[SignedMiddleware()]):

            @Route.get("/verify/{user_id}", name="verify-email")
            async def verify(user_id: int) -> dict[str, Any]:
                return {"user_id": user_id}

            del verify  # registered via @Route.*; drop local binding

        app = FastAPI()
        Router.singleton().register_with_app(app)

        from arvel.http.exceptions import HttpExceptionHandler

        HttpExceptionHandler().register(app)

        client = TestClient(app, base_url="https://example.com")
        # Missing signature entirely.
        resp = client.get("/verify/5")
        assert resp.status_code == 403

        # Bogus signature.
        resp = client.get("/verify/5?signature=deadbeef")
        assert resp.status_code == 403

    def test_signed_middleware_allows_valid_signature(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from arvel.http.middleware import SignedMiddleware
        from arvel.routing import URL, Route, Router
        from fastapi import FastAPI
        from starlette.testclient import TestClient

        Router.reset_singleton()
        monkeypatch.setenv("APP_URL", "https://example.com")
        monkeypatch.setenv("APP_KEY", "base64:" + "A" * 44)

        with Route.group(middleware=[SignedMiddleware()]):

            @Route.get("/verify/{user_id}", name="verify-email")
            async def verify(user_id: int) -> dict[str, Any]:
                return {"user_id": user_id}

            del verify  # registered via @Route.*; drop local binding

        app = FastAPI()
        Router.singleton().register_with_app(app)

        signed = URL.signed_route("verify-email", user_id=5)
        path_and_query = signed[len("https://example.com") :]

        client = TestClient(app, base_url="https://example.com")
        resp = client.get(path_and_query)
        assert resp.status_code == 200
        assert resp.json() == {"user_id": 5}

    def test_signed_route_uses_hmac_sha256_not_md5(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # SHA-256 base64 produces ~43 chars (urlsafe, no padding). MD5 would
        # produce ~22. This guards against a regression to a weak algorithm.
        from arvel.routing import URL, Route, Router

        Router.reset_singleton()
        monkeypatch.setenv("APP_URL", "https://example.com")
        monkeypatch.setenv("APP_KEY", "base64:" + "A" * 44)

        @Route.get("/x", name="x")
        async def _h() -> dict[str, Any]:
            return {}

        del _h  # registered via @Route.*; drop local binding

        signed = URL.signed_route("x")
        qs = parse_qs(urlparse(signed).query)
        sig = qs["signature"][0]
        # urlsafe base64 of 32 bytes → 43 chars (no padding) or 44 (with =).
        assert 40 <= len(sig.rstrip("=")) <= 50

    def test_signed_route_signature_changes_if_params_change(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from arvel.routing import URL, Route, Router

        Router.reset_singleton()
        monkeypatch.setenv("APP_URL", "https://example.com")
        monkeypatch.setenv("APP_KEY", "base64:" + "A" * 44)

        @Route.get("/verify/{user_id}", name="verify")
        async def _h(user_id: int) -> dict[str, Any]:
            return {}

        del _h  # registered via @Route.*; drop local binding

        sig_a = parse_qs(urlparse(URL.signed_route("verify", user_id=1)).query)["signature"][0]
        sig_b = parse_qs(urlparse(URL.signed_route("verify", user_id=2)).query)["signature"][0]
        assert sig_a != sig_b

    def test_signed_route_raises_for_unknown_route(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from arvel.routing import URL, RouteNotFoundError, Router

        Router.reset_singleton()
        monkeypatch.setenv("APP_URL", "https://example.com")
        monkeypatch.setenv("APP_KEY", "base64:" + "A" * 44)

        with pytest.raises(RouteNotFoundError):
            URL.signed_route("nonexistent")

    def test_signed_route_raises_when_app_key_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from arvel.routing import URL, Route, Router, RoutingError

        Router.reset_singleton()
        monkeypatch.setenv("APP_URL", "https://example.com")
        monkeypatch.delenv("APP_KEY", raising=False)

        @Route.get("/x", name="x")
        async def _h() -> dict[str, Any]:
            return {}

        del _h  # registered via @Route.*; drop local binding

        with pytest.raises(RoutingError, match="APP_KEY"):
            URL.signed_route("x")


# ─────────────────────────── Misc cross-cutting ──────────────────────────────


def test_routing_module_reexports_url_and_routing_error() -> None:
    """Both new public symbols should be importable from arvel.routing."""
    import arvel.routing as r

    assert hasattr(r, "URL")
    assert hasattr(r, "RoutingError")
    assert hasattr(r, "url")


def test_arvel_root_reexports_url_helper() -> None:
    """`url` is convenient enough that it should be importable from `arvel`."""
    import arvel

    assert hasattr(arvel, "url")


def test_signed_route_expires_at_naive_datetime_treated_as_utc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Passing a naive datetime should not silently use the local timezone."""
    from arvel.routing import URL, Route, Router

    Router.reset_singleton()
    monkeypatch.setenv("APP_URL", "https://example.com")
    monkeypatch.setenv("APP_KEY", "base64:" + "A" * 44)

    @Route.get("/x", name="x")
    async def _h() -> dict[str, Any]:
        return {}

    del _h  # registered via @Route.*; drop local binding

    naive = datetime.now().replace(tzinfo=None) + timedelta(hours=1)  # noqa: DTZ005
    with pytest.raises(ValueError, match="naive"):
        URL.signed_route("x", expires_at=naive)


def test_signed_route_works_with_expires_at_as_int_timestamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Accept Unix timestamp ints for convenience."""
    from arvel.routing import URL, Route, Router

    Router.reset_singleton()
    monkeypatch.setenv("APP_URL", "https://example.com")
    monkeypatch.setenv("APP_KEY", "base64:" + "A" * 44)

    @Route.get("/x", name="x")
    async def _h() -> dict[str, Any]:
        return {}

    del _h  # registered via @Route.*; drop local binding

    exp_ts = int(time.time()) + 3600
    signed = URL.signed_route("x", expires_at=exp_ts)
    qs = parse_qs(urlparse(signed).query)
    assert int(qs["expires"][0]) == exp_ts
