"""Coverage — AuthManager.attempt + Authenticatable identifiers (doc 15)."""

from __future__ import annotations

from typing import Any

from arvel.auth import Authenticatable, AuthManager


class User(Authenticatable):
    def __init__(self, identifier: int, password_hash: str) -> None:
        self.id = identifier
        self.password = password_hash


def test_authenticatable_identifiers() -> None:
    user = User(7, "hashed")
    assert user.get_auth_identifier() == 7
    assert user.get_auth_password() == "hashed"


async def test_attempt_success() -> None:
    from arvel.security import Hasher

    hasher = Hasher()
    user = User(1, hasher.make("secret"))

    async def provider(credentials: dict[str, Any]) -> User | None:
        return user if credentials["email"] == "a@b.com" else None

    manager = AuthManager()
    assert await manager.attempt({"email": "a@b.com", "password": "secret"}, provider) is True
    assert manager.user() is user
    assert manager.check()
    assert manager.id() == 1
    manager.logout()
    assert manager.guest()


async def test_attempt_wrong_password() -> None:
    from arvel.security import Hasher

    user = User(1, Hasher().make("secret"))

    async def provider(credentials: dict[str, Any]) -> User:
        return user

    assert await AuthManager().attempt({"email": "a@b.com", "password": "WRONG"}, provider) is False


async def test_attempt_unknown_user() -> None:
    async def provider(credentials: dict[str, Any]) -> None:
        return None

    assert await AuthManager().attempt({"email": "x", "password": "y"}, provider) is False
