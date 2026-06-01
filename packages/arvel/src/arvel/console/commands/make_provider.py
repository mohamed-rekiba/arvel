"""``make:provider`` — generate a service provider with the full lifecycle.

A :class:`arvel.providers.ServiceProvider` participates in four phases:

- :meth:`register` (sync) — bind types into the container. No I/O,
  no facade calls, no awaiting — runs **before** any other provider's
  ``boot`` and must stay side-effect-free.
- :meth:`boot` (async) — wiring after every provider has registered.
  This is the right place to register listeners, route channels,
  read config, or open connections.
- :meth:`commands` (sync) — return ``Command`` subclasses to expose
  through the CLI.
- :meth:`shutdown` (async) — release resources in reverse provider
  order on application teardown.
"""

from __future__ import annotations

from typing import ClassVar

from arvel.console.commands._base_make import BaseMakeCommand
from arvel.support.str import Str

_TEMPLATE = '''"""{title} — service provider."""

from __future__ import annotations

from arvel.console import Command
from arvel.providers import ServiceProvider


class {title}(ServiceProvider):
    """Wire this module's services into the application container."""

    def register(self) -> None:
        """Bind container entries. Sync; runs before any boot()."""

    async def boot(self) -> None:
        """Run wiring that needs other providers to be registered."""

    def commands(self) -> list[type[Command] | Command]:
        """Expose this provider's console commands."""
        return []

    async def shutdown(self) -> None:
        """Release resources on application teardown."""
'''


class MakeProviderCommand(BaseMakeCommand):
    name: ClassVar[str] = "make:provider"
    help: ClassVar[str] = "Generate a ServiceProvider (register/boot/commands/shutdown)"
    _target_subdir: ClassVar[str] = "app/providers"
    _suffix: ClassVar[str] = "ServiceProvider"

    def _render(self, name: str) -> str:
        return _TEMPLATE.format(title=Str.pascal(name))
