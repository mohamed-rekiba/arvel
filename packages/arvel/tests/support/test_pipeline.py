"""FR-001-006: Pipeline[InT, OutT]."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest


async def test_pipeline_passes_value_through_middlewares() -> None:
    from arvel.support import Pipeline

    async def add_one(v: int, next_: Callable[[int], Awaitable[int]]) -> int:
        return await next_(v + 1)

    async def times_two(v: int, next_: Callable[[int], Awaitable[int]]) -> int:
        return await next_(v * 2)

    async def final(v: int) -> int:
        return v

    pipe: Pipeline[int, int] = Pipeline()
    result = await pipe.send(3).through([add_one, times_two]).then(final)
    assert result == (3 + 1) * 2  # 8


async def test_pipeline_short_circuits_on_exception() -> None:
    from arvel.support import Pipeline

    async def boom(_v: int, _next: Callable[[int], Awaitable[int]]) -> int:
        msg = "nope"
        raise RuntimeError(msg)

    async def final(v: int) -> int:
        return v

    pipe: Pipeline[int, int] = Pipeline()
    with pytest.raises(RuntimeError, match="nope"):
        await pipe.send(1).through([boom]).then(final)


async def test_pipeline_empty_middlewares_calls_final_directly() -> None:
    from arvel.support import Pipeline

    async def final(v: int) -> int:
        return v * 10

    pipe: Pipeline[int, int] = Pipeline()
    result = await pipe.send(5).through([]).then(final)
    assert result == 50
