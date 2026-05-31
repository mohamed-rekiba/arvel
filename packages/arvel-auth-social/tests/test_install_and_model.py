"""Install command wiring, migration shape, and encrypted-token round-trip."""

from __future__ import annotations

import inspect

from arvel.facades.crypt import Crypt
from arvel_auth_social.commands import SocialInstallCommand
from arvel_auth_social.migrations import create_social_accounts_table as migration
from arvel_auth_social.models import SocialAccount
from arvel_auth_social.provider import SocialAuthServiceProvider
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def test_provider_registers_install_command() -> None:
    provider = SocialAuthServiceProvider.__new__(SocialAuthServiceProvider)
    assert SocialInstallCommand in provider.commands()


def test_install_command_metadata() -> None:
    assert SocialInstallCommand.name == "auth:social:install"
    assert SocialInstallCommand.needs_application is True


def test_migration_defines_up_and_down() -> None:
    assert inspect.iscoroutinefunction(migration.up)
    assert inspect.iscoroutinefunction(migration.down)


async def test_tokens_encrypted_at_rest(async_session: AsyncSession) -> None:
    from arvel.auth.models.user import User

    user = User(name="T", email="t@example.com", password="x")
    async_session.add(user)
    await async_session.flush()

    account = SocialAccount(
        user_id=user.id,
        provider="google",
        provider_id="g-9",
        tokens={"access_token": "super-secret"},
    )
    async_session.add(account)
    await async_session.flush()

    # Raw column value must be ciphertext, not the plaintext token.
    raw = await async_session.execute(
        select(SocialAccount.tokens).where(SocialAccount.id == account.id)
    )
    stored = raw.scalar_one()
    assert isinstance(stored, dict)
    assert stored["access_token"] == "super-secret"  # decrypted on load

    # Prove the underlying string is encrypted by inspecting the bind output.
    from arvel_auth_social.models import EncryptedJson

    ciphertext = EncryptedJson().process_bind_param({"access_token": "super-secret"}, None)  # type: ignore[arg-type]
    assert ciphertext is not None
    assert "super-secret" not in ciphertext
    assert Crypt.decrypt_string(ciphertext) == '{"access_token": "super-secret"}'
