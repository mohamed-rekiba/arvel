"""Tests for Gate before/after hooks — global authorization callbacks."""

from __future__ import annotations

from typing import Any

import pytest

from arvel.auth.policy import Gate, Policy, PolicyRegistry
from arvel.security.exceptions import AuthorizationError


class FakeUser:
    def __init__(self, user_id: str, *, is_super_admin: bool = False) -> None:
        self.id = user_id
        self.is_super_admin = is_super_admin


class FakePost:
    def __init__(self, owner_id: str) -> None:
        self.owner_id = owner_id


class PostPolicy(Policy):
    async def view(self, user: Any, resource: Any) -> bool:
        return True

    async def update(self, user: Any, resource: Any) -> bool:
        return user.id == resource.owner_id

    async def create(self, user: Any) -> bool:
        return True

    async def delete(self, user: Any, resource: Any) -> bool:
        return user.id == resource.owner_id


def _gate() -> Gate:
    registry = PolicyRegistry()
    registry.register(FakePost, PostPolicy)
    return Gate(registry)


class TestGateBeforeHooks:
    async def test_before_hook_grants_super_admin(self) -> None:
        """FR-013a: Super-admin hook returns True → access granted."""
        gate = _gate()

        async def super_admin_hook(user: Any, ability: str) -> bool | None:
            if getattr(user, "is_super_admin", False):
                return True
            return None

        gate.before(super_admin_hook)

        admin = FakeUser("admin", is_super_admin=True)
        post = FakePost("other-user")

        assert await gate.allows(admin, "update", post) is True

    async def test_before_hook_returns_none_continues(self) -> None:
        """FR-013b: Before hook returns None → normal policy evaluation."""
        gate = _gate()

        async def passthrough_hook(user: Any, ability: str) -> bool | None:
            return None

        gate.before(passthrough_hook)

        user = FakeUser("u1")
        post = FakePost("u2")

        assert await gate.allows(user, "update", post) is False

    async def test_before_hook_returns_false_denies(self) -> None:
        """FR-013c: Before hook returns False → access denied."""
        gate = _gate()

        async def deny_all_hook(user: Any, ability: str) -> bool | None:
            return False

        gate.before(deny_all_hook)

        user = FakeUser("u1")
        post = FakePost("u1")

        assert await gate.allows(user, "update", post) is False

    async def test_multiple_before_hooks_first_non_none_wins(self) -> None:
        """FR-013d: Multiple before hooks, first non-None result wins."""
        gate = _gate()

        call_order: list[str] = []

        async def hook_a(user: Any, ability: str) -> bool | None:
            call_order.append("a")
            return None

        async def hook_b(user: Any, ability: str) -> bool | None:
            call_order.append("b")
            return True

        async def hook_c(user: Any, ability: str) -> bool | None:
            call_order.append("c")
            return False

        gate.before(hook_a)
        gate.before(hook_b)
        gate.before(hook_c)

        user = FakeUser("u1")
        post = FakePost("u2")

        result = await gate.allows(user, "update", post)

        assert result is True
        assert call_order == ["a", "b"]

    async def test_before_hook_without_resource_type(self) -> None:
        gate = _gate()

        async def allow_hook(user: Any, ability: str) -> bool | None:
            return True

        gate.before(allow_hook)

        user = FakeUser("u1")

        assert await gate.allows(user, "create", resource_type=FakePost) is True


class TestGateAfterHooks:
    async def test_after_hook_can_override_deny_to_allow(self) -> None:
        """FR-014: After hook overrides policy result."""
        gate = _gate()

        async def override_hook(user: Any, ability: str, result: bool) -> bool | None:
            if ability == "update":
                return True
            return None

        gate.after(override_hook)

        user = FakeUser("u1")
        post = FakePost("u2")

        assert await gate.allows(user, "update", post) is True

    async def test_after_hook_returning_none_keeps_policy_result(self) -> None:
        gate = _gate()

        async def noop_hook(user: Any, ability: str, result: bool) -> bool | None:
            return None

        gate.after(noop_hook)

        user = FakeUser("u1")
        post = FakePost("u2")

        assert await gate.allows(user, "update", post) is False

    async def test_after_hook_can_deny_allowed_action(self) -> None:
        gate = _gate()

        async def deny_hook(user: Any, ability: str, result: bool) -> bool | None:
            return False

        gate.after(deny_hook)

        user = FakeUser("u1")
        post = FakePost("u1")

        assert await gate.allows(user, "update", post) is False

    async def test_multiple_after_hooks_last_non_none_wins(self) -> None:
        gate = _gate()

        async def hook_a(user: Any, ability: str, result: bool) -> bool | None:
            return True

        async def hook_b(user: Any, ability: str, result: bool) -> bool | None:
            return None

        gate.after(hook_a)
        gate.after(hook_b)

        user = FakeUser("u1")
        post = FakePost("u2")

        result = await gate.allows(user, "update", post)

        assert result is True

    async def test_authorize_respects_before_hooks(self) -> None:
        gate = _gate()

        async def deny_hook(user: Any, ability: str) -> bool | None:
            return False

        gate.before(deny_hook)

        user = FakeUser("u1")
        post = FakePost("u1")

        with pytest.raises(AuthorizationError):
            await gate.authorize(user, "update", post)


class TestGateHooksCombined:
    async def test_before_short_circuits_skips_policy_and_after(self) -> None:
        gate = _gate()
        after_called = False

        async def grant_hook(user: Any, ability: str) -> bool | None:
            return True

        async def after_hook(user: Any, ability: str, result: bool) -> bool | None:
            nonlocal after_called
            after_called = True
            return None

        gate.before(grant_hook)
        gate.after(after_hook)

        user = FakeUser("u1")
        post = FakePost("u2")

        result = await gate.allows(user, "update", post)

        assert result is True
        assert after_called is False

    async def test_existing_per_policy_before_still_works(self) -> None:
        """Ensure per-policy before() still functions alongside global hooks."""
        gate = _gate()

        async def noop_global(user: Any, ability: str) -> bool | None:
            return None

        gate.before(noop_global)

        admin = FakeUser("admin", is_super_admin=False)
        post = FakePost("other")

        assert await gate.allows(admin, "update", post) is False
