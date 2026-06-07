"""Install command wiring, migration shape, and encrypted-token round-trip."""

from __future__ import annotations

import inspect

from arvel.facades.crypt import Crypt
from arvel_oauth.commands import OAuthInstallCommand
from arvel_oauth.migrations import create_oauth_accounts_table as migration
from arvel_oauth.models import OAuthAccount
from arvel_oauth.provider import OAuthServiceProvider
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def test_provider_registers_install_command() -> None:
    provider = OAuthServiceProvider.__new__(OAuthServiceProvider)
    assert OAuthInstallCommand in provider.commands()


def test_install_command_metadata() -> None:
    from arvel.console._subsystem import CliSubsystem

    assert OAuthInstallCommand.name == "oauth:install"
    assert OAuthInstallCommand.needs_framework() is True
    assert CliSubsystem.USER_PROVIDERS in OAuthInstallCommand.requires


def test_migration_defines_up_and_down() -> None:
    assert inspect.iscoroutinefunction(migration.up)
    assert inspect.iscoroutinefunction(migration.down)


async def test_tokens_encrypted_at_rest(async_session: AsyncSession) -> None:
    from arvel.auth.models.user import User

    user = User(name="T", email="t@example.com", password="x")
    async_session.add(user)
    await async_session.flush()

    account = OAuthAccount(
        user_id=user.id,
        provider="google",
        provider_id="g-9",
        tokens={"access_token": "super-secret"},
    )
    async_session.add(account)
    await async_session.flush()

    # Raw column value must be ciphertext, not the plaintext token.
    raw = await async_session.execute(
        select(OAuthAccount.__table__.c.tokens).where(OAuthAccount.__table__.c.id == account.id)
    )
    stored = raw.scalar_one()
    assert isinstance(stored, dict)
    assert stored["access_token"] == "super-secret"  # decrypted on load

    # Prove the underlying string is encrypted by inspecting the bind output.
    from arvel_oauth.models import EncryptedJson

    ciphertext = EncryptedJson().process_bind_param({"access_token": "super-secret"}, None)  # type: ignore[arg-type]
    assert ciphertext is not None
    assert "super-secret" not in ciphertext
    assert Crypt.decrypt_string(ciphertext) == '{"access_token": "super-secret"}'
