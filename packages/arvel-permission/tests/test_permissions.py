"""Core API surface checks for HasRoles and HasPermissions."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import ClassVar

import pytest
import pytest_asyncio
from arvel.database.columns import id_
from arvel.database.model import Model
from arvel.database.orm import MorphToMany
from arvel.database.session import use_session
from arvel_permission.models import Role, model_has_roles
from arvel_permission.traits import HasRoles
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


class _GuardUser(Model, HasRoles):
    __tablename__ = "users_guard_scope"
    id: int = id_(init=False)
    default_guard_name: ClassVar[str] = "web"

    roles: ClassVar[MorphToMany[Role]] = MorphToMany(
        Role, table=model_has_roles, name="model", related_key="role_id"
    )


@pytest_asyncio.fixture()
async def session_factory(
    async_engine: AsyncEngine,
) -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    yield async_sessionmaker(async_engine, expire_on_commit=False)


def test_role_and_permission_models_have_unique_per_guard_name() -> None:
    """Role and Permission are unique on (name, guard_name)."""
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
    """HasRoles exposes assign/remove/sync and has_* helpers."""
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
    """HasPermissions exposes the give/revoke/sync/has_* surface."""
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


@pytest.mark.asyncio
async def test_has_role_is_guard_scoped(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Roles in different guards are not interchangeable."""
    from arvel_permission import GuardMismatchError

    async with session_factory() as session, use_session(session):
        web_admin = Role(name="admin", guard_name="web")
        api_admin = Role(name="admin", guard_name="api")
        user = _GuardUser()
        session.add_all([web_admin, api_admin, user])
        await session.flush()

        await user.assign_role(web_admin)
        assert await user.has_role(web_admin) is True
        with pytest.raises(GuardMismatchError):
            await user.has_role(api_admin, guard="web")


def test_permission_service_provider_registers_with_gate() -> None:
    """PermissionServiceProvider.boot wires permissions into Gate."""
    from arvel_permission import PermissionServiceProvider

    assert hasattr(PermissionServiceProvider, "boot")
    assert hasattr(PermissionServiceProvider, "register")


def test_registrar_caches_lookups_and_invalidates_on_refresh() -> None:
    """PermissionRegistrar caches lookups and supports refresh_cache."""
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
    """Public symbols are importable from the arvel_permission root."""
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
