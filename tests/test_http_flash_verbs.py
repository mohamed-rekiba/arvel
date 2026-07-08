"""HTTP (doc 09) — E7/H10: pull/increment survival within a request, and reflash()/keep()
extending flash lifetime across real requests, driven through the actual session middleware +
HTTP TestClient (not direct ``FlashBag`` construction)."""

from __future__ import annotations

from typing import Any

from litestar.testing import TestClient

from arvel.http import HttpKernel
from arvel.http.flash import FlashBag
from arvel.http.middleware import reset_sessions
from arvel.kernel import Application, set_application
from arvel.routing import Router


def setup_function() -> None:
    reset_sessions()  # the default session store is process-shared; isolate each test


def teardown_function() -> None:
    set_application(None)


def _client(router: Router) -> TestClient[Any]:
    # secure=False: TestClient talks plain http, so a real (non-__Host-) cookie round-trips —
    # same dev-http config as test_http_redirect.py.
    app = Application()
    app.make("config").set("session", {"secure": False})
    app.singleton("router", lambda _app: router)
    set_application(app)
    kernel = HttpKernel(app).use_default_groups()
    router.apply_to(kernel)
    return TestClient(kernel.build())


def test_pull_and_increment_through_a_live_request() -> None:
    async def handler(request: Any) -> dict[str, Any]:
        bag = FlashBag(request.session)
        request.session["stashed"] = "one-shot"
        return {
            "pulled": bag.pull("stashed"),
            "pulled_again": bag.pull("stashed", "gone"),
            "hit_1": bag.increment("hits"),
            "hit_2": bag.increment("hits"),
            "hit_3": bag.increment("hits", step=5),
        }

    router = Router()
    with router.group(group="web"):
        router.get("/verbs", handler)
    with _client(router) as client:
        body = client.get("/verbs").json()
    assert body == {
        "pulled": "one-shot",
        "pulled_again": "gone",
        "hit_1": 1,
        "hit_2": 2,
        "hit_3": 7,
    }


def test_reflash_keeps_all_flash_readable_one_extra_request() -> None:
    async def write(request: Any) -> dict[str, Any]:
        FlashBag(request.session).flash("a", "1").flash("b", "2")
        return {"ok": True}

    async def read_and_reflash(request: Any) -> dict[str, Any]:
        bag = FlashBag(request.session)
        seen = {"a": bag.get("a"), "b": bag.get("b")}
        bag.reflash()
        return seen

    async def read(request: Any) -> dict[str, Any]:
        bag = FlashBag(request.session)
        return {"a": bag.get("a"), "b": bag.get("b")}

    router = Router()
    with router.group(group="web"):
        router.get("/write", write)
        router.get("/read-reflash", read_and_reflash)
        router.get("/read", read)
    with _client(router) as client:
        client.get("/write")  # request A: flash a, b
        # request B: normal one-hop survival, then reflash() extends both one more hop
        assert client.get("/read-reflash").json() == {"a": "1", "b": "2"}
        # request C: still readable — reflash() extended past the ordinary one-request lifecycle
        assert client.get("/read").json() == {"a": "1", "b": "2"}
        # request D: not reflashed again in C — aged out on schedule
        assert client.get("/read").json() == {"a": None, "b": None}


def test_keep_extends_only_the_named_key_across_requests() -> None:
    async def write(request: Any) -> dict[str, Any]:
        bag = FlashBag(request.session)
        bag.flash("a", "1")
        bag.flash("b", "2")
        bag.flash("c", "3")
        return {"ok": True}

    async def read_and_keep_a(request: Any) -> dict[str, Any]:
        bag = FlashBag(request.session)
        seen = {"a": bag.get("a"), "b": bag.get("b"), "c": bag.get("c")}
        bag.keep(["a"])
        return seen

    async def read(request: Any) -> dict[str, Any]:
        bag = FlashBag(request.session)
        return {"a": bag.get("a"), "b": bag.get("b"), "c": bag.get("c")}

    router = Router()
    with router.group(group="web"):
        router.get("/write", write)
        router.get("/read-keep", read_and_keep_a)
        router.get("/read", read)
    with _client(router) as client:
        client.get("/write")  # request A: flash a, b, c
        # request B: all three still fresh from A; keep(["a"]) re-marks only "a"
        assert client.get("/read-keep").json() == {"a": "1", "b": "2", "c": "3"}
        # request C: only "a" survives — b/c weren't re-marked fresh in B
        assert client.get("/read").json() == {"a": "1", "b": None, "c": None}
