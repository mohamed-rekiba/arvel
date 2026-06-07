"""BroadcastServiceProvider — registers manager + facade + console commands."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from arvel.console._subsystem import CliSubsystem
from arvel.providers.service_provider import ServiceProvider

if TYPE_CHECKING:
    from arvel.console import Command


class BroadcastServiceProvider(ServiceProvider):
    """Binds BroadcastManager and wires the Broadcast facade."""

    subsystem: ClassVar[CliSubsystem | None] = CliSubsystem.BROADCAST

    def register(self) -> None:
        from arvel.broadcasting import BroadcastConfig, BroadcastManager
        from arvel.facades.broadcast import Broadcast

        c = self.app.container
        config = c.make(BroadcastConfig) if c.bound(BroadcastConfig) else BroadcastConfig()
        c.instance(BroadcastConfig, config)
        manager = BroadcastManager(config)
        c.instance(BroadcastManager, manager)
        Broadcast.set_manager(manager)

    async def boot(self) -> None:
        return None

    def commands(self) -> list[type[Command] | Command]:
        from arvel.console.commands.reverb_commands import ReverbStartCommand

        return [ReverbStartCommand]


__all__ = ["BroadcastServiceProvider"]
