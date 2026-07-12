"""Auth (doc 15) — Gate authorization resolution paths: define, policy, before-hook, responses."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

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


# --- policy resolution matrix (spec 15: __policy__ / registry / unregistered) --------------------


class Comment:
    pass


class CommentPolicy:
    def update(self, user: User, comment: Comment) -> bool:
        return user.admin


class AnnotatedPost(Post):
    __policy__ = PostPolicy  # explicit, typed convention — no gate.policy() call needed


class OverriddenPost(Post):
    __policy__ = CommentPolicy  # would deny (admin-only) unless overridden below


def test_resolve_policy_uses_model_policy_classvar() -> None:
    gate = Gate()
    assert isinstance(gate.resolve_policy(AnnotatedPost), PostPolicy)


async def test_policy_classvar_model_resolves_without_registration() -> None:
    gate = Gate()
    post = AnnotatedPost(owner_id=1)
    assert await gate.allows("update", post, user=User(1)) is True
    assert await gate.allows("update", post, user=User(2)) is False


def test_resolve_policy_uses_provider_registered_registry() -> None:
    gate = Gate()
    gate.register_policies({Comment: CommentPolicy})
    assert isinstance(gate.resolve_policy(Comment), CommentPolicy)


async def test_provider_registered_registry_resolves() -> None:
    gate = Gate()
    gate.register_policies({Comment: CommentPolicy})
    assert await gate.allows("update", Comment(), user=User(1, admin=True)) is True
    assert await gate.allows("update", Comment(), user=User(2, admin=False)) is False


def test_resolve_policy_unregistered_model_returns_none() -> None:
    assert Gate().resolve_policy(Comment) is None


async def test_unregistered_model_falls_through_to_deny() -> None:
    # no gate.define, no gate.policy, no __policy__, no register_policies → deny by default
    assert await Gate().allows("update", Comment(), user=User(1)) is False


def test_explicit_policy_registration_wins_over_classvar_and_registry() -> None:
    gate = Gate()
    gate.register_policies({OverriddenPost: CommentPolicy})  # lowest priority
    assert isinstance(gate.resolve_policy(OverriddenPost), CommentPolicy)  # __policy__ wins so far
    gate.policy(OverriddenPost, PostPolicy)  # explicit registration — highest priority
    assert isinstance(gate.resolve_policy(OverriddenPost), PostPolicy)


def test_classvar_wins_over_registry() -> None:
    gate = Gate()
    gate.register_policies({AnnotatedPost: CommentPolicy})  # registry says CommentPolicy
    # AnnotatedPost.__policy__ (PostPolicy) still wins — classvar beats the registry tier
    assert isinstance(gate.resolve_policy(AnnotatedPost), PostPolicy)


# --- guest handling: non-Optional auto-denies, Optional/unannotated is invoked with None ---------


async def test_guest_auto_denied_for_non_optional_typed_ability() -> None:
    gate = Gate()

    def view(user: User) -> bool:
        raise AssertionError("must not be called for a guest")  # would AttributeError in real code

    gate.define("view", view)
    assert await gate.allows("view", user=None) is False


async def test_guest_invoked_for_optional_typed_ability() -> None:
    gate = Gate()
    seen: list[Any] = []

    def view(user: User | None) -> bool:
        seen.append(user)
        return True  # this policy opted into guest access (e.g. a public resource)

    gate.define("view", view)
    assert await gate.allows("view", user=None) is True
    assert seen == [None]


async def test_guest_invoked_for_legacy_optional_typed_ability() -> None:
    gate = Gate()
    seen: list[Any] = []

    def view(user: Optional[User]) -> bool:  # noqa: UP045 - exercising the legacy Optional[] form
        seen.append(user)
        return True

    gate.define("view", view)
    assert await gate.allows("view", user=None) is True
    assert seen == [None]


async def test_guest_invoked_for_unannotated_ability() -> None:
    gate = Gate()
    # untyped lambdas (the common case) stay permissive — unchanged pre-existing behavior
    gate.define("view", lambda user: True)
    assert await gate.allows("view", user=None) is True


async def test_guest_auto_denied_for_non_optional_typed_policy_method() -> None:
    gate = Gate()
    gate.policy(Post, PostPolicy)  # PostPolicy.update is typed (user: User, post: Post)
    assert await gate.allows("update", Post(owner_id=1), user=None) is False


async def test_nullable_check_is_cached_per_callback() -> None:
    """The signature/annotation inspection runs once per callback, not once per call."""
    gate = Gate()

    def view(user: User) -> bool:
        return False

    gate.define("view", view)
    await gate.allows("view", user=None)
    cache_size_after_first = len(gate._nullable_cache)
    await gate.allows("view", user=None)
    await gate.allows("view", user=None)
    assert len(gate._nullable_cache) == cache_size_after_first == 1


class DenyAllPolicy:
    def update(self, user: User, post: Post) -> bool:
        return False


async def test_policy_method_takes_precedence_over_a_same_named_define() -> None:
    """Documented resolution order: before → policy method → named ability. A model with a
    registered policy is decided by the policy; a same-named `define` must not shadow it."""
    gate = Gate()
    gate.policy(Post, DenyAllPolicy)
    gate.define("update", lambda user, post: True)  # would-be permissive shadow
    assert await gate.allows("update", Post(owner_id=1), user=User(1)) is False


async def test_named_ability_still_resolves_when_the_policy_lacks_the_method() -> None:
    gate = Gate()
    gate.policy(Post, DenyAllPolicy)  # has no "ship" method
    gate.define("ship", lambda user, post: True)
    assert await gate.allows("ship", Post(owner_id=1), user=User(1)) is True


async def test_policy_before_runs_even_when_a_same_named_define_exists() -> None:
    class SuperAdminPolicy:
        def before(self, user: User, ability: str) -> Optional[bool]:
            return True if user.admin else None

        def update(self, user: User, post: Post) -> bool:
            return False

    gate = Gate()
    gate.policy(Post, SuperAdminPolicy)
    gate.define("update", lambda user, post: False)
    assert await gate.allows("update", Post(owner_id=9), user=User(1, admin=True)) is True
