"""SocialAuthServiceProvider — wires arvel-auth-social into an Arvel app.

Binds ``SocialAuthConfig`` and ``SocialAuthManager``, registers the
``auth:social:install`` command, and publishes the ``social_accounts`` migration
under the ``arvel-auth-social`` tag.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from arvel.providers.service_provider import ServiceProvider

from arvel_auth_social.commands import SocialInstallCommand
from arvel_auth_social.config import SocialAuthConfig
from arvel_auth_social.manager import SocialAuthManager

if TYPE_CHECKING:
    from arvel.console import Command


class SocialAuthServiceProvider(ServiceProvider):
    """Boot arvel-auth-social inside an Arvel application."""

    def register(self) -> None:
        config = SocialAuthConfig()
        self.container.instance(SocialAuthConfig, config)
        self.container.instance(SocialAuthManager, SocialAuthManager(config))

    async def boot(self) -> None:
        from arvel_auth_social import migrations as social_migrations  # noqa: PLC0415

        stub = Path(social_migrations.__file__).parent / "create_social_accounts_table.py"
        self.publishes(
            {stub: "database/migrations"},
            tag="arvel-auth-social",
            is_migrations=True,
        )

    def commands(self) -> list[type[Command] | Command]:
        return [SocialInstallCommand]


__all__ = ["SocialAuthServiceProvider"]
