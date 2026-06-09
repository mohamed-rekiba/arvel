"""Authorization escalation guards on AdminUsersController (WI-arvel-003 / F1).

The actor must hold a permission to grant or revoke it, and must outrank a role to
revoke it. Without these checks a `roles.manage` holder could grant themselves any
permission (OWASP A01). These are behavioral tests with monkeypatched dependencies —
no DB / docker.
"""

from __future__ import annotations

from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from arvel.http.exceptions import AuthorizationException, NotFoundException


def _controller_module() -> ModuleType:
    # pytest's prepend mode inserts the workspace root ahead of this kit backend, so a
    # bare `import config` resolves to the workspace's `config` package (which lacks the
    # kit's submodules) instead of the kit's own. Force the kit backend to the front and
    # drop any stale `config` binding before importing the controller's model chain.
    # Contained here on purpose — it's a monorepo test-harness quirk, not app behavior.
    import importlib
    import sys
    from pathlib import Path

    backend = str(Path(__file__).resolve().parents[2])
    if sys.path[0] != backend:
        sys.path.insert(0, backend)
    for name in [n for n in sys.modules if n == "config" or n.startswith("config.")]:
        del sys.modules[name]
    return importlib.import_module("app.http.controllers.admin.users")


class _Actor:
    def __init__(self, *, perms: set[str], level: int) -> None:
        self.id = 1
        self._perms = perms
        self._level = level

    async def has_permission_to(self, perm: str) -> bool:
        return perm in self._perms

    async def has_level(self, minimum: int) -> bool:
        return self._level >= minimum


def _patch_actor(monkeypatch: pytest.MonkeyPatch, mod: ModuleType, actor: _Actor) -> None:
    async def fake_require_permission(_request: Any, _perm: str) -> Any:
        return actor

    monkeypatch.setattr(mod, "require_permission", fake_require_permission)


def _model_returning(obj: Any) -> type:
    class _Query:
        async def first(self) -> Any:
            return obj

    class _Model:
        id = 0

        @classmethod
        def where(cls, *_a: Any, **_k: Any) -> Any:
            return _Query()

    return _Model


def _request() -> Any:
    return SimpleNamespace()


# ─── grant_permission ─────────────────────────────────────────────────────


async def test_grant_permission_blocks_when_actor_lacks_permission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _controller_module()
    _patch_actor(monkeypatch, mod, _Actor(perms=set(), level=60))
    ctrl = mod.AdminUsersController()
    payload = SimpleNamespace(permission="users.manage")
    with pytest.raises(AuthorizationException):
        await ctrl.grant_permission(5, payload, _request())


async def test_grant_permission_allows_when_actor_holds_permission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Actor holds the permission → passes the escalation gate and continues."""
    mod = _controller_module()
    _patch_actor(monkeypatch, mod, _Actor(perms={"users.manage"}, level=60))
    # Stop right after the actor check: permission lookup returns nothing.
    monkeypatch.setattr(mod, "Permission", _model_returning(None))
    ctrl = mod.AdminUsersController()
    payload = SimpleNamespace(permission="users.manage")
    with pytest.raises(NotFoundException):
        await ctrl.grant_permission(5, payload, _request())


# ─── revoke_permission ────────────────────────────────────────────────────


async def test_revoke_permission_blocks_when_actor_lacks_permission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _controller_module()
    _patch_actor(monkeypatch, mod, _Actor(perms=set(), level=60))
    ctrl = mod.AdminUsersController()
    with pytest.raises(AuthorizationException):
        await ctrl.revoke_permission(5, "users.manage", _request())


# ─── revoke_role ──────────────────────────────────────────────────────────


async def test_revoke_role_blocks_when_actor_level_below_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _controller_module()
    _patch_actor(monkeypatch, mod, _Actor(perms={"roles.manage"}, level=40))

    async def fake_role_level(_name: str) -> int:
        return 100

    monkeypatch.setattr(mod, "role_level", fake_role_level)
    ctrl = mod.AdminUsersController()
    with pytest.raises(AuthorizationException):
        await ctrl.revoke_role(5, "super_admin", _request())


async def test_revoke_role_allows_when_actor_level_sufficient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Actor outranks the role → passes the level gate and continues."""
    mod = _controller_module()
    _patch_actor(monkeypatch, mod, _Actor(perms={"roles.manage"}, level=100))

    async def fake_role_level(_name: str) -> int:
        return 60

    monkeypatch.setattr(mod, "role_level", fake_role_level)
    monkeypatch.setattr(mod, "User", _model_returning(None))
    ctrl = mod.AdminUsersController()
    with pytest.raises(NotFoundException):
        await ctrl.revoke_role(5, "catalog_manager", _request())


# ─── lifecycle outrank guards (suspend / unsuspend / delete / restore) ─────


class _Target:
    id = 5


def _user_model(target: Any) -> type:
    class _Query:
        async def first(self) -> Any:
            return target

    class _Model:
        id = 0

        @classmethod
        def where(cls, *_a: Any, **_k: Any) -> Any:
            return _Query()

        @classmethod
        def with_trashed(cls) -> type:
            return cls

    return _Model


def _patch_target_level(monkeypatch: pytest.MonkeyPatch, mod: ModuleType, level: int) -> None:
    async def fake_highest_role_level(_user: Any) -> int:
        return level

    monkeypatch.setattr(mod, "highest_role_level", fake_highest_role_level)


@pytest.mark.parametrize("action", ["suspend", "unsuspend", "destroy", "restore"])
async def test_lifecycle_blocks_when_target_outranks_actor(
    monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    mod = _controller_module()
    _patch_actor(monkeypatch, mod, _Actor(perms={"users.manage"}, level=80))
    monkeypatch.setattr(mod, "User", _user_model(_Target()))
    _patch_target_level(monkeypatch, mod, 100)
    ctrl = mod.AdminUsersController()
    with pytest.raises(AuthorizationException):
        await getattr(ctrl, action)(5, _request())


async def test_force_destroy_blocks_when_target_outranks_actor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _controller_module()

    async def fake_require_role_level(_request: Any, _perm: str, _level: int) -> Any:
        return _Actor(perms={"users.manage"}, level=80)

    monkeypatch.setattr(mod, "require_role_level", fake_require_role_level)
    monkeypatch.setattr(mod, "User", _user_model(_Target()))
    _patch_target_level(monkeypatch, mod, 100)
    ctrl = mod.AdminUsersController()
    with pytest.raises(AuthorizationException):
        await ctrl.force_destroy(5, _request())


async def test_suspend_allows_when_actor_outranks_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Actor outranks the target → passes the guard and reaches the service."""
    mod = _controller_module()
    _patch_actor(monkeypatch, mod, _Actor(perms={"users.manage"}, level=100))
    monkeypatch.setattr(mod, "User", _user_model(_Target()))
    _patch_target_level(monkeypatch, mod, 80)

    async def reached_service(_user_id: int) -> Any:
        raise RuntimeError("reached service")

    monkeypatch.setattr(mod.users, "suspend", reached_service)
    ctrl = mod.AdminUsersController()
    with pytest.raises(RuntimeError, match="reached service"):
        await ctrl.suspend(5, _request())


# ─── role/permission mutators also enforce the outrank guard ───────────────
# The actor-level / actor-permission gate isn't enough: a level-80 actor that
# clears it must still not touch a level-100 target (OWASP A01).


async def test_assign_role_blocks_when_target_outranks_actor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _controller_module()
    _patch_actor(monkeypatch, mod, _Actor(perms={"roles.manage"}, level=80))

    async def fake_role_level(_name: str) -> int:
        return 60

    monkeypatch.setattr(mod, "role_level", fake_role_level)
    monkeypatch.setattr(mod, "User", _user_model(_Target()))
    monkeypatch.setattr(mod, "Role", _model_returning(SimpleNamespace()))
    _patch_target_level(monkeypatch, mod, 100)
    ctrl = mod.AdminUsersController()
    with pytest.raises(AuthorizationException, match="outranks"):
        await ctrl.assign_role(5, SimpleNamespace(role="catalog_manager"), _request())


async def test_revoke_role_blocks_when_target_outranks_actor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _controller_module()
    _patch_actor(monkeypatch, mod, _Actor(perms={"roles.manage"}, level=80))

    async def fake_role_level(_name: str) -> int:
        return 60

    monkeypatch.setattr(mod, "role_level", fake_role_level)
    monkeypatch.setattr(mod, "User", _user_model(_Target()))
    _patch_target_level(monkeypatch, mod, 100)
    ctrl = mod.AdminUsersController()
    with pytest.raises(AuthorizationException, match="outranks"):
        await ctrl.revoke_role(5, "catalog_manager", _request())


async def test_grant_permission_blocks_when_target_outranks_actor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _controller_module()
    _patch_actor(monkeypatch, mod, _Actor(perms={"roles.manage", "users.manage"}, level=80))
    monkeypatch.setattr(mod, "Permission", _model_returning(SimpleNamespace()))
    monkeypatch.setattr(mod, "User", _user_model(_Target()))
    _patch_target_level(monkeypatch, mod, 100)
    ctrl = mod.AdminUsersController()
    with pytest.raises(AuthorizationException, match="outranks"):
        await ctrl.grant_permission(5, SimpleNamespace(permission="users.manage"), _request())


async def test_revoke_permission_blocks_when_target_outranks_actor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _controller_module()
    _patch_actor(monkeypatch, mod, _Actor(perms={"roles.manage", "users.manage"}, level=80))
    monkeypatch.setattr(mod, "Permission", _model_returning(SimpleNamespace()))
    monkeypatch.setattr(mod, "User", _user_model(_Target()))
    _patch_target_level(monkeypatch, mod, 100)
    ctrl = mod.AdminUsersController()
    with pytest.raises(AuthorizationException, match="outranks"):
        await ctrl.revoke_permission(5, "users.manage", _request())
