"""LogServiceProvider — no-op stub.

Logging is bootstrapped by ObservabilityServiceProvider. Register this provider
when you want an explicit placeholder in your provider list without side effects.
"""

from __future__ import annotations

from typing import ClassVar

from arvel.console._subsystem import CliSubsystem
from arvel.providers.service_provider import ServiceProvider


class LogServiceProvider(ServiceProvider):
    subsystem: ClassVar[CliSubsystem | None] = CliSubsystem.LOG

    def register(self) -> None:
        pass

    async def boot(self) -> None:
        pass


__all__ = ["LogServiceProvider"]
