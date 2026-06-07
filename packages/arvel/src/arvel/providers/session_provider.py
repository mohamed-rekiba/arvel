"""SessionServiceProvider — registers the SessionManager and Session facade."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from arvel.console._subsystem import CliSubsystem
from arvel.providers.service_provider import ServiceProvider

if TYPE_CHECKING:
    from arvel.console import Command


class SessionServiceProvider(ServiceProvider):
    """Binds SessionManager to the container and wires the Session facade."""

    # Sessions are part of the HTTP request lifecycle — same subsystem as Router.
    subsystem: ClassVar[CliSubsystem | None] = CliSubsystem.HTTP

    def register(self) -> None:
        from arvel.config.session_config import SessionConfig
        from arvel.facades.session import Session
        from arvel.session import SessionManager

        c = self.app.container
        config = c.make(SessionConfig) if c.bound(SessionConfig) else SessionConfig()
        c.instance(SessionConfig, config)
        manager = SessionManager(config)
        c.instance(SessionManager, manager)
        Session.bind(c)

    async def boot(self) -> None:
        from arvel.session import migrations as session_migrations

        stub = Path(session_migrations.__file__).parent / "create_sessions_table.py"
        self.publishes(
            {stub: "database/migrations"},
            tag="arvel-session",
            is_migrations=True,
        )

    def commands(self) -> list[type[Command] | Command]:
        return []


__all__ = ["SessionServiceProvider"]
