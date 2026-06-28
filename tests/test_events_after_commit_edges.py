"""Events depth (doc 11) — after-commit buffering edge cases: nesting, ordering, async isolation,
and immediate dispatch of non-after-commit events inside a transaction."""

from __future__ import annotations

import asyncio
from typing import Any

from arvel.events import Dispatcher, ShouldDispatchAfterCommit


class Shipped(ShouldDispatchAfterCommit):
    def __init__(self, n: int) -> None:
        self.n = n


class Logged:  # a plain (NOT after-commit) event
    def __init__(self, n: int) -> None:
        self.n = n


def _dispatcher(sink: list[Any]) -> Dispatcher:
    d = Dispatcher()
    d.listen(Shipped, lambda e: sink.append(("ship", e.n)))
    d.listen(Logged, lambda e: sink.append(("log", e.n)))
    return d


async def test_nested_transaction_flushes_only_on_outermost_commit() -> None:
    fired: list[Any] = []
    d = _dispatcher(fired)
    async with d.transaction():
        await d.dispatch(Shipped(1))
        async with d.transaction():  # inner reuses the outer buffer
            await d.dispatch(Shipped(2))
            assert fired == []  # inner "commit" must NOT flush
        assert fired == []  # still buffered after the inner block
    assert fired == [("ship", 1), ("ship", 2)]  # only the outermost commit flushes — in order


async def test_buffered_events_flush_in_fifo_order() -> None:
    fired: list[Any] = []
    d = _dispatcher(fired)
    async with d.transaction():
        for i in range(5):
            await d.dispatch(Shipped(i))
    assert fired == [("ship", i) for i in range(5)]


async def test_non_after_commit_event_fires_immediately_inside_transaction() -> None:
    fired: list[Any] = []
    d = _dispatcher(fired)
    async with d.transaction():
        await d.dispatch(Logged(1))  # plain event → immediate
        await d.dispatch(Shipped(9))  # after-commit → deferred
        assert fired == [("log", 1)]  # only the plain one fired so far
    assert fired == [("log", 1), ("ship", 9)]


async def test_concurrent_transactions_buffers_are_isolated() -> None:
    fired: list[Any] = []
    d = _dispatcher(fired)

    async def txn(tag: int, *, rollback: bool) -> None:
        try:
            async with d.transaction():
                await d.dispatch(Shipped(tag))
                await asyncio.sleep(0)  # interleave with the other transaction
                if rollback:
                    raise RuntimeError("rollback")
        except RuntimeError:
            pass

    # one commits, one rolls back, concurrently — buffers must not bleed across tasks
    await asyncio.gather(txn(1, rollback=False), txn(2, rollback=True))
    assert fired == [("ship", 1)]  # only the committed transaction's event fired
