"""Broadcast facade — classmethod API delegating to BroadcastManager (FR-013-007)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any, ClassVar

from arvel.broadcasting.channels import ChannelRegistry

if TYPE_CHECKING:
    from arvel.broadcasting.manager import BroadcastManager
    from arvel.broadcasting.protocol import Broadcaster
    from arvel.broadcasting.should_broadcast import ShouldBroadcast


_GLOBAL_REGISTRY = ChannelRegistry()


class Broadcast:
    """Bound by ``BroadcastServiceProvider.register()``.

    Tests can swap the bound manager via ``Broadcast.set_manager(...)``.
    """

    manager: ClassVar[BroadcastManager | None] = None

    @classmethod
    def set_manager(cls, manager: BroadcastManager | None) -> None:
        cls.manager = manager

    @classmethod
    def _require_manager(cls) -> BroadcastManager:
        if cls.manager is None:
            msg = "Broadcast facade is not bound. Register BroadcastServiceProvider."
            raise RuntimeError(msg)
        return cls.manager

    @classmethod
    def driver(cls, name: str | None = None) -> Broadcaster:
        return cls._require_manager().driver(name)

    @classmethod
    async def send(
        cls,
        channels: Sequence[str],
        event: str,
        payload: Mapping[str, object],
        *,
        except_socket_id: str | None = None,
    ) -> None:
        await cls.driver().broadcast(
            channels,
            event,
            payload,
            except_socket_id=except_socket_id,
        )

    @classmethod
    async def event(cls, evt: ShouldBroadcast) -> None:
        """Dispatch a ShouldBroadcast event via the default driver."""
        await cls.send(
            list(evt.broadcast_on()),
            evt.broadcast_as(),
            evt.broadcast_with(),
        )

    @classmethod
    def channel(
        cls,
        pattern: str,
    ) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
        """Decorator: register an authorization callback for ``pattern``."""

        def _decorator(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
            _GLOBAL_REGISTRY.register(pattern, fn)
            return fn

        return _decorator

    @classmethod
    def registry(cls) -> ChannelRegistry:
        return _GLOBAL_REGISTRY


__all__ = ["Broadcast"]
