"""3.4 routing-parity-fill: optional `{x?}` route params, `.where()` regex constraints,
`.missing(callback)` on model binding, per-route `.without_middleware()`, and generic
parameterized middleware aliases (`alias:arg1,arg2`). Test-first."""

from __future__ import annotations

from typing import Any

from litestar.testing import TestClient

from arvel.http import HttpKernel
from arvel.routing import Router


async def _ok(request: Any) -> dict[str, str]:
    return {"ok": "1"}


# --- optional route params ---------------------------------------------------------------


async def _greet(request: Any, name: str = "world") -> dict[str, str]:
    return {"hello": name}


def test_optional_param_compiles_to_two_paths() -> None:
    paths, fields = HttpKernel._compile_path("/greet/{name?}")
    assert paths == ["/greet/{name:str}", "/greet"]
    assert fields == {}


def test_optional_param_matches_with_and_without_the_segment() -> None:
    router = Router()
    router.get("/greet/{name?}", _greet)
    kernel = HttpKernel()
    router.apply_to(kernel)
    with TestClient(kernel.build()) as client:
        assert client.get("/greet/ada").json() == {"hello": "ada"}
        assert client.get("/greet").json() == {"hello": "world"}  # handler default applies


def test_multiple_trailing_optional_params() -> None:
    async def handler(request: Any, a: str = "A", b: str = "B") -> dict[str, str]:
        return {"a": a, "b": b}

    router = Router()
    router.get("/multi/{a?}/{b?}", handler)
    kernel = HttpKernel()
    router.apply_to(kernel)
    with TestClient(kernel.build()) as client:
        assert client.get("/multi/1/2").json() == {"a": "1", "b": "2"}
        assert client.get("/multi/1").json() == {"a": "1", "b": "B"}
        assert client.get("/multi").json() == {"a": "A", "b": "B"}


# --- where() regex constraints ------------------------------------------------------------


async def _show_number(request: Any, id: str) -> dict[str, str]:
    return {"id": id}


def test_where_constraint_matches() -> None:
    router = Router()
    router.get("/numbers/{id}", _show_number).where("id", r"\d+")
    kernel = HttpKernel()
    router.apply_to(kernel)
    with TestClient(kernel.build()) as client:
        assert client.get("/numbers/42").json() == {"id": "42"}


def test_where_constraint_mismatch_is_404_not_500() -> None:
    router = Router()
    router.get("/numbers/{id}", _show_number).where("id", r"\d+")
    kernel = HttpKernel()
    router.apply_to(kernel)
    with TestClient(kernel.build()) as client:
        response = client.get("/numbers/abc")
        assert response.status_code == 404


# --- missing(callback) on model binding ----------------------------------------------------


class _Widget:
    _rows = {"1": "Gadget"}

    def __init__(self, name: str) -> None:
        self.name = name

    @classmethod
    async def resolve_route_binding(cls, value: Any, field: str | None = None) -> _Widget | None:
        name = cls._rows.get(str(value))
        return cls(name) if name is not None else None


async def _show_widget(request: Any, widget: _Widget) -> dict[str, str]:
    return {"name": widget.name}


def test_missing_callback_customizes_the_404_response() -> None:
    from arvel.http.response import Response

    def custom_missing(request: Any) -> Any:
        return Response({"custom": "not here"}, status=404)

    router = Router()
    router.get("/widgets/{widget}", _show_widget).missing(custom_missing)
    kernel = HttpKernel()
    router.apply_to(kernel)
    with TestClient(kernel.build()) as client:
        response = client.get("/widgets/999")
        assert response.status_code == 404
        assert response.json() == {"custom": "not here"}
        assert client.get("/widgets/1").json() == {"name": "Gadget"}


def test_no_missing_callback_falls_back_to_default_404() -> None:
    router = Router()
    router.get("/widgets/{widget}", _show_widget)
    kernel = HttpKernel()
    router.apply_to(kernel)
    with TestClient(kernel.build()) as client:
        assert client.get("/widgets/999").status_code == 404


# --- per-route middleware exclusion --------------------------------------------------------

SEEN: list[str] = []


class _Tag:
    async def handle(self, request: Any, call_next: Any) -> Any:
        SEEN.append("tagged")
        return await call_next(request)


def test_without_middleware_excludes_a_group_middleware() -> None:
    SEEN.clear()
    router = Router()
    with router.group(group="tagged"):
        router.get("/plain", _ok)
        router.get("/exempt", _ok).without_middleware(_Tag)
    kernel = HttpKernel()
    kernel.middleware_group("tagged", [_Tag])
    router.apply_to(kernel)
    with TestClient(kernel.build()) as client:
        client.get("/plain")
        assert SEEN == ["tagged"]
        SEEN.clear()
        client.get("/exempt")
        assert SEEN == []


# --- generic parameterized middleware aliases ----------------------------------------------


class _Echo:
    def __init__(self, *args: str) -> None:
        self.args = args

    async def handle(self, request: Any, call_next: Any) -> Any:
        SEEN.append(",".join(self.args))
        return await call_next(request)


def test_parameterized_alias_reaches_the_constructor() -> None:
    SEEN.clear()
    kernel = HttpKernel()
    kernel.alias({"echo": _Echo})
    kernel.add_route(["GET"], "/echoed", _ok, middleware=["echo:one,two"])
    with TestClient(kernel.build()) as client:
        client.get("/echoed")
    assert SEEN == ["one,two"]


def test_resolve_middleware_plain_alias_still_works() -> None:
    kernel = HttpKernel()
    kernel.alias({"echo": _Echo})
    resolved = kernel.resolve_middleware("echo")
    assert resolved is _Echo


def test_resolve_middleware_throttle_still_special_cased() -> None:
    from arvel.http.middleware import ThrottleRequests

    kernel = HttpKernel()
    resolved = kernel.resolve_middleware("throttle:api")
    assert isinstance(resolved, ThrottleRequests)


def test_throttle_name_form_wins_over_a_registered_throttle_alias() -> None:
    """Both are documented: `kernel.alias({"throttle": ThrottleRequests})` and the reserved
    `throttle:<name>` named-limiter form. The generic alias-with-args branch must not swallow
    the reserved form — it constructed ThrottleRequests("uploads"), passing the limiter NAME as
    the positional max_attempts and 500ing every request at count-compare time."""
    from arvel.http import HttpKernel
    from arvel.http.middleware import ThrottleRequests

    kernel = HttpKernel()
    kernel.alias({"throttle": ThrottleRequests})
    resolved = kernel.resolve_middleware("throttle:uploads")
    assert isinstance(resolved, ThrottleRequests)
    assert resolved._limiter_name == "uploads"
    assert resolved.max_attempts != "uploads"  # never the name as a count
