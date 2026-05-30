"""FR-013-013, FR-013-014 — Exceptions and BroadcasterFake (under arvel.testing)."""

from __future__ import annotations

from typing import Any

import pytest


def test_exception_hierarchy() -> None:
    """FR-013-013: every broadcast-side exception inherits BroadcastException."""
    from arvel.broadcasting.exceptions import (
        BroadcastAuthError,
        BroadcastChannelError,
        BroadcastDriverError,
        BroadcastException,
    )

    assert issubclass(BroadcastDriverError, BroadcastException)
    assert issubclass(BroadcastChannelError, BroadcastException)
    assert issubclass(BroadcastAuthError, BroadcastException)


# ─── FR-013-014 — BroadcasterFake ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fake_records_calls() -> None:
    """FR-013-014 AC1: every broadcast() call recorded with channels/event/payload."""
    from arvel.testing.broadcasting import BroadcasterFake

    fake = BroadcasterFake()
    await fake.broadcast(["orders"], "OrderShipped", {"order_id": 42})
    await fake.broadcast(["chat.1"], "MessageSent", {"text": "hi"})
    assert len(fake.calls) == 2
    assert fake.calls[0].channels == ["orders"]
    assert fake.calls[0].event == "OrderShipped"
    assert fake.calls[0].payload == {"order_id": 42}


def test_fake_assert_broadcasted_passes() -> None:
    """FR-013-014 AC2: assert_broadcasted(event_name) passes if at least one call matches."""
    import asyncio

    from arvel.testing.broadcasting import BroadcasterFake

    fake = BroadcasterFake()
    asyncio.run(fake.broadcast(["orders"], "OrderShipped", {"order_id": 42}))
    fake.assert_broadcasted("OrderShipped")


def test_fake_assert_broadcasted_fails_with_message() -> None:
    """FR-013-014 AC2: assertion failure carries diagnostic context."""
    from arvel.testing.broadcasting import BroadcasterFake

    fake = BroadcasterFake()
    with pytest.raises(AssertionError, match="OrderShipped"):
        fake.assert_broadcasted("OrderShipped")


def test_fake_assert_broadcasted_on() -> None:
    """FR-013-014 AC3: assert_broadcasted_on(channel) filters by channel."""
    import asyncio

    from arvel.testing.broadcasting import BroadcasterFake

    fake = BroadcasterFake()
    asyncio.run(fake.broadcast(["orders"], "X", {}))
    fake.assert_broadcasted_on("orders", "X")
    with pytest.raises(AssertionError):
        fake.assert_broadcasted_on("other-channel", "X")


def test_fake_assert_nothing_broadcasted() -> None:
    """FR-013-014 AC4: assert_nothing_broadcasted passes when no calls made."""
    from arvel.testing.broadcasting import BroadcasterFake

    fake = BroadcasterFake()
    fake.assert_nothing_broadcasted()


def test_fake_lives_under_arvel_testing() -> None:
    """ADR-059: BroadcasterFake exposed from arvel.testing.broadcasting."""
    import arvel.testing.broadcasting as t

    assert hasattr(t, "BroadcasterFake")


def test_fake_implements_broadcaster_protocol() -> None:
    """ADR-059: BroadcasterFake satisfies the Broadcaster Protocol."""
    from arvel.broadcasting import Broadcaster
    from arvel.testing.broadcasting import BroadcasterFake

    assert isinstance(BroadcasterFake(), Broadcaster)


@pytest.mark.asyncio
async def test_fake_respects_except_socket_id() -> None:
    """FR-013-014: except_socket_id is recorded so tests can assert on it."""
    from arvel.testing.broadcasting import BroadcasterFake

    fake = BroadcasterFake()
    await fake.broadcast(["x"], "X", {}, except_socket_id="abc")
    assert fake.calls[0].except_socket_id == "abc"
    # Sanity: Any is the same imported symbol used in real code; keeps lint happy.
    _ignored: Any = None
    assert _ignored is None
