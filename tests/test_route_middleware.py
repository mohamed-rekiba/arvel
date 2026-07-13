"""Router/HttpKernel middleware wiring: group + per-route middleware run in order
global -> group -> route (web=session+CSRF, api=throttle)."""

from __future__ import annotations

from typing import Any

from litestar.testing import TestClient

from arvel.http import HttpKernel
from arvel.http.middleware import EncryptCookies
from arvel.routing import Router

CALLS: list[str] = []


class _Mw:
    label = "?"

    async def handle(self, request: Any, call_next: Any) -> Any:
        CALLS.append(self.label)
        return await call_next(request)


class GlobalMw(_Mw):
    label = "global"


class WebMw(_Mw):
    label = "web"


class RouteMw(_Mw):
    label = "route"


class OuterMw(_Mw):
    label = "outer"


class InnerMw(_Mw):
    label = "inner"


async def _ok(request: Any) -> dict[str, str]:
    return {"ok": "1"}


def _client(router: Router, **groups: list[Any]) -> TestClient[Any]:
    kernel = HttpKernel()
    for name, stack in groups.items():
        kernel.middleware_group(name, stack)
    router.apply_to(kernel)
    return TestClient(kernel.build())


def test_group_label_runs_group_middleware() -> None:
    router = Router()
    with router.group(group="web"):
        router.get("/in", _ok)
    router.get("/out", _ok)
    with _client(router, web=[WebMw]) as client:
        CALLS.clear()
        client.get("/in")
        assert CALLS == ["web"]
        CALLS.clear()
        client.get("/out")
        assert CALLS == []


def test_per_route_middleware() -> None:
    router = Router()
    router.get("/a", _ok).middleware(RouteMw)
    router.get("/b", _ok)
    with _client(router) as client:
        CALLS.clear()
        client.get("/a")
        assert CALLS == ["route"]
        CALLS.clear()
        client.get("/b")
        assert CALLS == []


def test_group_middleware_via_context_manager() -> None:
    router = Router()
    with router.group(middleware=[WebMw]):
        router.get("/in", _ok)
    router.get("/out", _ok)
    with _client(router) as client:
        CALLS.clear()
        client.get("/in")
        assert CALLS == ["web"]
        CALLS.clear()
        client.get("/out")
        assert CALLS == []


def test_nested_groups_compose_and_restore() -> None:
    router = Router()
    with router.group(middleware=[OuterMw]):
        router.get("/outer", _ok)
        with router.group(middleware=[InnerMw]):
            router.get("/inner", _ok)
        router.get("/after", _ok)
    router.get("/top", _ok)
    with _client(router) as client:
        CALLS.clear()
        client.get("/inner")
        assert CALLS == ["outer", "inner"]
        CALLS.clear()
        client.get("/outer")
        assert CALLS == ["outer"]
        CALLS.clear()
        client.get("/after")  # sibling after inner block: inner must NOT leak
        assert CALLS == ["outer"]
        CALLS.clear()
        client.get("/top")  # outside all groups
        assert CALLS == []


def test_pipeline_order_global_group_route() -> None:
    router = Router()
    with router.group(group="web"):
        router.get("/x", _ok).middleware(RouteMw)
    kernel = HttpKernel()
    kernel.global_middleware.append(GlobalMw)
    kernel.middleware_group("web", [WebMw])
    router.apply_to(kernel)
    with TestClient(kernel.build()) as client:
        CALLS.clear()
        client.get("/x")
        assert CALLS == ["global", "web", "route"]


def test_apply_to_threads_group_and_middleware() -> None:
    router = Router()
    with router.group(group="api", middleware=[RouteMw]):
        router.get("/u", _ok)
    kernel = HttpKernel()
    router.apply_to(kernel)
    # the kernel route entry carries the group + middleware (no silent drop)
    entry = next(r for r in kernel.routes() if r[1] == "/u")
    assert entry[3] == "api"  # group slot
    assert RouteMw in entry[4]  # middleware slot


def test_as_asgi_wires_default_groups(monkeypatch: Any) -> None:
    import arvel.http as http
    from arvel.kernel.application import Application

    called = {"v": False}
    original = http.HttpKernel.use_default_groups

    def spy(self: Any) -> Any:
        called["v"] = True
        return original(self)

    monkeypatch.setattr(http.HttpKernel, "use_default_groups", spy)
    app = Application.configure().create()
    app.as_asgi()
    assert called["v"] is True


def test_web_group_runs_real_csrf_end_to_end() -> None:
    """A web-group route actually runs the real default web stack (StartSession +
    ValidateCsrfToken): a state-changing POST with no CSRF token is rejected 419."""

    async def _create(request: Any) -> dict[str, str]:
        return {"ok": "1"}

    router = Router()
    with router.group(group="web"):
        router.post("/posts", _create)
    kernel = HttpKernel().use_default_groups()
    router.apply_to(kernel)
    with TestClient(kernel.build()) as client:
        assert client.post("/posts").status_code == 419  # CSRF middleware reached the route
        assert client.get("/posts").status_code in (
            200,
            405,
        )  # safe method exempt (or no GET route)


def test_use_default_groups_puts_encrypt_cookies_first_in_web() -> None:
    """H7: EncryptCookies must run before StartSession/ValidateCsrfToken so their cookies go
    through its codec."""
    kernel = HttpKernel().use_default_groups()
    assert kernel.groups["web"][0] is EncryptCookies


def test_no_group_no_middleware_is_global_only() -> None:
    router = Router()
    router.get("/plain", _ok)
    kernel = HttpKernel()
    kernel.global_middleware.append(GlobalMw)
    router.apply_to(kernel)
    with TestClient(kernel.build()) as client:
        CALLS.clear()
        assert client.get("/plain").json() == {"ok": "1"}
        assert CALLS == ["global"]
