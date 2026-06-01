"""request-scoped Context, defer(), and Concurrency."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest
from arvel.context import (
    Concurrency,
    Context,
    ContextMiddleware,
    ContextRepository,
    DeferredTaskMiddleware,
    bind_repository,
    defer,
    reset_repository,
)
from starlette.types import Receive, Scope, Send


@pytest.fixture(autouse=True)
def fresh_context() -> Iterator[ContextRepository]:
    repo = ContextRepository()
    token = bind_repository(repo)
    try:
        yield repo
    finally:
        reset_repository(token)


async def _receive() -> dict[str, object]:
    return {"type": "http.request"}


async def _send(_message: object) -> None:
    return None


def test_add_and_get() -> None:
    Context.add("request_id", "abc-123")
    assert Context.get("request_id") == "abc-123"
    assert Context.get("missing", "fallback") == "fallback"


def test_hidden_keys_absent_from_all() -> None:
    Context.add("tenant_id", "acme")
    Context.add_hidden("db_password", "s3cret")

    assert Context.all() == {"tenant_id": "acme"}
    assert Context.get_hidden("db_password") == "s3cret"
    assert "db_password" not in Context.all()


def test_push_accumulates_a_list() -> None:
    Context.push("breadcrumbs", "one")
    Context.push("breadcrumbs", "two", "three")
    assert Context.get("breadcrumbs") == ["one", "two", "three"]


def test_dehydrate_excludes_hidden() -> None:
    Context.add("user_id", "42")
    Context.add_hidden("token", "nope")

    payload = Context.dehydrate()
    assert payload == {"user_id": "42"}
    assert "token" not in payload


def test_hydrate_restores_visible_keys() -> None:
    Context.hydrate({"user_id": "42", "tenant_id": "acme"})
    assert Context.get("user_id") == "42"
    assert Context.get("tenant_id") == "acme"


def test_forget_and_flush() -> None:
    Context.add("a", 1)
    Context.add_hidden("b", 2)
    Context.forget("a")
    assert not Context.has("a")
    Context.flush()
    assert Context.is_empty()


async def test_concurrency_run_returns_results_in_order() -> None:
    async def slow() -> str:
        await asyncio.sleep(0.01)
        return "slow"

    async def fast() -> str:
        return "fast"

    results = await Concurrency.run([slow, fast])
    assert results == ["slow", "fast"]


async def test_concurrency_run_propagates_exceptions() -> None:
    async def ok() -> int:
        return 1

    async def boom() -> int:
        raise ValueError("kaboom")

    with pytest.raises(ValueError, match="kaboom"):
        await Concurrency.run([ok, boom])


async def test_context_isolated_per_task() -> None:
    Context.add("shared", "parent")

    async def child() -> object:
        repo = ContextRepository()
        token = bind_repository(repo)
        try:
            return Context.get("shared")
        finally:
            reset_repository(token)

    assert await child() is None
    assert Context.get("shared") == "parent"


async def test_context_middleware_flushes_between_requests() -> None:
    leaked: list[object] = []

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        leaked.append(Context.get("per_request"))
        Context.add("per_request", "value")

    middleware = ContextMiddleware(app)
    scope: Scope = {"type": "http", "path": "/"}

    await middleware(scope, _receive, _send)
    await middleware(scope, _receive, _send)

    # Second request must not see the first request's key.
    assert leaked == [None, None]


async def test_deferred_tasks_run_after_response_and_isolate_failures() -> None:
    ran: list[str] = []

    def first_fails() -> None:
        ran.append("first-but-fails")
        raise RuntimeError("boom")

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        defer(first_fails)
        defer(lambda: ran.append("second"))

    outer = ContextMiddleware(DeferredTaskMiddleware(app))
    scope: Scope = {"type": "http", "path": "/"}

    await outer(scope, _receive, _send)

    # Both ran even though the first raised; the error was logged, not propagated.
    assert ran == ["first-but-fails", "second"]
