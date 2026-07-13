"""HTTP-PARITY §4 — CSRF except-list: a URI glob pattern (class-level ``except_`` or configured
``session.csrf_except``) exempts a route from ``ValidateCsrfToken`` entirely; every other
state-changing route still needs a valid token."""

from __future__ import annotations

from typing import Any

from litestar.testing import TestClient

from arvel.http import HttpKernel
from arvel.http.middleware import ValidateCsrfToken
from arvel.kernel import Application, set_application
from arvel.routing import Router


def teardown_function() -> None:
    set_application(None)


async def _ok(request: Any) -> dict[str, bool]:
    return {"ok": True}


def _client(router: Router, *, csrf_except: list[str] | None = None) -> TestClient[Any]:
    app = Application()
    if csrf_except is not None:
        app.make("config").set("session", {"secure": False, "csrf_except": csrf_except})
    else:
        app.make("config").set("session", {"secure": False})
    set_application(app)
    kernel = HttpKernel(app).use_default_groups()
    router.apply_to(kernel)
    return TestClient(kernel.build())


def test_configured_except_path_posts_without_a_token() -> None:
    router = Router()
    with router.group(group="web"):
        router.post("/webhooks/stripe", _ok)
        router.post("/orders", _ok)
    with _client(router, csrf_except=["webhooks/*"]) as client:
        assert client.post("/webhooks/stripe").status_code == 201  # exempt — no token needed
        assert client.post("/orders").status_code == 419  # not exempt — still guarded


def test_subclass_except_is_merged_with_config() -> None:
    class AppCsrf(ValidateCsrfToken):
        except_ = ["health"]

    kernel = HttpKernel().use_default_groups()
    kernel.groups["web"] = [
        mw if mw is not ValidateCsrfToken else AppCsrf for mw in kernel.groups["web"]
    ]
    router = Router()
    with router.group(group="web"):
        router.post("/health", _ok)
        router.post("/other", _ok)
    router.apply_to(kernel)
    with TestClient(kernel.build()) as client:
        assert client.post("/health").status_code == 201
        assert client.post("/other").status_code == 419


def test_no_except_configured_everything_still_419s_without_a_token() -> None:
    router = Router()
    with router.group(group="web"):
        router.post("/orders", _ok)
    with _client(router) as client:
        assert client.post("/orders").status_code == 419
