"""QA-Pre tests for WI-arvel-045 — arvel-permission Spatie v7 parity gaps.

All tests are written RED. They fail until Stage 3b (Execution) implements the code.
Maps to FR-045-01 through FR-045-13.
"""

from __future__ import annotations

import enum
from typing import Never

import pytest
from arvel_permission.models import Role
from sqlalchemy.ext.asyncio import AsyncSession

# ── FR-045-01: Composite PK on pivot tables ───────────────────────────────────


def test_model_has_roles_has_no_surrogate_id() -> None:
    """Pivot must not have a surrogate 'id' column."""
    from arvel_permission.models import ModelHasRole

    cols = {c.name for c in ModelHasRole.__table__.columns}
    assert "id" not in cols, "ModelHasRole must use composite PK, not surrogate id"


def test_model_has_permissions_has_no_surrogate_id() -> None:
    from arvel_permission.models import ModelHasPermission

    cols = {c.name for c in ModelHasPermission.__table__.columns}
    assert "id" not in cols, "ModelHasPermission must use composite PK, not surrogate id"


def test_model_has_roles_has_no_timestamps() -> None:
    from arvel_permission.models import ModelHasRole

    cols = {c.name for c in ModelHasRole.__table__.columns}
    assert "created_at" not in cols
    assert "updated_at" not in cols


def test_model_has_permissions_has_no_timestamps() -> None:
    from arvel_permission.models import ModelHasPermission

    cols = {c.name for c in ModelHasPermission.__table__.columns}
    assert "created_at" not in cols
    assert "updated_at" not in cols


def test_model_has_roles_composite_pk() -> None:
    from arvel_permission.models import ModelHasRole

    pk_cols = {c.name for c in ModelHasRole.__table__.primary_key}
    assert pk_cols == {"role_id", "model_id", "model_type"}


def test_model_has_permissions_composite_pk() -> None:
    from arvel_permission.models import ModelHasPermission

    pk_cols = {c.name for c in ModelHasPermission.__table__.primary_key}
    assert pk_cols == {"permission_id", "model_id", "model_type"}


# ── FR-045-02: Narrow except in traits ────────────────────────────────────────


def test_has_permission_to_propagates_attribute_error() -> None:
    """Non-MissingGreenlet errors must not be swallowed."""
    from arvel_permission.traits import HasPermissions

    class _BrokenRole:
        guard_name = "web"

        @property
        def permissions(self) -> Never:
            raise AttributeError("broken relationship")

    class _User(HasPermissions):
        default_guard_name = "web"

        def __init__(self) -> None:
            self.permissions = []

    user = _User()
    object.__setattr__(user, "roles", [_BrokenRole()])

    with pytest.raises(AttributeError):
        user.has_permission_to("edit articles")


# ── FR-045-03: PermissionConfig cache_enabled wired ───────────────────────────


def test_cache_enabled_false_bypasses_in_memory_cache() -> None:
    from arvel_permission.config import PermissionConfig
    from arvel_permission.service import PermissionRegistrar

    config = PermissionConfig(cache_enabled=False)
    reg = PermissionRegistrar(config=config)
    reg.register_role("editor")
    # With cache_enabled=False the second call must still return a role
    # but must NOT return the cached instance (it goes through the lookup path)
    r1 = reg.register_role("editor")
    r2 = reg.register_role("editor")
    # The important thing is it doesn't raise; behaviour detail:
    assert r1.name == "editor"
    assert r2.name == "editor"
    # Cache must not be populated
    assert reg.find_role("editor") is None


# ── FR-045-04: HasPermissions on Role ────────────────────────────────────────


def test_role_has_give_permission_to() -> None:
    from arvel_permission.models import Role

    assert hasattr(Role, "give_permission_to"), "Role must have give_permission_to"
    assert hasattr(Role, "has_permission_to"), "Role must have has_permission_to"
    assert hasattr(Role, "revoke_permission_to"), "Role must have revoke_permission_to"
    assert hasattr(Role, "sync_permissions"), "Role must have sync_permissions"


def test_role_permissions_relationship_is_not_viewonly() -> None:
    from arvel_permission.models import Role
    from sqlalchemy.orm import RelationshipProperty

    rel = Role.__mapper__.relationships["permissions"]
    assert isinstance(rel, RelationshipProperty)
    assert rel.viewonly is False, "Role.permissions must be writable (viewonly=False)"


def test_role_give_permission_to_in_memory() -> None:
    from arvel_permission.models import Permission, Role

    role = Role(name="editor", guard_name="web")
    role.permissions = []
    perm = Permission(name="edit articles", guard_name="web")
    role.give_permission_to(perm)
    assert role.has_permission_to("edit articles")


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
    from arvel_permission.traits import HasPermissions

    assert hasattr(HasPermissions, "get_direct_permissions")
    assert hasattr(HasPermissions, "get_permissions_via_roles")


def test_get_direct_permissions_returns_only_direct() -> None:
    from arvel_permission.models import Permission, Role
    from arvel_permission.traits import HasPermissions, HasRoles

    class _User(HasRoles, HasPermissions):
        default_guard_name = "web"

        def __init__(self) -> None:
            self.roles = []
            self.permissions = []

    user = _User()
    direct_perm = Permission(name="edit articles", guard_name="web")
    role_perm = Permission(name="publish articles", guard_name="web")
    role = Role(name="editor", guard_name="web")
    role.permissions = [role_perm]
    user.permissions = [direct_perm]
    user.roles = [role]

    direct = user.get_direct_permissions()
    via_roles = user.get_permissions_via_roles()

    assert any(p.name == "edit articles" for p in direct)
    assert not any(p.name == "publish articles" for p in direct)
    assert any(p.name == "publish articles" for p in via_roles)
    assert not any(p.name == "edit articles" for p in via_roles)


# ── FR-045-09: Package-root exports + convenience methods ────────────────────


def test_factory_functions_in_all() -> None:
    import arvel_permission

    assert hasattr(arvel_permission, "make_roles_relationship")
    assert hasattr(arvel_permission, "make_permissions_relationship")


def test_role_find_by_name_exists() -> None:
    from arvel_permission.models import Role

    assert hasattr(Role, "find_by_name"), "Role.find_by_name must exist"
    assert hasattr(Role, "find_by_id"), "Role.find_by_id must exist"
    assert hasattr(Role, "find_or_create"), "Role.find_or_create must exist"


def test_permission_find_by_name_exists() -> None:
    from arvel_permission.models import Permission

    assert hasattr(Permission, "find_by_name")
    assert hasattr(Permission, "find_by_id")
    assert hasattr(Permission, "find_or_create")


# ── FR-045-10: sync_roles detach parameter ───────────────────────────────────


def test_sync_roles_detach_false_appends() -> None:
    from arvel_permission.models import Role
    from arvel_permission.traits import HasRoles

    class _User(HasRoles):
        default_guard_name = "web"

        def __init__(self) -> None:
            self.roles = []

    user = _User()
    user.roles = [Role(name="author", guard_name="web")]
    user.sync_roles(["editor"], detach=False)
    names = user.get_role_names()
    assert "author" in names
    assert "editor" in names


def test_sync_roles_detach_true_replaces() -> None:
    from arvel_permission.models import Role
    from arvel_permission.traits import HasRoles

    class _User(HasRoles):
        default_guard_name = "web"

        def __init__(self) -> None:
            self.roles = []

    user = _User()
    user.roles = [Role(name="author", guard_name="web")]
    user.sync_roles(["editor"], detach=True)
    names = user.get_role_names()
    assert "author" not in names
    assert "editor" in names


def test_assign_role_accepts_str_enum() -> None:
    """assign_role must accept StrEnum values."""
    from arvel_permission.traits import HasRoles

    class MyRole(enum.StrEnum):
        EDITOR = "editor"

    class _User(HasRoles):
        default_guard_name = "web"

        def __init__(self) -> None:
            self.roles = []

    user = _User()
    user.assign_role(MyRole.EDITOR)
    assert user.has_role("editor")


# ── FR-045-11: Wildcard permissions ──────────────────────────────────────────


def test_wildcard_permission_matches_sub_permission() -> None:
    from arvel_permission.models import Permission
    from arvel_permission.traits import HasPermissions

    class _User(HasPermissions):
        default_guard_name = "web"

        def __init__(self) -> None:
            self.permissions = []

    user = _User()
    user.permissions = [Permission(name="edit.*", guard_name="web")]
    object.__setattr__(user, "roles", [])
    assert user.has_permission_to("edit.articles")
    assert not user.has_permission_to("delete.articles")


def test_wildcard_star_matches_everything() -> None:
    from arvel_permission.models import Permission
    from arvel_permission.traits import HasPermissions

    class _User(HasPermissions):
        default_guard_name = "web"

        def __init__(self) -> None:
            self.permissions = []

    user = _User()
    user.permissions = [Permission(name="*", guard_name="web")]
    object.__setattr__(user, "roles", [])
    assert user.has_permission_to("anything.at.all")


# ── FR-045-12: Integration tests (behavioral) ────────────────────────────────


@pytest.mark.asyncio
async def test_assign_role_roundtrip(async_session: AsyncSession, editor_role: Role) -> None:
    """Assigning a role in DB and reloading must show the role on the user."""
    from arvel_permission.models import ModelHasRole
    from sqlalchemy import select

    pivot = ModelHasRole(role_id=editor_role.id, model_type="User", model_id="1", guard_name="web")
    async_session.add(pivot)
    await async_session.flush()

    result = await async_session.execute(
        select(ModelHasRole).where(ModelHasRole.model_type == "User", ModelHasRole.model_id == "1")
    )
    rows = result.scalars().all()
    assert len(rows) == 1
    assert rows[0].role_id == editor_role.id


@pytest.mark.asyncio
async def test_duplicate_pivot_row_raises(async_session: AsyncSession, editor_role: Role) -> None:
    """Inserting the same role for the same model twice must raise IntegrityError."""
    from arvel_permission.models import ModelHasRole
    from sqlalchemy.exc import IntegrityError

    pivot1 = ModelHasRole(role_id=editor_role.id, model_type="User", model_id="1", guard_name="web")
    pivot2 = ModelHasRole(role_id=editor_role.id, model_type="User", model_id="1", guard_name="web")
    async_session.add(pivot1)
    await async_session.flush()
    async_session.expunge(pivot1)
    async_session.add(pivot2)
    with pytest.raises(IntegrityError):
        await async_session.flush()


@pytest.mark.asyncio
async def test_a_register_role_creates_db_row(async_session: AsyncSession) -> None:
    from arvel_permission.service import PermissionRegistrar

    reg = PermissionRegistrar(session=async_session)
    role = await reg.a_register_role("admin")
    assert role.id is not None
    role2 = await reg.a_register_role("admin")
    assert role2.id == role.id


@pytest.mark.asyncio
async def test_a_register_role_twice_returns_same_id(async_session: AsyncSession) -> None:
    from arvel_permission.service import PermissionRegistrar

    reg = PermissionRegistrar(session=async_session)
    r1 = await reg.a_register_role("moderator")
    r2 = await reg.a_register_role("moderator")
    assert r1.id == r2.id


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
    from arvel_permission.models import Role as _Role

    found = await _Role.find_by_name("editor", session=async_session)
    assert found is not None
    assert found.id == editor_role.id


@pytest.mark.asyncio
async def test_find_by_name_raises_role_does_not_exist(async_session: AsyncSession) -> None:
    from arvel_permission.exceptions import RoleDoesNotExist
    from arvel_permission.models import Role as _Role

    with pytest.raises(RoleDoesNotExist):
        await _Role.find_by_name("nonexistent", session=async_session)


@pytest.mark.asyncio
async def test_find_or_create_creates_when_absent(async_session: AsyncSession) -> None:
    from arvel_permission.models import Role as _Role

    role = await _Role.find_or_create("new-role", session=async_session)
    assert role.name == "new-role"
    assert role.id is not None


@pytest.mark.asyncio
async def test_find_or_create_returns_existing(
    async_session: AsyncSession, editor_role: Role
) -> None:
    from arvel_permission.models import Role as _Role

    role = await _Role.find_or_create("editor", session=async_session)
    assert role.id == editor_role.id


# ── FR-045-13: Stale cleanup ──────────────────────────────────────────────────


def test_no_importorskip_in_test_permissions() -> None:
    import pathlib

    src = pathlib.Path(__file__).parent / "test_permissions.py"
    if not src.exists():
        pytest.skip("test_permissions.py not found")
    content = src.read_text()
    assert "pytest.importorskip" not in content, (
        "pytest.importorskip must be removed from test_permissions.py"
    )


def test_fake_int_model_has_table_attribute() -> None:
    import importlib.util
    import pathlib

    src = pathlib.Path(__file__).parent / "test_integer_pk.py"
    if not src.exists():
        pytest.skip("test_integer_pk.py not found")
    spec = importlib.util.spec_from_file_location("test_integer_pk", src)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    fake = getattr(mod, "_FakeIntModel", None)
    assert fake is not None
    assert hasattr(fake, "__table__"), "_FakeIntModel must have a __table__ attribute after fix"
