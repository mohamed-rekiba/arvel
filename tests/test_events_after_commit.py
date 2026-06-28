"""C7 — after-commit event deferral + subscriber discovery."""

from __future__ import annotations

from typing import Any

import pytest

from arvel.events import Dispatcher, ShouldDispatchAfterCommit


class OrderShipped(ShouldDispatchAfterCommit):
    def __init__(self, order_id: int) -> None:
        self.order_id = order_id


async def test_after_commit_dispatches_immediately_without_transaction() -> None:
    dispatcher = Dispatcher()
    fired: list[int] = []
    dispatcher.listen(OrderShipped, lambda event: fired.append(event.order_id))

    await dispatcher.dispatch(OrderShipped(1))
    assert fired == [1]


async def test_after_commit_defers_until_commit() -> None:
    dispatcher = Dispatcher()
    fired: list[int] = []
    dispatcher.listen(OrderShipped, lambda event: fired.append(event.order_id))

    async with dispatcher.transaction():
        await dispatcher.dispatch(OrderShipped(2))
        assert fired == []  # deferred while the transaction is open
    assert fired == [2]  # flushed on commit


async def test_after_commit_discarded_on_rollback() -> None:
    dispatcher = Dispatcher()
    fired: list[int] = []
    dispatcher.listen(OrderShipped, lambda event: fired.append(event.order_id))

    with pytest.raises(RuntimeError):
        async with dispatcher.transaction():
            await dispatcher.dispatch(OrderShipped(3))
            raise RuntimeError("boom")
    assert fired == []  # rolled back → never dispatched


async def test_subscriber_discovery() -> None:
    dispatcher = Dispatcher()
    fired: list[str] = []

    class OrderSubscriber:
        def subscribe(self, events: Dispatcher) -> None:
            events.listen("order.created", self.on_created)

        def on_created(self, *args: Any) -> None:
            fired.append("created")

    dispatcher.subscribe(OrderSubscriber())
    await dispatcher.dispatch("order.created")
    assert fired == ["created"]
