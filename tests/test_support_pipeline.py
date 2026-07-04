"""Pipeline — onion/middleware semantics (Laravel `Pipeline` parity): each pipe receives
`(value, next)` and decides whether/how to call `next`. Covers onion order, short-circuiting,
`via()` for object pipes, sync/async mixing, and the 1-arg transform sugar."""

from __future__ import annotations

from typing import Any

from arvel.support import Pipeline


async def test_onion_order_wraps_before_and_after_the_destination() -> None:
    events: list[str] = []

    async def a(value: int, nxt: Any) -> int:
        events.append("a-before")
        result = await nxt(value)
        events.append("a-after")
        return result

    async def b(value: int, nxt: Any) -> int:
        events.append("b-before")
        result = await nxt(value)
        events.append("b-after")
        return result

    async def dest(value: int) -> int:
        events.append("dest")
        return value + 1

    result = await Pipeline().send(1).through([a, b]).then(dest)

    assert result == 2
    assert events == ["a-before", "b-before", "dest", "b-after", "a-after"]


async def test_each_pipe_receives_the_prior_result() -> None:
    def add_one(value: int, nxt: Any) -> Any:
        return nxt(value + 1)

    def double(value: int, nxt: Any) -> Any:
        return nxt(value * 2)

    result = await Pipeline().send(3).through([add_one, double]).then(lambda v: v)
    assert result == 8  # (3 + 1) * 2


async def test_short_circuit_pipe_never_calls_next() -> None:
    calls: list[str] = []

    def gatekeeper(value: int, nxt: Any) -> str:
        calls.append("gatekeeper")
        return "blocked"  # never calls nxt

    def unreachable(value: int, nxt: Any) -> Any:
        calls.append("unreachable")
        return nxt(value)

    def dest(value: int) -> int:
        calls.append("dest")
        return value

    result = await Pipeline().send(1).through([gatekeeper, unreachable]).then(dest)

    assert result == "blocked"
    assert calls == ["gatekeeper"]


async def test_then_return_yields_the_piped_value_with_no_destination() -> None:
    def increment(value: int, nxt: Any) -> Any:
        return nxt(value + 1)

    result = await Pipeline().send(1).through([increment, increment]).then_return()
    assert result == 3


async def test_via_names_the_object_pipe_method() -> None:
    class UppercasePipe:
        async def process(self, value: str, nxt: Any) -> Any:
            return await nxt(value.upper())

    result = await Pipeline().send("hi").through([UppercasePipe()]).via("process").then(lambda v: v)
    assert result == "HI"


async def test_via_defaults_to_handle() -> None:
    class ExclaimPipe:
        def handle(self, value: str, nxt: Any) -> Any:
            return nxt(value + "!")

    result = await Pipeline().send("hi").through([ExclaimPipe()]).then(lambda v: v)
    assert result == "hi!"


async def test_async_and_sync_pipes_mix_freely() -> None:
    events: list[str] = []

    async def async_pipe(value: int, nxt: Any) -> Any:
        events.append("async-before")
        result = await nxt(value)
        events.append("async-after")
        return result

    def sync_pipe(value: int, nxt: Any) -> Any:
        events.append("sync-before")
        return nxt(value)  # returns the awaitable chain untouched

    async def dest(value: int) -> int:
        events.append("dest")
        return value

    result = await Pipeline().send(1).through([async_pipe, sync_pipe]).then(dest)

    assert result == 1
    assert events == ["async-before", "sync-before", "dest", "async-after"]


async def test_one_arg_callable_is_auto_adapted_as_a_transform() -> None:
    def to_upper(value: str) -> str:
        return value.upper()

    async def trim(value: str) -> str:
        return value.strip()

    result = await Pipeline().send("  hi  ").through([trim, to_upper]).then_return()
    assert result == "HI"


async def test_empty_pipeline_calls_destination_directly() -> None:
    result = await Pipeline().send(5).through([]).then(lambda v: v * 2)
    assert result == 10
