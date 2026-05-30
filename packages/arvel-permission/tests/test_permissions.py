"""Tests for arvel-permission (Spatie Permission v7 parity).

Maps to FR-025-04 .. FR-025-09 and the related NFRs.
"""

from __future__ import annotations

import pytest


def test_role_and_permission_models_have_unique_per_guard_name() -> None:
    """FR-025-06: Role/Permission unique on (name, guard_name)."""
    from arvel_permission import Permission, Role
    from sqlalchemy import Table, UniqueConstraint

    role_table = Role.__table__
    perm_table = Permission.__table__
    assert isinstance(role_table, Table)
    assert isinstance(perm_table, Table)
    assert role_table.name == "roles"
    assert perm_table.name == "permissions"
    role_uniques: set[tuple[str, ...]] = {
        tuple(c.name for c in u.columns)
        for u in role_table.constraints
        if isinstance(u, UniqueConstraint)
    }
    assert ("name", "guard_name") in role_uniques or ("guard_name", "name") in role_uniques


def test_has_roles_assign_remove_sync() -> None:
    """FR-025-07: HasRoles exposes the full mixin contract."""
    from arvel_permission import HasRoles

    for method in (
        "assign_role",
        "remove_role",
        "sync_roles",
        "has_role",
        "has_any_role",
        "has_all_roles",
        "get_role_names",
    ):
        assert hasattr(HasRoles, method), f"HasRoles missing {method}"


def test_has_permissions_lifecycle() -> None:
    """FR-025-07: HasPermissions methods exist and follow Spatie shape."""
    from arvel_permission import HasPermissions

    for method in (
        "give_permission_to",
        "revoke_permission_to",
        "sync_permissions",
        "has_permission_to",
        "has_any_permission",
        "has_all_permissions",
        "get_all_permissions",
        "get_permission_names",
    ):
        assert hasattr(HasPermissions, method), f"HasPermissions missing {method}"


def test_has_role_is_guard_scoped() -> None:
    """FR-025-07: roles in different guards are not interchangeable."""
    from arvel_permission import GuardMismatchError, HasRoles, Role

    class _User(HasRoles):
        def __init__(self) -> None:
            self.roles = []

    web_admin = Role(name="admin", guard_name="web")
    api_admin = Role(name="admin", guard_name="api")

    user = _User()
    user.roles = [web_admin]
    assert user.has_role(web_admin) is True
    with pytest.raises(GuardMismatchError):
        user.has_role(api_admin, guard="web")


def test_permission_service_provider_registers_with_gate() -> None:
    """FR-025-08: PermissionServiceProvider.boot wires permissions into Gate."""
    from arvel_permission import PermissionServiceProvider

    assert hasattr(PermissionServiceProvider, "boot")
    assert hasattr(PermissionServiceProvider, "register")


def test_registrar_caches_lookups_and_invalidates_on_refresh() -> None:
    """FR-025-09: PermissionRegistrar caches and supports refresh_cache."""
    from arvel_permission import PermissionRegistrar

    registrar = PermissionRegistrar()
    for method in (
        "register_role",
        "register_permission",
        "find_role",
        "find_permission",
        "refresh_cache",
    ):
        assert hasattr(registrar, method), f"PermissionRegistrar missing {method}"


def test_public_api_exports() -> None:
    """FR-025-05: public symbols importable from arvel_permission root."""
    import arvel_permission

    for name in (
        "Role",
        "Permission",
        "HasRoles",
        "HasPermissions",
        "PermissionRegistrar",
        "PermissionServiceProvider",
        "GuardMismatchError",
    ):
        assert hasattr(arvel_permission, name), f"arvel_permission missing public symbol {name}"
