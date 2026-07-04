"""HTTP-PARITY §4 — invokable controllers (a class with ``__call__``, container-instantiated at
dispatch) and ``Controller.middleware()``/``ControllerMiddleware(only=, except_=)`` honored by
``Router.resource``."""

from __future__ import annotations

from typing import Any

from litestar.testing import TestClient

from arvel.http import HttpKernel
from arvel.kernel import Application, set_application
from arvel.routing import Controller, ControllerMiddleware, Router


def teardown_function() -> None:
    set_application(None)


# --- invokable controller -----------------------------------------------------------------


class Greet:
    """A class with ``__call__`` — no base class needed; route-bindable directly."""

    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, request: Any, name: str) -> dict[str, Any]:
        self.calls += 1
        return {"hello": name}


def test_invokable_controller_is_routed() -> None:
    kernel = HttpKernel()
    kernel.get("/greet/{name}", Greet)
    with TestClient(kernel.build()) as client:
        resp = client.get("/greet/ada")
    assert resp.status_code == 200
    assert resp.json() == {"hello": "ada"}


def test_invokable_controller_is_instantiated_via_the_container() -> None:
    """Each request gets its own instance (container-resolved), matching how the kernel already
    instantiates middleware classes via ``app.make`` — not one shared singleton."""
    app = Application()
    set_application(app)
    router = Router()
    router.get("/greet/{name}", Greet)
    kernel = HttpKernel(app)
    router.apply_to(kernel)
    with TestClient(kernel.build()) as client:
        assert client.get("/greet/ada").json() == {"hello": "ada"}
        assert client.get("/greet/bo").json() == {"hello": "bo"}


# --- controller middleware only()/except() --------------------------------------------------


SEEN: list[str] = []


class TagMiddleware:
    async def handle(self, request: Any, call_next: Any) -> Any:
        SEEN.append("tagged")
        return await call_next(request)


class PostController(Controller):
    @classmethod
    def middleware(cls) -> list[ControllerMiddleware]:
        return [ControllerMiddleware(TagMiddleware, only=("show",))]

    async def index(self, request: Any) -> dict[str, Any]:
        return {"action": "index"}

    async def show(self, request: Any, post: str) -> dict[str, Any]:
        return {"action": "show", "id": post}


def test_controller_middleware_only_applies_to_the_named_action() -> None:
    router = Router()
    router.resource("posts", PostController)
    kernel = HttpKernel()
    router.apply_to(kernel)
    with TestClient(kernel.build()) as client:
        SEEN.clear()
        client.get("/posts")  # index — not in `only`
        assert SEEN == []
        client.get("/posts/5")  # show — in `only`
        assert SEEN == ["tagged"]


class WidgetController(Controller):
    @classmethod
    def middleware(cls) -> list[ControllerMiddleware]:
        return [ControllerMiddleware(TagMiddleware, except_=("index",))]

    async def index(self, request: Any) -> dict[str, Any]:
        return {"action": "index"}

    async def show(self, request: Any, widget: str) -> dict[str, Any]:
        return {"action": "show", "id": widget}


def test_controller_middleware_except_skips_the_named_action() -> None:
    router = Router()
    router.resource("widgets", WidgetController)
    kernel = HttpKernel()
    router.apply_to(kernel)
    with TestClient(kernel.build()) as client:
        SEEN.clear()
        client.get("/widgets")  # index — excepted
        assert SEEN == []
        client.get("/widgets/9")  # show — not excepted
        assert SEEN == ["tagged"]


def test_controller_middleware_applies_to_call() -> None:
    entry = ControllerMiddleware("auth", only=("show", "update"))
    assert entry.applies_to("show") is True
    assert entry.applies_to("index") is False

    excepted = ControllerMiddleware("auth", except_=("destroy",))
    assert excepted.applies_to("destroy") is False
    assert excepted.applies_to("show") is True


def test_default_controller_middleware_is_empty() -> None:
    class Plain(Controller):
        async def index(self, request: Any) -> dict[str, Any]:
            return {}

    assert Plain.middleware() == []
