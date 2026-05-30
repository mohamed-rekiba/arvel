"""Spatie v7 parity for arvel-permission, on the async ``MorphToMany`` core.

Maps to FR-045-01 .. FR-045-13. The pivots are plain Core ``Table``s; hosts
grant roles/permissions through async accessors, so the behavioral tests run
against a real session.
"""

from __future__ import annotations

import enum
from collections.abc import AsyncGenerator
from typing import ClassVar

import pytest
import pytest_asyncio
from arvel.database.columns import id_
from arvel.database.model import Model
from arvel.database.orm import BelongsToMany, MorphToMany
from arvel.database.session import use_session
from arvel_permission.models import (
    Permission,
    Role,
    model_has_permissions,
    model_has_roles,
)
from arvel_permission.traits import HasPermissions, HasRoles
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped


class _P045User(Model, HasRoles, HasPermissions):
    __tablename__ = "users_045"
    id: Mapped[int] = id_(init=False)
    default_guard_name: str = "web"

    roles: ClassVar[MorphToMany[Role]] = MorphToMany(
        Role, table=model_has_roles, name="model", related_key="role_id"
    )
    permissions: ClassVar[MorphToMany[Permission]] = MorphToMany(
        Permission, table=model_has_permissions, name="model", related_key="permission_id"
    )


@pytest_asyncio.fixture()
async def session_factory(
    async_engine: AsyncEngine,
) -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    yield async_sessionmaker(async_engine, expire_on_commit=False)


# ── FR-045-01: Composite PK on pivot tables, no surrogate id, no timestamps ───


def test_model_has_roles_shape() -> None:
    cols = {c.name for c in model_has_roles.columns}
    assert "id" not in cols
    assert "created_at" not in cols
    assert "updated_at" not in cols
    pk_cols = {c.name for c in model_has_roles.primary_key}
    assert pk_cols == {"role_id", "model_id", "model_type"}


def test_model_has_permissions_shape() -> None:
    cols = {c.name for c in model_has_permissions.columns}
    assert "id" not in cols
    assert "created_at" not in cols
    assert "updated_at" not in cols
    pk_cols = {c.name for c in model_has_permissions.primary_key}
    assert pk_cols == {"permission_id", "model_id", "model_type"}


# ── FR-045-03: PermissionConfig cache_enabled wired ───────────────────────────


def test_cache_enabled_false_bypasses_in_memory_cache() -> None:
    from arvel_permission.config import PermissionConfig
    from arvel_permission.service import PermissionRegistrar

    config = PermissionConfig(cache_enabled=False)
    reg = PermissionRegistrar(config=config)
    reg.register_role("editor")
    r1 = reg.register_role("editor")
    r2 = reg.register_role("editor")
    assert r1.name == "editor"
    assert r2.name == "editor"
    assert reg.find_role("editor") is None


# ── FR-045-04: HasPermissions grafted onto Role ───────────────────────────────


def test_role_has_permission_methods() -> None:
    for method in (
        "give_permission_to",
        "has_permission_to",
        "revoke_permission_to",
        "sync_permissions",
    ):
        assert hasattr(Role, method), f"Role must have {method}"


def test_role_permissions_is_belongs_to_many() -> None:
    descriptor = Role.__dict__["permissions"]
    assert isinstance(descriptor, BelongsToMany)


@pytest.mark.asyncio
async def test_role_give_permission_to_db(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, use_session(session):
        role = Role(name="editor", guard_name="web")
        session.add(role)
        await session.flush()
        await role.give_permission_to("edit articles")
        await session.commit()
        assert await role.has_permission_to("edit articles")


# ── FR-045-05: Route middleware ───────────────────────────────────────────────


def test_middleware_classes_importable() -> None:
    from arvel_permission.middleware import (
        PermissionMiddleware,
        RoleMiddleware,
        RoleOrPermissionMiddleware,
    )

    assert callable(RoleMiddleware)
    assert callable(PermissionMiddleware)
    assert callable(RoleOrPermissionMiddleware)


def test_middleware_exported_from_package() -> None:
    import arvel_permission

    for name in ("RoleMiddleware", "PermissionMiddleware", "RoleOrPermissionMiddleware"):
        assert hasattr(arvel_permission, name), f"arvel_permission missing {name}"


# ── FR-045-07: Typed exceptions ───────────────────────────────────────────────


def test_typed_exceptions_importable() -> None:
    from arvel_permission.exceptions import PermissionDoesNotExist, RoleDoesNotExist

    assert issubclass(RoleDoesNotExist, Exception)
    assert issubclass(PermissionDoesNotExist, Exception)


def test_typed_exceptions_in_all() -> None:
    import arvel_permission

    assert hasattr(arvel_permission, "RoleDoesNotExist")
    assert hasattr(arvel_permission, "PermissionDoesNotExist")


# ── FR-045-08: get_direct_permissions / get_permissions_via_roles ─────────────


def test_has_permissions_has_direct_and_via_role_methods() -> None:
    assert hasattr(HasPermissions, "get_direct_permissions")
    assert hasattr(HasPermissions, "get_permissions_via_roles")


@pytest.mark.asyncio
async def test_direct_vs_via_roles(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, use_session(session):
        role = Role(name="editor", guard_name="web")
        user = _P045User()
        session.add_all([role, user])
        await session.flush()

        await role.give_permission_to("publish articles")
        await user.give_permission_to("edit articles")
        await user.assign_role(role)
        await session.commit()

        direct = await user.get_direct_permissions()
        via_roles = await user.get_permissions_via_roles()

        assert any(p.name == "edit articles" for p in direct)
        assert not any(p.name == "publish articles" for p in direct)
        assert any(p.name == "publish articles" for p in via_roles)
        assert not any(p.name == "edit articles" for p in via_roles)


# ── FR-045-09: find_by_name / find_by_id / find_or_create ─────────────────────


def test_role_find_helpers_exist() -> None:
    assert hasattr(Role, "find_by_name")
    assert hasattr(Role, "find_by_id")
    assert hasattr(Role, "find_or_create")


def test_permission_find_helpers_exist() -> None:
    assert hasattr(Permission, "find_by_name")
    assert hasattr(Permission, "find_by_id")
    assert hasattr(Permission, "find_or_create")


# ── FR-045-10: sync_roles detach parameter + StrEnum support ──────────────────


@pytest.mark.asyncio
async def test_sync_roles_detach_false_appends(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, use_session(session):
        user = _P045User()
        session.add(user)
        await session.flush()
        await user.assign_role("author")
        await user.sync_roles(["editor"], detach=False)
        names = await user.get_role_names()
        assert "author" in names
        assert "editor" in names


@pytest.mark.asyncio
async def test_sync_roles_detach_true_replaces(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, use_session(session):
        user = _P045User()
        session.add(user)
        await session.flush()
        await user.assign_role("author")
        await user.sync_roles(["editor"], detach=True)
        names = await user.get_role_names()
        assert "author" not in names
        assert "editor" in names


@pytest.mark.asyncio
async def test_assign_role_accepts_str_enum(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    class MyRole(enum.StrEnum):
        EDITOR = "editor"

    async with session_factory() as session, use_session(session):
        user = _P045User()
        session.add(user)
        await session.flush()
        await user.assign_role(MyRole.EDITOR)
        assert await user.has_role("editor")


# ── FR-045-11: Wildcard permissions ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_wildcard_permission_matches_sub_permission(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, use_session(session):
        user = _P045User()
        session.add(user)
        await session.flush()
        await user.give_permission_to("edit.*")
        assert await user.has_permission_to("edit.articles")
        assert not await user.has_permission_to("delete.articles")


@pytest.mark.asyncio
async def test_wildcard_star_matches_everything(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, use_session(session):
        user = _P045User()
        session.add(user)
        await session.flush()
        await user.give_permission_to("*")
        assert await user.has_permission_to("anything.at.all")


# ── FR-045-12: Behavioral round-trips ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_assign_role_roundtrip(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as s1, use_session(s1):
        user = _P045User()
        s1.add(user)
        await s1.flush()
        await user.assign_role("editor")
        await s1.commit()
        user_id = user.id

    async with session_factory() as s2, use_session(s2):
        reloaded = await _P045User.where(_P045User.id == user_id).first()
        assert reloaded is not None
        assert [r.name for r in await reloaded.roles.all()] == ["editor"]


@pytest.mark.asyncio
async def test_assign_role_is_idempotent(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, use_session(session):
        user = _P045User()
        session.add(user)
        await session.flush()
        await user.assign_role("editor")
        await user.assign_role("editor")
        assert await user.get_role_names() == ["editor"]


@pytest.mark.asyncio
async def test_a_register_role_creates_db_row(async_session: AsyncSession) -> None:
    from arvel_permission.service import PermissionRegistrar

    reg = PermissionRegistrar(session=async_session)
    role = await reg.a_register_role("admin")
    assert role.id is not None
    role2 = await reg.a_register_role("admin")
    assert role2.id == role.id


@pytest.mark.asyncio
async def test_refresh_cache_clears_in_memory_state(async_session: AsyncSession) -> None:
    from arvel_permission.service import PermissionRegistrar

    reg = PermissionRegistrar(session=async_session)
    await reg.a_register_role("editor")
    assert reg.find_role("editor") is not None
    reg.refresh_cache()
    assert reg.find_role("editor") is None


@pytest.mark.asyncio
async def test_find_by_name_returns_role(async_session: AsyncSession, editor_role: Role) -> None:
    found = await Role.find_by_name("editor", session=async_session)
    assert found is not None
    assert found.id == editor_role.id


@pytest.mark.asyncio
async def test_find_by_name_raises_role_does_not_exist(async_session: AsyncSession) -> None:
    from arvel_permission.exceptions import RoleDoesNotExist

    with pytest.raises(RoleDoesNotExist):
        await Role.find_by_name("nonexistent", session=async_session)


@pytest.mark.asyncio
async def test_find_or_create_creates_when_absent(async_session: AsyncSession) -> None:
    role = await Role.find_or_create("new-role", session=async_session)
    assert role.name == "new-role"
    assert role.id is not None


@pytest.mark.asyncio
async def test_find_or_create_returns_existing(
    async_session: AsyncSession, editor_role: Role
) -> None:
    role = await Role.find_or_create("editor", session=async_session)
    assert role.id == editor_role.id
