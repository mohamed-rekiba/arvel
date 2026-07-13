"""E8/H16 — URL-join consolidation: `arvel.support.helpers.app_url` is the ONE joiner;
`routing._absolute` and `views._url` are thin delegators, and `_UrlGenerator`/`route()` reach it
through `_absolute`. All call sites must produce IDENTICAL output for the same input, across a
configured `app.url`, no configured `app.url`, a path with/without a leading slash, and the empty
path (spec: projects/arvel/specs/E8-kernel-throttle-url.md)."""

from __future__ import annotations

from typing import Any

import pytest
from litestar.testing import TestClient

from arvel.http import HttpKernel
from arvel.kernel import Application, set_application
from arvel.routing import Router, route, url
from arvel.support.helpers import app_url
from arvel.views import _url as views_url


def teardown_function() -> None:
    set_application(None)


@pytest.mark.parametrize("path", ["/x", "x", "", "/", "a/b", "/a/b/"])
@pytest.mark.parametrize(
    "base_url", [None, "https://example.test", "https://example.test/", ""], ids=repr
)
def test_all_three_joiners_agree(base_url: str | None, path: str) -> None:
    app = Application()
    if base_url is not None:
        app.make("config").set("app", {"url": base_url})
    set_application(app)

    expected = app_url(path)
    assert url(path) == expected
    assert views_url(path) == expected


def test_all_three_joiners_agree_with_no_application_at_all() -> None:
    set_application(None)
    for path in ("/x", "x", "", "/"):
        expected = app_url(path)
        assert url(path) == expected
        assert views_url(path) == expected


def test_route_absolute_reaches_the_same_joiner() -> None:
    router = Router()
    router.get("/items/{item_id}", lambda request, item_id: {"id": item_id}, name="items.show")
    app = Application()
    app.make("config").set("app", {"url": "https://example.test"})
    app.singleton("router", lambda _app: router)
    set_application(app)

    assert route("items.show", item_id=7) == app_url("/items/7")


def test_current_route_through_a_real_request_matches_app_url() -> None:
    async def show(request: Any) -> dict[str, Any]:
        return {"current": url.current()}

    app = Application()
    app.make("config").set("app", {"url": "https://example.test"})
    set_application(app)

    kernel = HttpKernel(app=app)
    kernel.get("/report", show)
    with TestClient(kernel.build()) as client:
        body = client.get("/report").json()
    assert body["current"] == app_url("/report")
