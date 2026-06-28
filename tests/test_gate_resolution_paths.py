"""Auth (doc 15) — Gate authorization resolution paths: define, policy, before-hook, responses."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from arvel.auth.gate import AuthorizationError, Gate, GateResponse


@dataclass
class User:
    id: int
    admin: bool = False


@dataclass
class Post:
    owner_id: int


class PostPolicy:
    def update(self, user: User, post: Post) -> bool:
        return user.id == post.owner_id


async def test_defined_ability_path() -> None:
    gate = Gate()
    gate.define("ship", lambda user: user.admin)
    assert await gate.allows("ship", user=User(1, admin=True)) is True
    assert await gate.allows("ship", user=User(2, admin=False)) is False


async def test_policy_method_resolution_path() -> None:
    gate = Gate()
    gate.policy(Post, PostPolicy)
    ada, post = User(1), Post(owner_id=1)
    assert await gate.allows("update", post, user=ada) is True
    assert await gate.allows("update", post, user=User(2)) is False  # not the owner


async def test_before_hook_short_circuits() -> None:
    gate = Gate()
    gate.define("ship", lambda user: False)  # would deny
    gate.before(lambda user, ability: True if user.admin else None)
    assert await gate.allows("ship", user=User(1, admin=True)) is True  # before wins
    assert await gate.allows("ship", user=User(2)) is False  # before returns None → falls through


async def test_unknown_ability_defaults_to_deny() -> None:
    assert await Gate().allows("nonexistent", user=User(1)) is False


async def test_denies_is_inverse() -> None:
    gate = Gate()
    gate.define("ship", lambda user: user.admin)
    assert await gate.denies("ship", user=User(1, admin=False)) is True


async def test_authorize_raises_on_deny_passes_on_allow() -> None:
    gate = Gate()
    gate.define("ship", lambda user: user.admin)
    await gate.authorize("ship", user=User(1, admin=True))  # no raise
    with pytest.raises(AuthorizationError):
        await gate.authorize("ship", user=User(2, admin=False))


async def test_inspect_returns_gate_response() -> None:
    gate = Gate()
    gate.define("ship", lambda user: user.admin)
    allow = await gate.inspect("ship", user=User(1, admin=True))
    deny = await gate.inspect("ship", user=User(2))
    assert isinstance(allow, GateResponse) and bool(allow) is True
    assert bool(deny) is False


async def test_any_and_none() -> None:
    gate = Gate()
    gate.define("a", lambda user: False)
    gate.define("b", lambda user: True)
    assert await gate.any(["a", "b"], user=User(1)) is True
    assert await gate.none(["a"], user=User(1)) is True


async def test_async_policy_method_is_awaited() -> None:
    gate = Gate()

    class AsyncPolicy:
        async def view(self, user: User, post: Post) -> bool:
            return True

    gate.policy(Post, AsyncPolicy)
    assert await gate.allows("view", Post(owner_id=9), user=User(1)) is True


async def test_user_param_overrides_current_user() -> None:
    from arvel.auth import current_user

    gate = Gate()
    gate.define("ship", lambda user: user.admin)
    token = current_user.set(User(1, admin=False))
    try:
        assert await gate.allows("ship", user=User(2, admin=True)) is True  # explicit user wins
        assert await gate.allows("ship") is False  # falls back to current_user
    finally:
        current_user.reset(token)
