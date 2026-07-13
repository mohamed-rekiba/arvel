"""HTTP-PARITY §2 — the fluent ``redirect()`` value: route()/away()/back()/with_()/with_input()/
with_errors(), converted by the kernel into a 302 + session flash through the **real** session
middleware (``StartSession``) — reusing ``FlashBag``/``Request._flash_old_input``, not a second
flash implementation."""

from __future__ import annotations

from typing import Any

from litestar.testing import TestClient

from arvel.http import HttpKernel
from arvel.http.middleware import reset_sessions
from arvel.http.redirect import Redirect, redirect
from arvel.kernel import Application, set_application
from arvel.routing import Router


def setup_function() -> None:
    reset_sessions()  # the default session store is process-shared; isolate each test


def teardown_function() -> None:
    set_application(None)


def _client(router: Router) -> TestClient[Any]:
    # secure=False: TestClient talks plain http://testserver.local, and a browser cookie jar
    # (httpx's included) never re-sends a Secure cookie over a non-https origin — so the real
    # __Host-session round trip needs the dev-http config, same as any local (non-TLS) dev server.
    app = Application()
    app.make("config").set("session", {"secure": False})
    app.singleton("router", lambda _app: router)  # so redirect().route()/to_route() can resolve it
    set_application(app)
    kernel = HttpKernel(app).use_default_groups()
    router.apply_to(kernel)
    return TestClient(kernel.build())


def test_redirect_builder_is_fluent() -> None:
    r = redirect("/x").with_("status", "Saved!").with_errors({"email": ["bad"]})
    assert isinstance(r, Redirect)
    assert r.location == "/x"
    assert r.flash_data == {"status": "Saved!"}
    assert r.errors == {"email": ["bad"]}


def test_route_resolves_via_the_bound_router() -> None:
    router = Router()
    router.get("/thanks", lambda request: {"ok": True}, name="thanks")
    app = Application()
    app.singleton("router", lambda _app: router)
    set_application(app)
    try:
        assert redirect().route("thanks").location == "/thanks"
    finally:
        set_application(None)


def test_away_sets_the_location_with_no_origin_check() -> None:
    r = redirect().away("https://elsewhere.example/path")
    assert r.location == "https://elsewhere.example/path"


def _seed(client: TestClient[Any], path: str) -> str:
    """A safe-method GET through the web group: seeds the session + CSRF cookies, returns the
    CSRF token to send back on the next state-changing request."""
    client.get(path)
    return client.cookies.get("XSRF-TOKEN", "")


def test_redirect_route_and_flash_served_through_real_session_middleware() -> None:
    """redirect().route(...).with_('status', ...) → 302 to the resolved URL, flash readable
    on the very next request through the same (real) session cookie."""

    async def submit(request: Any) -> Redirect:
        return redirect().route("done").with_("status", "Saved!")

    async def read_flash(request: Any) -> dict[str, Any]:
        from arvel.http.flash import FlashBag

        return {"status": FlashBag(request.session).get("status")}

    router = Router()
    with router.group(group="web"):
        router.post("/submit", submit)
        router.get("/after", read_flash, name="done")
    with _client(router) as client:
        token = _seed(client, "/after")
        assert client.get("/after").json()["status"] is None  # nothing flashed yet

        submitted = client.post("/submit", headers={"x-csrf-token": token}, follow_redirects=False)
        assert submitted.status_code == 302
        assert submitted.headers["location"] == "/after"

        assert client.get("/after").json()["status"] == "Saved!"  # flashed, readable once
        assert client.get("/after").json()["status"] is None  # gone the request after


def test_back_redirects_to_referer_same_origin_only() -> None:
    async def go_back(request: Any) -> Redirect:
        return redirect().back(fallback="/home")

    router = Router()
    router.get("/back", go_back)
    kernel = HttpKernel()
    router.apply_to(kernel)
    with TestClient(kernel.build()) as client:
        same_origin = client.get(
            "/back", headers={"referer": "http://testserver.local/prior"}, follow_redirects=False
        )
        assert same_origin.status_code == 302
        assert same_origin.headers["location"] == "http://testserver.local/prior"

        cross_origin = client.get(
            "/back", headers={"referer": "https://evil.example/x"}, follow_redirects=False
        )
        assert cross_origin.headers["location"] == "/"  # cross-origin referer rejected → root

        no_referer = client.get("/back", follow_redirects=False)
        assert no_referer.headers["location"] == "/home"  # falls back


def test_with_errors_flashes_a_readable_error_bag() -> None:
    async def submit(request: Any) -> Redirect:
        return redirect("/form").with_errors({"email": ["is invalid"]})

    async def read_errors(request: Any) -> dict[str, Any]:
        from arvel.http.flash import FlashBag

        return FlashBag(request.session).errors()

    router = Router()
    with router.group(group="web"):
        router.post("/form-submit", submit)
        router.get("/form", read_errors)
    with _client(router) as client:
        token = _seed(client, "/form")
        # follow_redirects=False: httpx auto-following the 302 would itself be the read that
        # consumes the one-shot flash, before this test's own explicit read gets a turn.
        client.post("/form-submit", headers={"x-csrf-token": token}, follow_redirects=False)
        assert client.get("/form").json() == {"email": ["is invalid"]}


def test_with_input_flashes_old_input_readable_next_request() -> None:
    async def submit(request: Any) -> Redirect:
        return redirect("/form").with_input(except_=("secret_field",))

    async def read_old(request: Any) -> dict[str, Any]:
        from arvel.http.flash import FlashBag

        old = FlashBag(request.session).old()
        return {k: v for k, v in old.items() if k in ("email", "password", "secret_field")}

    router = Router()
    with router.group(group="web"):
        router.post("/form-submit", submit)
        router.get("/form", read_old)
    with _client(router) as client:
        token = _seed(client, "/form")
        client.post(
            "/form-submit",
            data={"email": "a@b.com", "password": "secret", "secret_field": "x", "_token": token},
            headers={"x-csrf-token": token},
            follow_redirects=False,
        )
        # password always excluded (Request._DONT_FLASH); secret_field excluded via except_
        assert client.get("/form").json() == {"email": "a@b.com"}
