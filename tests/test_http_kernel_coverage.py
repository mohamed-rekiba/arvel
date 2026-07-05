"""arvel.http.kernel.HttpKernel — verb registration, middleware-group customization, and the
best-effort handler introspection helpers (``_handler_io`` / ``_query_params``) that degrade to
``Any``/no-params on unintrospectable handlers rather than raising."""

from __future__ import annotations

from typing import Any

import msgspec

from arvel.http.kernel import HttpKernel


def test_put_and_patch_register_routes() -> None:
    kernel = HttpKernel()
    kernel.put("/p", lambda r: None)
    kernel.patch("/p", lambda r: None)
    methods = {tuple(route[0]) for route in kernel.routes()}
    assert ("PUT",) in methods
    assert ("PATCH",) in methods


def test_middleware_group_customization_is_fluent() -> None:
    kernel = HttpKernel()
    assert kernel.append_to_group("web", "a").prepend_to_group("web", "b") is kernel
    assert kernel.groups["web"] == ["b", "a"]
    kernel.middleware_group("admin", ["x"])
    assert kernel.groups["admin"] == ["x"]
    kernel.alias({"auth": object})
    assert kernel.resolve_middleware("auth") is object
    assert kernel.resolve_middleware("passthrough") == "passthrough"


class _Body(msgspec.Struct):
    name: str


def test_handler_io_detects_a_struct_body() -> None:
    def handler(request: Any, body: _Body) -> dict[str, Any]:
        return {}

    return_hint, body = HttpKernel._handler_io(handler)  # pyright: ignore[reportPrivateUsage]
    assert body == ("body", _Body)


def test_handler_io_degrades_on_unresolvable_hints() -> None:
    def handler(request: Any, x: "NopeUndefined") -> None:  # noqa: F821 - intentional bad ref
        return None

    return_hint, body = HttpKernel._handler_io(handler)  # pyright: ignore[reportPrivateUsage]
    assert body is None  # string annotations can't be a Struct subclass


def test_handler_io_on_an_uninspectable_object() -> None:
    # inspect.signature(object()) raises TypeError -> the (return_hint, None) fallback
    return_hint, body = HttpKernel._handler_io(object())  # pyright: ignore[reportPrivateUsage]
    assert body is None


def test_query_params_skips_request_body_path_and_varargs() -> None:
    def handler(request: Any, id: int, q: str = "x", *args: Any, **kwargs: Any) -> None:
        return None

    params = HttpKernel._query_params(  # pyright: ignore[reportPrivateUsage]
        handler, "/items/{id}", body_name=None
    )
    names = [p[0] for p in params]
    assert names == ["q"]  # request(first), id(path), *args/**kwargs all excluded


def test_query_params_degrades_on_unresolvable_hints() -> None:
    def handler(request: Any, x: "NopeUndefined") -> None:  # noqa: F821 - intentional bad ref
        return None

    assert (
        HttpKernel._query_params(handler, "/", body_name=None)  # pyright: ignore[reportPrivateUsage]
        == []
    )
