"""ConsoleServiceProvider — binds console Application + collects provider commands.

Introduced by WI-arvel-020 to close FB-019-001. At ``register()`` it binds an
empty :class:`arvel.console.Application` into the framework container; at
``boot()`` it walks every registered ``ServiceProvider``, calls its
``commands()`` method, and attaches each returned item to the bound
Application.

Once bound, the scheduler kernel can resolve the Application and wire
``SchedulerHooks.run_command`` without any user-supplied hook (see
``arvel.providers.scheduler_provider.SchedulerServiceProvider``).

User apps should register this provider **last** (or at least after every
provider whose ``commands()`` depends on container bindings made during
``register()``). Order matters because provider commands often need DI from
the container, and only ``register()`` is guaranteed to have run by the
time ``commands()`` is called.
"""

from __future__ import annotations

import logging

from arvel.console import Application
from arvel.providers.service_provider import ServiceProvider

_log = logging.getLogger("arvel.console")


class ConsoleServiceProvider(ServiceProvider):
    """Binds :class:`arvel.console.Application` and collects provider commands."""

    def register(self) -> None:
        """Bind an empty Application; commands are attached later in ``boot()``."""
        self.app.container.instance(Application, Application(commands=[]))

    async def boot(self) -> None:
        """Walk every provider, collect commands, register each on the Application.

        A provider whose ``commands()`` raises is logged and skipped — other
        providers' commands still register. Items returned as ``type`` are
        instantiated with no args; items returned as ``Command`` instances are
        registered as-is.
        """
        console_app: Application = self.app.container.make(Application)

        for provider in self.app.iter_providers():
            if provider is self:
                continue
            try:
                items = provider.commands()
            except Exception as exc:  # noqa: BLE001
                # Provider commands() runs arbitrary user code that may raise
                # any subclass of Exception (ImportError on lazy imports, container
                # resolution failures, validation errors, ...). Catching broadly is
                # intentional: a single faulty provider must not take down the rest
                # of the CLI bootstrap.
                _log.warning(
                    "%s.commands() raised %s; skipping its console commands. Reason: %s",
                    type(provider).__name__,
                    type(exc).__name__,
                    exc,
                )
                continue

            for item in items:
                cmd = item() if isinstance(item, type) else item
                console_app.register_command(cmd)


__all__ = ["ConsoleServiceProvider"]
