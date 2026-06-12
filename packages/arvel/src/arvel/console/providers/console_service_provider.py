"""ConsoleServiceProvider — binds console Application + collects provider commands.

At ``register`` it binds an
empty :class:`arvel.console.Application` into the framework container; at
``boot`` it walks every registered ``ServiceProvider``, calls its
``commands`` method, and attaches each returned item to the bound
Application.

Once bound, the scheduler kernel can resolve the Application and wire
``SchedulerHooks.run_command`` without any user-supplied hook (see
``arvel.providers.scheduler_provider.SchedulerServiceProvider``).

User apps should register this provider **last** (or at least after every
provider whose ``commands`` depends on container bindings made during
``register``). Order matters because provider commands often need DI from
the container, and only ``register`` is guaranteed to have run by the
time ``commands`` is called.
"""

from __future__ import annotations

from arvel.console import Application
from arvel.providers.service_provider import ServiceProvider


class ConsoleServiceProvider(ServiceProvider):
    """Binds :class:`arvel.console.Application` and collects provider commands."""

    def register(self) -> None:
        """Bind an empty Application; commands are attached later in ``boot()``."""
        self.app.container.instance(Application, Application(commands=[]))

    async def boot(self) -> None:
        """Walk every provider, collect commands, register each on the Application.

        A faulty ``commands()`` (bad lazy import, container resolution error, …)
        is a developer error — it propagates and fails boot loudly rather than
        silently hiding every command that provider would have registered. Items
        returned as ``type`` are instantiated with no args; ``Command`` instances
        register as-is.
        """
        console_app: Application = self.app.container.make(Application)

        for provider in self.app.iter_providers():
            if provider is self:
                continue
            for item in provider.commands():
                cmd = item() if isinstance(item, type) else item
                console_app.register_command(cmd)


__all__ = ["ConsoleServiceProvider"]
