"""HTTP (doc 04) — middleware group customization API: append/prepend/alias. Test-first."""

from __future__ import annotations

from typing import Any

from arvel.http import HttpKernel


class A:
    async def handle(self, request: Any, call_next: Any) -> Any:
        return await call_next(request)


class B:
    async def handle(self, request: Any, call_next: Any) -> Any:
        return await call_next(request)


class C:
    async def handle(self, request: Any, call_next: Any) -> Any:
        return await call_next(request)


def test_append_and_prepend_to_group() -> None:
    kernel = HttpKernel()
    kernel.append_to_group("web", A)
    kernel.append_to_group("web", B)
    kernel.prepend_to_group("web", C)
    assert kernel.groups["web"] == [C, A, B]


def test_middleware_group_defines_a_named_group() -> None:
    kernel = HttpKernel()
    kernel.middleware_group("admin", [A, B])
    assert kernel.groups["admin"] == [A, B]


def test_alias_resolution() -> None:
    kernel = HttpKernel()
    kernel.alias({"auth": A})
    assert kernel.resolve_middleware("auth") is A
    assert kernel.resolve_middleware(B) is B  # a non-alias reference passes through


async def test_grouped_middleware_runs_in_pipeline_order() -> None:
    kernel = HttpKernel()
    order: list[str] = []

    class Recorder:
        async def handle(self, request: Any, call_next: Any) -> Any:
            order.append("mw")
            return await call_next(request)

    kernel.append_to_group("web", Recorder)

    async def destination(request: Any) -> str:
        order.append("handler")
        return "ok"

    # instantiated once, like _dispatch, so a terminable middleware shares state across handle/terminate
    instances = [kernel._make(m) for m in kernel.groups["web"]]
    result = await kernel._run_pipeline(instances, object(), destination)
    assert result == "ok"
    assert order == ["mw", "handler"]


def test_use_default_groups_populates_web_and_api() -> None:
    from arvel.http.middleware import (
        ShareErrorsFromSession,
        StartSession,
        ThrottleRequests,
        ValidateCsrfToken,
    )

    kernel = HttpKernel().use_default_groups()
    assert kernel.groups["web"] == [StartSession, ShareErrorsFromSession, ValidateCsrfToken]
    assert kernel.groups["api"] == [ThrottleRequests]
