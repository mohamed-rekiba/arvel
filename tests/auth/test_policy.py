"""Tests for the policy-based authorization system."""

from __future__ import annotations

from typing import Any

import pytest

from arvel.auth.policy import Gate, Policy, PolicyRegistry
from arvel.security.exceptions import AuthorizationError


class FakeUser:
    def __init__(self, user_id: str, *, is_admin: bool = False) -> None:
        self.id = user_id
        self.is_admin = is_admin


class FakePost:
    def __init__(self, owner_id: str) -> None:
        self.owner_id = owner_id


class PostPolicy(Policy):
    async def before(self, user: Any, action: str) -> bool | None:
        if getattr(user, "is_admin", False):
            return True
        return None

    async def view(self, user: Any, resource: Any) -> bool:
        return True

    async def update(self, user: Any, resource: Any) -> bool:
        return user.id == resource.owner_id

    async def create(self, user: Any) -> bool:
        return True

    async def delete(self, user: Any, resource: Any) -> bool:
        return user.id == resource.owner_id


class TestPolicyRegistry:
    def test_register_and_get(self) -> None:
        registry = PolicyRegistry()
        registry.register(FakePost, PostPolicy)
        assert registry.get(FakePost) is PostPolicy

    def test_has_returns_true(self) -> None:
        registry = PolicyRegistry()
        registry.register(FakePost, PostPolicy)
        assert registry.has(FakePost) is True

    def test_has_returns_false(self) -> None:
        registry = PolicyRegistry()
        assert registry.has(FakePost) is False


class TestGate:
    def _gate(self) -> Gate:
        registry = PolicyRegistry()
        registry.register(FakePost, PostPolicy)
        return Gate(registry)

    @pytest.mark.anyio
    async def test_allows_owner(self) -> None:
        gate = self._gate()
        user = FakeUser("u1")
        post = FakePost("u1")
        assert await gate.allows(user, "update", post) is True

    @pytest.mark.anyio
    async def test_denies_non_owner(self) -> None:
        gate = self._gate()
        user = FakeUser("u1")
        post = FakePost("u2")
        assert await gate.allows(user, "update", post) is False

    @pytest.mark.anyio
    async def test_admin_bypass(self) -> None:
        gate = self._gate()
        admin = FakeUser("admin", is_admin=True)
        post = FakePost("u2")
        assert await gate.allows(admin, "update", post) is True

    @pytest.mark.anyio
    async def test_no_policy_denies(self) -> None:
        registry = PolicyRegistry()
        gate = Gate(registry)
        user = FakeUser("u1")
        post = FakePost("u1")
        assert await gate.allows(user, "update", post) is False

    @pytest.mark.anyio
    async def test_authorize_raises_on_deny(self) -> None:
        gate = self._gate()
        user = FakeUser("u1")
        post = FakePost("u2")
        with pytest.raises(AuthorizationError, match="Not authorized"):
            await gate.authorize(user, "update", post)

    @pytest.mark.anyio
    async def test_authorize_passes_on_allow(self) -> None:
        gate = self._gate()
        user = FakeUser("u1")
        post = FakePost("u1")
        await gate.authorize(user, "update", post)

    @pytest.mark.anyio
    async def test_unknown_action_denies(self) -> None:
        gate = self._gate()
        user = FakeUser("u1")
        post = FakePost("u1")
        assert await gate.allows(user, "nonexistent_action", post) is False

    @pytest.mark.anyio
    async def test_create_without_resource(self) -> None:
        gate = self._gate()
        user = FakeUser("u1")
        assert await gate.allows(user, "create", resource_type=FakePost) is True

    @pytest.mark.anyio
    async def test_no_resource_or_type_denies(self) -> None:
        gate = self._gate()
        user = FakeUser("u1")
        assert await gate.allows(user, "create") is False
