"""HTTP (doc 04) — Lens-A fix: redirect/exception flash must survive on a SERIALIZING session
store (cache/redis), not only the aliasing in-process dict. The session middleware saves on the
way out of its pipeline, before the kernel writes the flash; the kernel's after_response persist
captures it. Driven through the real kernel + TestClient."""

from __future__ import annotations

from typing import Any

from litestar.testing import TestClient

from arvel.cache import CacheManager
from arvel.http import HttpKernel
from arvel.http.flash import FlashBag
from arvel.http.middleware import (
    ShareErrorsFromSession,
    StartSession,
    ValidateCsrfToken,
    reset_sessions,
)
from arvel.http.redirect import Redirect, redirect
from arvel.kernel import Application, set_application
from arvel.routing import Router


def setup_function() -> None:
    reset_sessions()


def teardown_function() -> None:
    set_application(None)


def _cache_backed_client(router: Router) -> TestClient[Any]:
    app = Application()
    app.make("config").set("session", {"secure": False})
    app.singleton("router", lambda _app: router)
    set_application(app)
    kernel = HttpKernel(app)
    # web group with a cache (serializing) session store — the path the in-process dict masked
    session = StartSession(cache=CacheManager().driver("array"))
    kernel.middleware_group("web", [session, ShareErrorsFromSession, ValidateCsrfToken])
    router.apply_to(kernel)
    return TestClient(kernel.build())


def _seed(client: TestClient[Any], path: str) -> str:
    client.get(path)
    return client.cookies.get("XSRF-TOKEN", "")


def test_redirect_flash_survives_a_cache_backed_session() -> None:
    async def submit(request: Any) -> Redirect:
        return redirect("/form").with_errors({"email": ["is invalid"]})

    async def read_errors(request: Any) -> dict[str, Any]:
        return FlashBag(request.session).errors()

    router = Router()
    with router.group(group="web"):
        router.post("/form-submit", submit)
        router.get("/form", read_errors)
    with _cache_backed_client(router) as client:
        token = _seed(client, "/form")
        client.post("/form-submit", headers={"x-csrf-token": token}, follow_redirects=False)
        assert client.get("/form").json() == {"email": ["is invalid"]}
