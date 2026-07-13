"""H5 — ``HttpKernel.middleware_priority`` pins the relative run order of named middleware
regardless of where they were inserted (global/group/route); middleware absent from the list
keep their original relative insertion order (a stable sort keyed by priority-index-or-last)."""

from __future__ import annotations

from typing import Any

from litestar.testing import TestClient

from arvel.http import HttpKernel
from arvel.routing import Router

CALLS: list[str] = []


class _Mw:
    label = "?"

    async def handle(self, request: Any, call_next: Any) -> Any:
        CALLS.append(self.label)
        return await call_next(request)


class First(_Mw):
    label = "first"


class Second(_Mw):
    label = "second"


class Third(_Mw):
    label = "third"


async def _ok(request: Any) -> dict[str, str]:
    return {"ok": "1"}


def test_priority_reorders_regardless_of_insertion_order() -> None:
    """First/Second inserted in that order (route middleware) but the priority list pins
    Second before First — observed call order must follow the pin, not registration."""
    router = Router()
    router.get("/x", _ok).middleware(First, Second)
    kernel = HttpKernel()
    kernel.middleware_priority = [Second, First]
    router.apply_to(kernel)
    with TestClient(kernel.build()) as client:
        CALLS.clear()
        client.get("/x")
        assert CALLS == ["second", "first"]


def test_unlisted_middleware_keeps_relative_insertion_order() -> None:
    """Third isn't in the priority list; it keeps its original position relative to the
    pinned pair around it."""
    router = Router()
    router.get("/y", _ok).middleware(First, Third, Second)
    kernel = HttpKernel()
    kernel.middleware_priority = [Second, First]  # Third unlisted
    router.apply_to(kernel)
    with TestClient(kernel.build()) as client:
        CALLS.clear()
        client.get("/y")
        # pinned pair reorders to second, first; Third (unlisted) keeps its relative spot
        # among the unlisted, sorting stably after the pinned ones (index = len(priority))
        assert CALLS == ["second", "first", "third"]


def test_empty_priority_list_is_no_behavior_change() -> None:
    router = Router()
    router.get("/z", _ok).middleware(First, Second)
    kernel = HttpKernel()  # default middleware_priority == []
    router.apply_to(kernel)
    with TestClient(kernel.build()) as client:
        CALLS.clear()
        client.get("/z")
        assert CALLS == ["first", "second"]  # plain insertion order, unchanged
