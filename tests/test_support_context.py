"""Context — an ambient, contextvars-backed key/value store (Laravel `Context` parity): CRUD,
stacks, hidden values (never in `all()`), `scope()` restoring the prior snapshot, the
dehydrate/hydrate round-trip (incl. hidden + callbacks), and per-task isolation."""

from __future__ import annotations

import asyncio

import pytest

from arvel.support import Context


async def test_add_get_has_forget() -> None:
    Context.add("tenant", "acme")
    assert Context.get("tenant") == "acme"
    assert Context.has("tenant") is True
    assert Context.get("missing", "default") == "default"
    Context.forget("tenant")
    assert Context.has("tenant") is False


async def test_all_returns_every_visible_key() -> None:
    Context.add("a", 1)
    Context.add("b", 2)
    assert Context.all() == {"a": 1, "b": 2}
    Context.forget("a")
    Context.forget("b")


async def test_push_pop_and_stack_contains() -> None:
    Context.push("trace", "start")
    Context.push("trace", "middle", "end")
    assert Context.stack_contains("trace", "middle") is True
    assert Context.stack_contains("trace", "nope") is False
    assert Context.pop("trace") == "end"
    assert Context.pop("trace") == "middle"
    assert Context.pop("trace") == "start"
    assert Context.pop("trace") is None  # empty stack pops to None, doesn't raise


async def test_increment_and_decrement() -> None:
    assert Context.increment("hits") == 1
    assert Context.increment("hits") == 2
    assert Context.increment("hits", 5) == 7
    assert Context.decrement("hits") == 6
    assert Context.decrement("hits", 3) == 3
    Context.forget("hits")


async def test_hidden_never_appears_in_all() -> None:
    Context.add_hidden("secret", "shh")
    assert Context.get_hidden("secret") == "shh"
    assert Context.has_hidden("secret") is True
    assert "secret" not in Context.all()
    assert Context.all_hidden() == {"secret": "shh"}


async def test_scope_restores_the_prior_snapshot_on_exit() -> None:
    Context.add("k", "outer")
    with Context.scope(k="inner", extra="new"):
        assert Context.get("k") == "inner"
        assert Context.get("extra") == "new"
    assert Context.get("k") == "outer"
    assert Context.has("extra") is False
    Context.forget("k")


async def test_scope_restores_after_an_exception() -> None:
    Context.add("k", "outer")
    with pytest.raises(ValueError, match="boom"), Context.scope(k="inner"):
        assert Context.get("k") == "inner"
        raise ValueError("boom")
    assert Context.get("k") == "outer"
    Context.forget("k")


async def test_dehydrate_hydrate_round_trip_includes_hidden() -> None:
    Context.add("visible-key", "v")
    Context.add_hidden("hidden-key", "h")
    payload = Context.dehydrate()

    Context.forget("visible-key")
    Context.hydrate({"visible": {}, "hidden": {}})
    assert Context.all() == {}
    assert Context.all_hidden() == {}

    Context.hydrate(payload)
    assert Context.get("visible-key") == "v"
    assert Context.get_hidden("hidden-key") == "h"
    Context.forget("visible-key")


async def test_dehydrating_and_hydrated_callbacks_fire() -> None:
    seen: list[str] = []
    Context.dehydrating(lambda _payload: seen.append("dehydrating"))
    Context.hydrated(lambda _payload: seen.append("hydrated"))

    payload = Context.dehydrate()
    Context.hydrate(payload)

    assert seen == ["dehydrating", "hydrated"]
    Context.flush_callbacks()  # don't leak registrations into later tests


async def test_context_is_isolated_across_concurrent_tasks() -> None:
    async def worker(tenant: str) -> str:
        Context.add("tenant", tenant)
        await asyncio.sleep(0)  # yield so tasks interleave across the await
        return Context.get("tenant")

    results = await asyncio.gather(worker("a"), worker("b"), worker("c"))
    assert results == ["a", "b", "c"]  # each task kept its own value, no cross-task bleed
