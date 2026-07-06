"""HTTP-PARITY §3 — URL generation: ``url()``/``route()``/``to_route()``/``temporary_signed_route``,
``url().current()``/``.full()``/``.previous()``/``.query()``, and the documented clean error when
``.current()``/``.full()`` are called outside an active request."""

from __future__ import annotations

from typing import Any

import pytest
from litestar.testing import TestClient

from arvel.http import HttpKernel
from arvel.kernel import Application, set_application
from arvel.routing import Router, route, temporary_signed_route, to_route, url


def teardown_function() -> None:
    set_application(None)


def _app_with_router(router: Router, *, base_url: str | None = None) -> Application:
    app = Application()
    if base_url is not None:
        app.make("config").set("app", {"url": base_url})
    app.singleton("router", lambda _app: router)
    set_application(app)
    return app


def test_url_with_path_is_absolute_from_config_app_url() -> None:
    _app_with_router(Router(), base_url="https://example.test")
    assert url("/p") == "https://example.test/p"
    assert url("p") == "https://example.test/p"  # leading slash normalized


def test_url_with_no_path_returns_the_generator_itself() -> None:
    _app_with_router(Router(), base_url="https://example.test")
    generator = url()
    assert generator is url  # the same singleton, so .current()/.full() chain off it


def test_url_degrades_to_bare_path_with_no_app_url_configured() -> None:
    assert url("/p") == "/p"


def test_route_is_absolute_by_default_and_path_only_when_opted_out() -> None:
    router = Router()
    router.get("/items/{item_id}", lambda request, item_id: {"id": item_id}, name="items.show")
    _app_with_router(router, base_url="https://example.test")
    assert route("items.show", item_id=7) == "https://example.test/items/7"
    assert route("items.show", item_id=7, absolute=False) == "/items/7"


def test_route_fills_a_route_key_bound_param() -> None:
    # the inline {post:slug} route-key form must be substituted, not left in the path with the
    # value dumped into the query string.
    router = Router()
    router.get("/posts/{post:slug}", lambda request, post: {"post": post}, name="posts.show")
    _app_with_router(router)
    assert route("posts.show", post="my-slug", absolute=False) == "/posts/my-slug"


def test_route_percent_encodes_path_segment_values() -> None:
    router = Router()
    router.get("/users/{id}", lambda request, id: {"id": id}, name="users.show")
    _app_with_router(router)
    assert route("users.show", id="a b/c", absolute=False) == "/users/a%20b%2Fc"


def test_to_route_is_redirect_dot_route_sugar() -> None:
    router = Router()
    router.get("/thanks", lambda request: {"ok": True}, name="thanks")
    _app_with_router(router)
    r = to_route("thanks")
    assert r.location == "/thanks"


def test_temporary_signed_route_validates_before_expiry_and_is_tamper_evident() -> None:
    router = Router()
    router.get("/unsub/{uid}", lambda request, uid: {"ok": True}, name="unsub")
    app = Application()
    app.make("config").set("app", {"key": "test-signing-key"})
    app.singleton("router", lambda _app: router)
    set_application(app)
    signed = temporary_signed_route("unsub", 3600, uid=7)
    assert router.has_valid_signature(signed)
    assert not router.has_valid_signature(signed + "x")  # tampered


def test_current_full_previous_via_a_real_request() -> None:
    async def show(request: Any) -> dict[str, Any]:
        return {"current": url.current(), "full": url.full(), "previous": url.previous("/x")}

    kernel = HttpKernel()
    kernel.get("/report", show)
    with TestClient(kernel.build()) as client:
        body = client.get("/report?a=1", headers={"referer": "http://testserver.local/from"}).json()
    assert body["current"].endswith("/report")
    assert body["full"].endswith("/report?a=1")
    assert body["previous"] == "http://testserver.local/from"


def test_previous_degrades_to_fallback_with_no_referer() -> None:
    async def show(request: Any) -> dict[str, Any]:
        return {"previous": url.previous("/fallback")}

    kernel = HttpKernel()
    kernel.get("/x", show)
    with TestClient(kernel.build()) as client:
        assert client.get("/x").json()["previous"] == "/fallback"


def test_url_current_outside_a_request_raises_a_clean_error() -> None:
    with pytest.raises(RuntimeError, match="active request"):
        url.current()


def test_url_query_appends_encoded_params() -> None:
    assert url.query("/search", {"q": "a b"}) == "/search?q=a+b"
