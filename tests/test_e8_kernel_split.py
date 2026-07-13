"""E8/H12 — HttpKernel split: the response-conversion funnel and the binding resolver live in
their own intra-`http` units (`arvel.http.responder`, `arvel.http.binding`); the kernel no longer
defines them, only delegates. Test-first (spec: projects/arvel/specs/E8-kernel-throttle-url.md)."""

from __future__ import annotations

from typing import Any

import pytest
from litestar.testing import TestClient

from arvel.http import HttpKernel
from arvel.http.binding import BindingMissing, BindingResolver
from arvel.http.kernel import HttpKernel as _HttpKernelClass
from arvel.http.responder import apply_cookies, redirect_response, to_litestar_response, to_response
from arvel.routing import Router


def test_kernel_no_longer_defines_the_response_funnel() -> None:
    for name in ("_to_response", "_apply_cookies", "_redirect_response", "_to_litestar_response"):
        assert not hasattr(_HttpKernelClass, name), f"HttpKernel still defines {name}"


def test_kernel_no_longer_defines_the_binding_resolver() -> None:
    for name in ("_resolve_bindings", "_resolve_implicit_bindings", "_BindingMissing"):
        assert not hasattr(_HttpKernelClass, name), f"HttpKernel still defines {name}"


def test_responder_module_exposes_the_funnel_functions() -> None:
    # free functions (DR-0042) — no instantiation, no state
    assert callable(to_response)
    assert callable(apply_cookies)
    assert callable(redirect_response)
    assert callable(to_litestar_response)


def test_kernel_holds_a_binding_resolver_sharing_the_bindings_dict() -> None:
    kernel = HttpKernel()
    assert isinstance(kernel._bindings, BindingResolver)
    # the resolver must share the SAME dict object, not a copy — see the late-binding test below.
    assert kernel._bindings._bindings is kernel.bindings


async def test_binding_resolver_raises_binding_missing_on_a_miss() -> None:
    bindings: dict[str, Any] = {"user": lambda _key: None}
    resolver = BindingResolver(bindings)
    with pytest.raises(BindingMissing):
        await resolver.resolve_explicit({"user": "1"})


class _Widget:
    _store = {"1": "gizmo"}

    def __init__(self, name: str) -> None:
        self.name = name

    @classmethod
    async def find(cls, key: Any) -> _Widget | None:
        name = cls._store.get(str(key))
        return cls(name) if name is not None else None


async def _show_widget(request: Any, widget: _Widget) -> dict[str, Any]:
    return {"name": widget.name}


def test_binding_registered_after_kernel_construction_still_resolves() -> None:
    """The resolver must hold `kernel.bindings` BY REFERENCE: `router.apply_to(kernel)` mutates
    that dict (`kernel.bindings.update(...)`) strictly after `HttpKernel()` is constructed (and so
    after the `BindingResolver` inside it is built) — a snapshot would 404 here instead of
    resolving (top regression risk, DR-0042)."""
    router = Router()
    router.get("/widgets/{widget}", _show_widget)
    router.model("widget", _Widget)

    kernel = HttpKernel()  # BindingResolver built here, before the explicit binding registers
    router.apply_to(kernel)  # registers the explicit binding AFTER construction

    with TestClient(kernel.build()) as client:
        response = client.get("/widgets/1")
        assert response.status_code == 200
        assert response.json() == {"name": "gizmo"}
