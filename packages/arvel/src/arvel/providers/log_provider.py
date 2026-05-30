"""LogServiceProvider — no-op stub.

Logging is bootstrapped by ObservabilityServiceProvider. Register this provider
when you want an explicit placeholder in your provider list without side effects.
"""

from __future__ import annotations

from arvel.providers.service_provider import ServiceProvider


class LogServiceProvider(ServiceProvider):
    def register(self) -> None:
        pass

    async def boot(self) -> None:
        pass


__all__ = ["LogServiceProvider"]
