"""OAuthServiceProvider — wires arvel-oauth into an Arvel app.

Binds ``OAuthConfig`` and ``OAuthManager``, registers the
``oauth:install`` command, and publishes the ``oauth_accounts`` migration
under the ``arvel-oauth`` tag.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from arvel.providers.service_provider import ServiceProvider

from arvel_oauth.commands import OAuthInstallCommand
from arvel_oauth.config import OAuthConfig
from arvel_oauth.manager import OAuthManager

if TYPE_CHECKING:
    from arvel.console import Command


class OAuthServiceProvider(ServiceProvider):
    """Boot arvel-oauth inside an Arvel application."""

    def register(self) -> None:
        config = OAuthConfig()
        self.container.instance(OAuthConfig, config)
        self.container.instance(OAuthManager, OAuthManager(config))

    async def boot(self) -> None:
        from arvel_oauth import migrations as oauth_migrations  # noqa: PLC0415

        stub = Path(oauth_migrations.__file__).parent / "create_oauth_accounts_table.py"
        self.publishes(
            {stub: "database/migrations"},
            tag="arvel-oauth",
            is_migrations=True,
        )

    def commands(self) -> list[type[Command] | Command]:
        return [OAuthInstallCommand]


__all__ = ["OAuthServiceProvider"]
