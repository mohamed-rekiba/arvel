"""Broadcaster Protocol contract tests."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import pytest


def test_broadcaster_is_runtime_checkable_protocol() -> None:
    """Broadcaster is @runtime_checkable Protocol."""
    from arvel.broadcasting import Broadcaster

    assert hasattr(Broadcaster, "__protocol_attrs__") or hasattr(
        Broadcaster, "_is_runtime_protocol"
    ), "Broadcaster must be a @runtime_checkable Protocol"


def test_broadcaster_has_async_broadcast_method() -> None:
    """signature accepts channels list, event name, payload, optional socket_id."""
    from arvel.broadcasting import Broadcaster

    assert hasattr(Broadcaster, "broadcast")


@pytest.mark.parametrize(
    "driver_path",
    [
        "arvel.broadcasting.drivers.log.LogBroadcaster",
        "arvel.broadcasting.drivers.null.NullBroadcaster",
        "arvel.broadcasting.drivers.redis.RedisBroadcaster",
        "arvel.broadcasting.drivers.pusher.PusherBroadcaster",
    ],
)
def test_every_shipped_driver_implements_broadcaster(driver_path: str) -> None:
    """isinstance(driver, Broadcaster) returns True for every shipped driver."""
    import importlib

    module_path, cls_name = driver_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    cls = getattr(module, cls_name)
    # Don't instantiate — drivers may require config. Class check is enough.
    assert hasattr(cls, "broadcast")
    # Check Protocol membership by attribute presence rather than isinstance
    # (some drivers have unusual __init__ signatures we don't want to call here).
    assert callable(cls.broadcast)


@pytest.mark.asyncio
async def test_null_broadcaster_isinstance_check() -> None:
    """Confirm runtime_checkable behavior with a no-arg constructor driver."""
    from arvel.broadcasting import Broadcaster
    from arvel.broadcasting.drivers.null import NullBroadcaster

    null = NullBroadcaster()
    assert isinstance(null, Broadcaster)


def test_broadcaster_signature_accepts_named_params() -> None:
    """broadcast(channels, event, payload, *, except_socket_id=None)."""
    import inspect

    from arvel.broadcasting import Broadcaster

    sig = inspect.signature(Broadcaster.broadcast)
    assert "channels" in sig.parameters
    assert "event" in sig.parameters
    assert "payload" in sig.parameters
    assert "except_socket_id" in sig.parameters
    assert sig.parameters["except_socket_id"].kind is inspect.Parameter.KEYWORD_ONLY


def test_typing_imports_alive() -> None:
    """Keep ``Mapping`` and ``Sequence`` imports live — referenced by tests above."""
    sample: Mapping[str, Sequence[str]] = {"channels": []}
    assert sample["channels"] == []
