"""Tests for claims-aware (role-based) policies."""

from __future__ import annotations

import pytest

from arvel.auth.policy import (
    AuthContext,
    Gate,
    PolicyRegistry,
    RoleBasedPolicy,
)
from arvel.security.exceptions import AuthorizationError


class TestAuthContext:
    def test_has_role(self) -> None:
        ctx = AuthContext(user="u1", roles=["admin", "editor"])
        assert ctx.has_role("admin") is True
        assert ctx.has_role("viewer") is False

    def test_has_any_role(self) -> None:
        ctx = AuthContext(user="u1", roles=["editor"])
        assert ctx.has_any_role("admin", "editor") is True
        assert ctx.has_any_role("admin", "super") is False

    def test_in_group(self) -> None:
        ctx = AuthContext(user="u1", groups=["/org/team-a"])
        assert ctx.in_group("/org/team-a") is True
        assert ctx.in_group("/org/team-b") is False

    def test_in_any_group(self) -> None:
        ctx = AuthContext(user="u1", groups=["/org/team-a", "/org/team-b"])
        assert ctx.in_any_group("/org/team-a", "/other") is True
        assert ctx.in_any_group("/x", "/y") is False

    def test_empty_context(self) -> None:
        ctx = AuthContext(user="u1")
        assert ctx.has_role("admin") is False
        assert ctx.in_group("/any") is False
        assert ctx.sub == ""
        assert ctx.claims == {}


class _ArticlePolicy(RoleBasedPolicy):
    role_action_map = {  # noqa: RUF012
        "view_any": ["viewer", "editor", "admin"],
        "view": ["viewer", "editor", "admin"],
        "create": ["editor", "admin"],
        "update": ["editor", "admin"],
        "delete": ["admin"],
    }


class _Article:
    pass


@pytest.mark.anyio
class TestRoleBasedPolicy:
    async def test_admin_bypass_via_before(self) -> None:
        policy = _ArticlePolicy()
        ctx = AuthContext(user="u1", roles=["admin"])
        result = await policy.before(ctx, "delete")
        assert result is True

    async def test_super_admin_bypass(self) -> None:
        policy = _ArticlePolicy()
        ctx = AuthContext(user="u1", roles=["super-admin"])
        result = await policy.before(ctx, "anything")
        assert result is True

    async def test_non_admin_before_returns_none(self) -> None:
        policy = _ArticlePolicy()
        ctx = AuthContext(user="u1", roles=["editor"])
        result = await policy.before(ctx, "delete")
        assert result is None

    async def test_editor_can_create(self) -> None:
        policy = _ArticlePolicy()
        ctx = AuthContext(user="u1", roles=["editor"])
        assert await policy.create(ctx) is True

    async def test_viewer_cannot_create(self) -> None:
        policy = _ArticlePolicy()
        ctx = AuthContext(user="u1", roles=["viewer"])
        assert await policy.create(ctx) is False

    async def test_editor_can_update(self) -> None:
        policy = _ArticlePolicy()
        ctx = AuthContext(user="u1", roles=["editor"])
        article = _Article()
        assert await policy.update(ctx, article) is True

    async def test_viewer_cannot_delete(self) -> None:
        policy = _ArticlePolicy()
        ctx = AuthContext(user="u1", roles=["viewer"])
        article = _Article()
        assert await policy.delete(ctx, article) is False

    async def test_plain_user_object_denied(self) -> None:
        policy = _ArticlePolicy()
        assert await policy.create("plain-user") is False

    async def test_unmapped_action_denied(self) -> None:
        policy = _ArticlePolicy()
        ctx = AuthContext(user="u1", roles=["editor"])
        assert await policy._check_role(ctx, "publish") is False


@pytest.mark.anyio
class TestGateWithRolePolicy:
    async def test_gate_allows_editor_create(self) -> None:
        registry = PolicyRegistry()
        registry.register(_Article, _ArticlePolicy)
        gate = Gate(registry)

        ctx = AuthContext(user="u1", roles=["editor"])
        assert await gate.allows(ctx, "create", resource_type=_Article) is True

    async def test_gate_denies_viewer_delete(self) -> None:
        registry = PolicyRegistry()
        registry.register(_Article, _ArticlePolicy)
        gate = Gate(registry)

        ctx = AuthContext(user="u1", roles=["viewer"])
        article = _Article()
        assert await gate.allows(ctx, "delete", article) is False

    async def test_gate_authorize_raises_on_denial(self) -> None:
        registry = PolicyRegistry()
        registry.register(_Article, _ArticlePolicy)
        gate = Gate(registry)

        ctx = AuthContext(user="u1", roles=["viewer"])
        article = _Article()
        with pytest.raises(AuthorizationError):
            await gate.authorize(ctx, "delete", article)

    async def test_gate_admin_bypass(self) -> None:
        registry = PolicyRegistry()
        registry.register(_Article, _ArticlePolicy)
        gate = Gate(registry)

        ctx = AuthContext(user="u1", roles=["admin"])
        assert await gate.allows(ctx, "delete", resource_type=_Article) is True
