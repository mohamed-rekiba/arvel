"""
Gate + Policy[T] authorization.
Tests import from arvel.auth.gate and arvel.auth.policy → red state.
"""

from __future__ import annotations

from typing import Any

import pytest


class _FakeUser:
    def __init__(self, id: str, role: str = "user") -> None:
        self.id = id
        self.role = role


def _ability_edit_post(user: Any, post: Any) -> bool:
    return bool(user.id == post["owner_id"])


def _ability_edit_post_get(user: Any, post: Any) -> bool:
    return bool(user.id == post.get("owner_id"))


def _ability_admin_only(user: Any) -> bool:
    return bool(user.role == "admin")


def _ability_read(_user: Any) -> bool:
    return True


def _before_super_admin(user: Any, _ability: Any) -> bool | None:
    return True if user.role == "super_admin" else None


@pytest.mark.asyncio
async def test_gate_allows_registered_ability() -> None:
    from arvel.auth.gate import Gate

    gate = Gate()
    gate.define("edit-post", _ability_edit_post)

    user = _FakeUser("u1")
    assert await gate.allows("edit-post", user, {"owner_id": "u1"}) is True
    assert await gate.allows("edit-post", user, {"owner_id": "u2"}) is False


@pytest.mark.asyncio
async def test_gate_denies_is_inverse_of_allows() -> None:
    from arvel.auth.gate import Gate

    gate = Gate()
    gate.define("delete-post", _ability_admin_only)

    user = _FakeUser("u1", role="user")
    assert await gate.denies("delete-post", user) is True

    admin = _FakeUser("a1", role="admin")
    assert await gate.denies("delete-post", admin) is False


# Gate fail-closed — unregistered ability raises


@pytest.mark.asyncio
async def test_gate_fail_closed_raises_for_unregistered_ability() -> None:
    from arvel.auth.exceptions import AuthorizationException
    from arvel.auth.gate import Gate

    gate = Gate()
    user = _FakeUser("u1")

    with pytest.raises(AuthorizationException):
        await gate.allows("nonexistent-ability", user)


# Gate.authorize() raises 403 on denial


@pytest.mark.asyncio
async def test_gate_authorize_raises_authorization_exception_on_denial() -> None:
    from arvel.auth.exceptions import AuthorizationException
    from arvel.auth.gate import Gate

    gate = Gate()
    gate.define("admin-only", _ability_admin_only)

    with pytest.raises(AuthorizationException):
        await gate.authorize("admin-only", _FakeUser("u1", role="user"))


@pytest.mark.asyncio
async def test_gate_authorize_does_not_raise_when_allowed() -> None:
    from arvel.auth.gate import Gate

    gate = Gate()
    gate.define("admin-only", _ability_admin_only)

    await gate.authorize("admin-only", _FakeUser("a1", role="admin"))


# Gate.before() override


@pytest.mark.asyncio
async def test_gate_before_override_grants_all_for_super_admin() -> None:
    from arvel.auth.gate import Gate

    gate = Gate()
    gate.define("edit-post", _ability_edit_post_get)
    gate.before(_before_super_admin)

    admin = _FakeUser("sa1", role="super_admin")
    # even without being the owner, before() grants access
    assert await gate.allows("edit-post", admin, {"owner_id": "other"}) is True


# Gate.after() hook


@pytest.mark.asyncio
async def test_gate_after_hook_called_with_result() -> None:
    from arvel.auth.gate import Gate

    after_calls: list[tuple[Any, str, bool]] = []
    gate = Gate()
    gate.define("read", _ability_read)

    def _after(user: Any, ability: Any, result: Any) -> None:
        after_calls.append((user, ability, result))

    gate.after(_after)

    user = _FakeUser("u1")
    await gate.allows("read", user)
    assert len(after_calls) == 1
    assert after_calls[0] == (user, "read", True)


@pytest.mark.asyncio
async def test_policy_view_method_called_for_view_ability() -> None:
    from arvel.auth.policy import Policy

    class PostPolicy(Policy[dict[str, Any]]):
        async def view(self, user: Any, resource: dict[str, Any]) -> bool:
            return True

        async def update(self, user: Any, resource: dict[str, Any]) -> bool:
            return bool(user.get("role") == "admin")

    policy = PostPolicy()
    user = _FakeUser("u1")
    assert await policy.check("view", user, {"id": "p1"}) is True


@pytest.mark.asyncio
async def test_policy_update_method_returns_false_for_non_admin() -> None:
    from arvel.auth.policy import Policy

    class PostPolicy(Policy[dict[str, Any]]):
        async def view(self, user: Any, resource: dict[str, Any]) -> bool:
            return True

        async def update(self, user: Any, resource: dict[str, Any]) -> bool:
            return isinstance(user, _FakeUser) and user.role == "admin"

    policy = PostPolicy()
    user = _FakeUser("u1", role="user")
    assert await policy.check("update", user, {"id": "p1"}) is False


# Gate.policy() registers a policy


@pytest.mark.asyncio
async def test_gate_policy_registration_routes_to_policy_method() -> None:
    from arvel.auth.gate import Gate
    from arvel.auth.policy import Policy

    class PostPolicy(Policy[dict[str, Any]]):
        async def view(self, user: Any, resource: dict[str, Any]) -> bool:
            return resource.get("public", False) is True

    gate = Gate()
    gate.policy(dict, PostPolicy())

    user = _FakeUser("u1")
    assert await gate.allows("view", user, {"public": True}) is True
    assert await gate.allows("view", user, {"public": False}) is False


# Policy before() filters — Laravel parity (True grants all, False denies all, None falls through)


@pytest.mark.asyncio
async def test_gate_policy_before_grants_all_for_admin() -> None:
    from arvel.auth.gate import Gate
    from arvel.auth.policy import Policy

    class PostPolicy(Policy[dict[str, Any]]):
        def before(self, user: Any, _ability: str) -> bool | None:
            return True if user.role == "admin" else None

        async def view(self, _user: Any, resource: dict[str, Any]) -> bool:
            return resource.get("public", False) is True

    gate = Gate()
    gate.policy(dict, PostPolicy())

    admin = _FakeUser("a1", role="admin")
    # before() grants even when the view method would deny
    assert await gate.allows("view", admin, {"public": False}) is True


@pytest.mark.asyncio
async def test_gate_policy_before_denies_all_for_banned() -> None:
    from arvel.auth.gate import Gate
    from arvel.auth.policy import Policy

    class PostPolicy(Policy[dict[str, Any]]):
        def before(self, user: Any, _ability: str) -> bool | None:
            return False if user.role == "banned" else None

        async def view(self, _user: Any, _resource: dict[str, Any]) -> bool:
            return True

    gate = Gate()
    gate.policy(dict, PostPolicy())

    banned = _FakeUser("b1", role="banned")
    # before() denies even though view() would allow
    assert await gate.allows("view", banned, {"public": True}) is False


@pytest.mark.asyncio
async def test_gate_policy_before_none_falls_through_to_method() -> None:
    from arvel.auth.gate import Gate
    from arvel.auth.policy import Policy

    class PostPolicy(Policy[dict[str, Any]]):
        def before(self, _user: Any, _ability: str) -> bool | None:
            return None

        async def view(self, _user: Any, resource: dict[str, Any]) -> bool:
            return resource.get("public", False) is True

    gate = Gate()
    gate.policy(dict, PostPolicy())

    user = _FakeUser("u1")
    assert await gate.allows("view", user, {"public": True}) is True
    assert await gate.allows("view", user, {"public": False}) is False


@pytest.mark.asyncio
async def test_policy_check_honours_before() -> None:
    from arvel.auth.policy import Policy

    class PostPolicy(Policy[dict[str, Any]]):
        def before(self, user: Any, _ability: str) -> bool | None:
            return True if user.role == "admin" else None

        async def update(self, _user: Any, _resource: dict[str, Any]) -> bool:
            return False

    policy = PostPolicy()
    admin = _FakeUser("a1", role="admin")
    user = _FakeUser("u1", role="user")
    assert await policy.check("update", admin, {"id": "p1"}) is True
    assert await policy.check("update", user, {"id": "p1"}) is False
