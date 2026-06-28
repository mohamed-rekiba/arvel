"""Phase F / It.8 — container parity & request scope: extend() decorates scoped bindings, forget()
rebuilds, flush() clears, resolvable() includes deferred, and a per-request scope shares scoped
instances across the request (S1)."""

from __future__ import annotations

from typing import Any

from litestar.testing import TestClient

from arvel.http import HttpKernel
from arvel.kernel import ServiceProvider
from arvel.kernel.application import Application
from arvel.kernel.container import Container
from arvel.routing import Router


def test_extend_decorates_a_scoped_binding() -> None:
    c = Container()

    class Svc:
        tag = "base"

    c.scoped("svc", lambda _c: Svc())

    def decorate(obj: Any, _c: Container) -> Any:
        obj.tag = "extended"
        return obj

    c.extend("svc", decorate)
    with c.scope():
        assert c.make("svc").tag == "extended"  # extender ran on the scoped instance


def test_forget_rebuilds_on_next_make() -> None:
    c = Container()
    c.singleton("svc", lambda _c: object())
    first = c.make("svc")
    assert c.make("svc") is first  # singleton shares
    c.forget("svc")
    assert c.make("svc") is not first  # forgotten → rebuilt (binding kept)


def test_flush_clears_bindings() -> None:
    c = Container()
    c.singleton("svc", lambda _c: object())
    assert c.bound("svc")
    c.flush()
    assert not c.bound("svc")


def test_application_flush_keeps_the_app_usable() -> None:
    app = Application()
    app.singleton("svc", lambda _c: object())
    app.flush()
    assert not app.bound("svc")  # user binding cleared
    assert app.make("app") is app  # self-bindings re-seeded → app still resolvable after flush
    assert app.make(Container) is app


def test_resolvable_includes_deferred_but_bound_does_not() -> None:
    class DeferredProvider(ServiceProvider):
        def register(self) -> None:
            self.app.singleton("svc", lambda _c: "D")

        def provides(self) -> list[Any]:
            return ["svc"]

    app = Application()
    app.register_deferred(DeferredProvider(app))
    assert app.bound("svc") is False  # not materialized yet (Laravel semantics, unchanged)
    assert app.resolvable("svc") is True  # but resolvable — a deferred provider will register it


def test_scoped_binding_is_shared_within_a_request() -> None:
    app = Application()

    class Svc: ...

    app.scoped("req_svc", lambda _c: Svc())

    async def handler(request: Any) -> dict[str, Any]:
        return {"same": app.make("req_svc") is app.make("req_svc")}

    router = Router()
    router.get("/", handler)
    kernel = HttpKernel(app)
    router.apply_to(kernel)
    with TestClient(kernel.build()) as client:
        assert client.get("/").json()["same"] is True  # S1: shared within the request scope
