"""Phase 9 — AuthManager (session state) + Gate/Policy authorization."""

from __future__ import annotations

import pytest

from arvel.auth import Authenticatable, AuthManager, AuthorizationError, Gate


class User(Authenticatable):
    def __init__(self, identifier: int, *, is_admin: bool = False) -> None:
        self.id = identifier
        self.is_admin = is_admin


class Post:
    def __init__(self, owner_id: int) -> None:
        self.user_id = owner_id


class PostPolicy:
    async def update(self, user: User, post: Post) -> bool:
        return post.user_id == user.id


def test_auth_manager_login_logout() -> None:
    manager = AuthManager()
    assert manager.guest()
    user = User(7)
    manager.login(user)
    assert manager.check()
    assert manager.user() is user
    assert manager.id() == 7
    manager.logout()
    assert manager.guest()


async def test_gate_define() -> None:
    gate = Gate()
    gate.define("is-admin", lambda user: user.is_admin)
    assert await gate.allows("is-admin", user=User(1, is_admin=True))
    assert await gate.denies("is-admin", user=User(2))


async def test_gate_policy_resolution() -> None:
    gate = Gate()
    gate.policy(Post, PostPolicy)
    assert await gate.allows("update", Post(1), user=User(1))
    assert not await gate.allows("update", Post(2), user=User(1))


async def test_gate_before_hook_short_circuits() -> None:
    gate = Gate()
    gate.before(lambda user, ability: True if user.is_admin else None)
    gate.define("edit", lambda user: False)
    assert await gate.allows("edit", user=User(1, is_admin=True))  # before wins
    assert not await gate.allows("edit", user=User(2))


async def test_gate_authorize_raises_when_denied() -> None:
    gate = Gate()
    gate.define("edit", lambda user: False)
    with pytest.raises(AuthorizationError):
        await gate.authorize("edit", user=User(1))


async def test_gate_inspect_any_none() -> None:
    gate = Gate()
    gate.define("a", lambda user: True)
    gate.define("b", lambda user: False)
    assert (await gate.inspect("a", user=User(1))).allowed
    denied = await gate.inspect("b", user=User(1))
    assert not denied.allowed
    assert denied.code == 403
    assert await gate.any(["a", "b"], user=User(1))
    assert not await gate.none(["a"], user=User(1))


async def test_authenticatable_can() -> None:
    gate = Gate()
    gate.define("ping", lambda user: True)
    # no app bound → user.can resolves a fresh empty Gate → denies
    assert await User(1).can("ping") is False
