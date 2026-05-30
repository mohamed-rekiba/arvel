"""QA-Pre tests for WI-arvel-051 — arvel-permission post-045 parity fixes.

All tests are written RED. They fail until Stage 3b (Execution) implements the fixes.
Maps to FR-051-01 through FR-051-10.
"""

from __future__ import annotations

from typing import Any

import pytest
from arvel.database.columns import id_
from arvel.database.model import Model
from arvel_permission.traits import (
    HasPermissions,
    HasRoles,
    make_permissions_relationship,
    make_roles_relationship,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped


def _passthrough(r: Any) -> Any:
    """call_next stub for middleware tests — returns the request unchanged."""
    return r


# Module-level model for query-scope tests so SQLAlchemy can resolve Mapped[int]
# inside the declarative scan (de-stringification needs module-level Mapped import).
class _QUser(Model, HasRoles, HasPermissions):
    __tablename__ = "users_051_query_scope"
    id: Mapped[int] = id_(init=False)
    default_guard_name: str = "web"


_QUser.roles = make_roles_relationship(lambda: _QUser, model_type="_QUser")
_QUser.permissions = make_permissions_relationship(lambda: _QUser, model_type="_QUser")


# ── FR-051-01: Wire PermissionConfig.wildcard_enabled to has_permission_to ────


def test_wildcard_config_wire_disables_matching_globally() -> None:
    """FR-051-01a/b/c: Setting wildcard_enabled=False prevents wildcard matching."""
    from arvel_permission.config import PermissionConfig
    from arvel_permission.models import Permission
    from arvel_permission.traits import HasPermissions, apply_wildcard_config

    config = PermissionConfig(wildcard_enabled=False)
    original = HasPermissions.wildcard_permission
    try:
        apply_wildcard_config(config)
        assert HasPermissions.wildcard_permission is False

        class _User(HasPermissions):
            default_guard_name = "web"

            def __init__(self) -> None:
                self.permissions = []

        user = _User()
        user.permissions = [Permission(name="edit.*", guard_name="web")]
        assert user.has_permission_to("edit.articles") is False, (
            "wildcard_enabled=False must disable global wildcard matching"
        )
    finally:
        HasPermissions.wildcard_permission = original


def test_wildcard_config_wire_model_level_override_wins() -> None:
    """FR-051-01b: Model-level wildcard_permission=True overrides global False."""
    from arvel_permission.config import PermissionConfig
    from arvel_permission.models import Permission
    from arvel_permission.traits import HasPermissions, apply_wildcard_config

    config = PermissionConfig(wildcard_enabled=False)
    original = HasPermissions.wildcard_permission
    try:
        apply_wildcard_config(config)

        class _OverrideUser(HasPermissions):
            default_guard_name = "web"
            wildcard_permission: bool = True

            def __init__(self) -> None:
                self.permissions = []

        user = _OverrideUser()
        user.permissions = [Permission(name="edit.*", guard_name="web")]
        assert user.has_permission_to("edit.articles") is True, (
            "instance-level wildcard_permission=True must still match"
        )
    finally:
        HasPermissions.wildcard_permission = original


# ── FR-051-02: RoleHasPermission composite PK (not unique constraint) ─────────


def test_role_has_permissions_migration_uses_composite_pk() -> None:
    """FR-051-02a: Migration must create a composite PK, not a unique constraint."""
    import inspect

    from arvel_permission.migrations.create_permission_tables import up

    source = inspect.getsource(up)
    assert '"role_has_permissions_unique"' not in source, (
        "Migration must not use a named unique constraint on role_has_permissions; "
        "use composite PK (.primary() on each column) instead."
    )


def test_role_has_permissions_orm_declares_composite_pk() -> None:
    """FR-051-02c: ORM model must declare composite PK."""
    from arvel_permission.models import RoleHasPermission

    pk_cols = {c.name for c in RoleHasPermission.__table__.primary_key}
    assert pk_cols == {"permission_id", "role_id"}, (
        f"RoleHasPermission PK should be (permission_id, role_id), got {pk_cols}"
    )


# ── FR-051-03: Middleware guard forwarding ────────────────────────────────────


@pytest.mark.asyncio
async def test_role_middleware_forwards_guard_to_has_role() -> None:
    """FR-051-03a: RoleMiddleware passes guard to user.has_role."""
    from arvel_permission.exceptions import UnauthorizedException
    from arvel_permission.middleware import RoleMiddleware

    captured: dict[str, str | None] = {"guard": None}

    class _User:
        def has_role(self, role: str, *, guard: str | None = None) -> bool:
            captured["guard"] = guard
            return False

    class _Request:
        user = _User()

    mw = RoleMiddleware("admin", guard="api")
    with pytest.raises(UnauthorizedException):
        await mw(_Request(), call_next=_passthrough)
    assert captured["guard"] == "api", (
        f"RoleMiddleware must forward guard='api', got guard={captured['guard']!r}"
    )


@pytest.mark.asyncio
async def test_permission_middleware_forwards_guard() -> None:
    """FR-051-03b: PermissionMiddleware passes guard to user.has_permission_to."""
    from arvel_permission.exceptions import UnauthorizedException
    from arvel_permission.middleware import PermissionMiddleware

    captured: dict[str, str | None] = {"guard": None}

    class _User:
        def has_permission_to(self, perm: str, *, guard: str | None = None) -> bool:
            captured["guard"] = guard
            return False

    class _Request:
        user = _User()

    mw = PermissionMiddleware("edit", guard="api")
    with pytest.raises(UnauthorizedException):
        await mw(_Request(), call_next=_passthrough)
    assert captured["guard"] == "api", (
        f"PermissionMiddleware must forward guard='api', got {captured['guard']!r}"
    )


# ── FR-051-04: Middleware pipe-separated OR syntax ────────────────────────────


@pytest.mark.asyncio
async def test_role_middleware_pipe_or_grants_on_second_match() -> None:
    """FR-051-04a: RoleMiddleware('admin|manager') grants when user has 'manager'."""
    from arvel_permission.middleware import RoleMiddleware

    class _User:
        def has_role(self, role: str, *, guard: str | None = None) -> bool:
            return role == "manager"

    sentinel: list[Any] = []

    async def _next(r: Any) -> str:
        sentinel.append("ok")
        return "ok"

    class _Request:
        user = _User()

    mw = RoleMiddleware("admin|manager")
    await mw(_Request(), call_next=_next)
    assert sentinel, "Pipe OR 'admin|manager' must pass when user has 'manager'"


@pytest.mark.asyncio
async def test_permission_middleware_pipe_or_grants_on_first_match() -> None:
    """FR-051-04b: PermissionMiddleware('publish|edit') grants on first match."""
    from arvel_permission.middleware import PermissionMiddleware

    class _User:
        def has_permission_to(self, perm: str, *, guard: str | None = None) -> bool:
            return perm == "publish"

    sentinel: list[Any] = []

    async def _next(r: Any) -> str:
        sentinel.append("ok")
        return "ok"

    class _Request:
        user = _User()

    mw = PermissionMiddleware("publish|edit")
    await mw(_Request(), call_next=_next)
    assert sentinel, "Pipe OR 'publish|edit' must pass when user has 'publish'"


@pytest.mark.asyncio
async def test_role_middleware_pipe_or_denies_when_none_match() -> None:
    """FR-051-04: Pipe OR denies when user has neither role."""
    from arvel_permission.exceptions import UnauthorizedException
    from arvel_permission.middleware import RoleMiddleware

    class _User:
        def has_role(self, role: str, *, guard: str | None = None) -> bool:
            return False

    class _Request:
        user = _User()

    mw = RoleMiddleware("admin|manager")
    with pytest.raises(UnauthorizedException) as exc_info:
        await mw(_Request(), call_next=_passthrough)
    assert exc_info.value.status_code == 403


# ── FR-051-05: Async registrar cache_enabled consistency ─────────────────────


@pytest.mark.asyncio
async def test_async_registrar_cache_disabled_does_not_cache(
    async_session: AsyncSession,
) -> None:
    """FR-051-05a/b: a_register_role with cache_enabled=False must not populate cache."""
    from arvel_permission.config import PermissionConfig
    from arvel_permission.service import PermissionRegistrar

    config = PermissionConfig(cache_enabled=False)
    reg = PermissionRegistrar(session=async_session, config=config)
    await reg.a_register_role("editor")
    assert reg.find_role("editor") is None, (
        "a_register_role must not populate cache when cache_enabled=False"
    )


@pytest.mark.asyncio
async def test_async_registrar_cache_enabled_does_cache(
    async_session: AsyncSession,
) -> None:
    """FR-051-05c: a_register_role with cache_enabled=True caches the result."""
    from arvel_permission.config import PermissionConfig
    from arvel_permission.service import PermissionRegistrar

    config = PermissionConfig(cache_enabled=True)
    reg = PermissionRegistrar(session=async_session, config=config)
    await reg.a_register_role("editor")
    assert reg.find_role("editor") is not None, "a_register_role must cache when cache_enabled=True"


# ── FR-051-06: Bidirectional Permission ↔ Role API ───────────────────────────


def test_permission_has_roles_relationship() -> None:
    """FR-051-06a: Permission must declare a 'roles' SQLAlchemy relationship."""
    from arvel_permission.models import Permission
    from sqlalchemy.orm import RelationshipProperty

    assert "roles" in Permission.__mapper__.relationships, (
        "Permission must declare a 'roles' relationship"
    )
    rel = Permission.__mapper__.relationships["roles"]
    assert isinstance(rel, RelationshipProperty)


def test_permission_has_assign_role_method() -> None:
    """FR-051-06b: Permission must have assign_role method."""
    from arvel_permission.models import Permission

    assert hasattr(Permission, "assign_role"), "Permission must have assign_role"
    assert hasattr(Permission, "remove_role"), "Permission must have remove_role"
    assert hasattr(Permission, "sync_roles"), "Permission must have sync_roles"


def test_permission_assign_role_in_memory() -> None:
    """FR-051-06b: permission.assign_role adds the role to permission.roles."""
    from arvel_permission.models import Permission, Role

    perm = Permission(name="edit articles", guard_name="web")
    perm.roles = []
    role = Role(name="editor", guard_name="web")
    perm.assign_role(role)
    assert any(r.name == "editor" for r in perm.roles), (
        "assign_role must add role to Permission.roles"
    )


def test_permission_remove_role_in_memory() -> None:
    """FR-051-06c: permission.remove_role removes the role from permission.roles."""
    from arvel_permission.models import Permission, Role

    perm = Permission(name="edit articles", guard_name="web")
    role = Role(name="editor", guard_name="web")
    perm.roles = [role]
    perm.remove_role("editor")
    assert not any(r.name == "editor" for r in perm.roles)


def test_permission_sync_roles_in_memory() -> None:
    """FR-051-06d: permission.sync_roles replaces roles wholesale."""
    from arvel_permission.models import Permission, Role

    perm = Permission(name="edit articles", guard_name="web")
    perm.roles = [Role(name="old-role", guard_name="web")]
    perm.sync_roles(["editor", "admin"])
    names = [r.name for r in perm.roles]
    assert "old-role" not in names
    assert "editor" in names
    assert "admin" in names


# ── FR-051-07: UnauthorizedException ─────────────────────────────────────────


def test_unauthorized_exception_importable() -> None:
    """FR-051-07a: UnauthorizedException must be importable from exceptions."""
    from arvel_permission.exceptions import UnauthorizedException

    assert issubclass(UnauthorizedException, Exception)


def test_unauthorized_exception_has_status_code() -> None:
    """FR-051-07b: UnauthorizedException must carry a status_code attribute."""
    from arvel_permission.exceptions import UnauthorizedException

    exc = UnauthorizedException(status_code=403)
    assert exc.status_code == 403


@pytest.mark.asyncio
async def test_role_middleware_raises_unauthorized_on_deny() -> None:
    """FR-051-07c: RoleMiddleware raises UnauthorizedException on auth failure."""
    from arvel_permission.exceptions import UnauthorizedException
    from arvel_permission.middleware import RoleMiddleware

    class _User:
        def has_role(self, role: str, *, guard: str | None = None) -> bool:
            return False

    class _Request:
        user = _User()

    mw = RoleMiddleware("admin")
    with pytest.raises(UnauthorizedException):
        await mw(_Request(), call_next=_passthrough)


@pytest.mark.asyncio
async def test_permission_middleware_raises_unauthorized_on_deny() -> None:
    """FR-051-07c: PermissionMiddleware raises UnauthorizedException on auth failure."""
    from arvel_permission.exceptions import UnauthorizedException
    from arvel_permission.middleware import PermissionMiddleware

    class _User:
        def has_permission_to(self, perm: str, *, guard: str | None = None) -> bool:
            return False

    class _Request:
        user = _User()

    mw = PermissionMiddleware("edit")
    with pytest.raises(UnauthorizedException):
        await mw(_Request(), call_next=_passthrough)


@pytest.mark.asyncio
async def test_no_user_raises_unauthorized_with_401() -> None:
    """FR-051-07b: No user raises UnauthorizedException(status_code=401)."""
    from arvel_permission.exceptions import UnauthorizedException
    from arvel_permission.middleware import RoleMiddleware

    class _Request:
        user = None

    mw = RoleMiddleware("admin")
    with pytest.raises(UnauthorizedException) as exc_info:
        await mw(_Request(), call_next=_passthrough)
    assert exc_info.value.status_code == 401


# ── FR-051-08: Wildcard subpart syntax (comma-separated segments) ─────────────


def test_wildcard_subpart_resource_action() -> None:
    """FR-051-08a: 'posts,users.create,update' matches 'posts.create'."""
    from arvel_permission.traits import matches_wildcard

    assert matches_wildcard("posts,users.create,update", "posts.create")
    assert matches_wildcard("posts,users.create,update", "users.update")
    assert not matches_wildcard("posts,users.create,update", "posts.delete")
    assert not matches_wildcard("posts,users.create,update", "roles.create")


def test_wildcard_subpart_star_action() -> None:
    """FR-051-08b: '*.create,update' matches 'articles.create' and 'roles.update'."""
    from arvel_permission.traits import matches_wildcard

    assert matches_wildcard("*.create,update", "articles.create")
    assert matches_wildcard("*.create,update", "roles.update")
    assert not matches_wildcard("*.create,update", "articles.delete")


def test_wildcard_subpart_three_segment() -> None:
    """FR-051-08c: 'posts.*.1,4,6' matches 'posts.edit.1' but not 'posts.edit.2'."""
    from arvel_permission.traits import matches_wildcard

    assert matches_wildcard("posts.*.1,4,6", "posts.edit.1")
    assert matches_wildcard("posts.*.1,4,6", "posts.view.4")
    assert not matches_wildcard("posts.*.1,4,6", "posts.edit.2")


def test_wildcard_subpart_existing_patterns_unchanged() -> None:
    """FR-051-08d: Existing '*' and 'resource.*' patterns still work."""
    from arvel_permission.traits import matches_wildcard

    assert matches_wildcard("*", "anything.at.all")
    assert matches_wildcard("edit.*", "edit.articles")
    assert not matches_wildcard("edit.*", "publish.articles")
    assert not matches_wildcard("edit.*", "edit.articles.section")


# ── FR-051-09: Model query scopes ─────────────────────────────────────────────


def test_has_roles_has_query_with_role_classmethod() -> None:
    """FR-051-09a: HasRoles must expose query_with_role classmethod."""
    from arvel_permission.traits import HasRoles

    assert hasattr(HasRoles, "query_with_role"), "HasRoles must have query_with_role"
    assert hasattr(HasRoles, "query_without_role"), "HasRoles must have query_without_role"


def test_has_permissions_has_query_with_permission_classmethod() -> None:
    """FR-051-09c: HasPermissions must expose query_with_permission classmethod."""
    from arvel_permission.traits import HasPermissions

    assert hasattr(HasPermissions, "query_with_permission"), (
        "HasPermissions must have query_with_permission"
    )
    assert hasattr(HasPermissions, "query_without_permission"), (
        "HasPermissions must have query_without_permission"
    )


@pytest.mark.asyncio
async def test_query_with_role_returns_matching_models(
    async_session: AsyncSession,
) -> None:
    """FR-051-09a/f: query_with_role returns models with the given role (SQL query)."""
    from arvel_permission.models import ModelHasRole, Role

    # Table is created by conftest's create_all (module-level _QUser shares metadata).

    # Create users + role
    u1 = _QUser()
    u2 = _QUser()
    async_session.add_all([u1, u2])
    await async_session.flush()

    role = Role(name="editor", guard_name="web")
    async_session.add(role)
    await async_session.flush()

    pivot = ModelHasRole(
        role_id=role.id, model_type="_QUser", model_id=str(u1.id), guard_name="web"
    )
    async_session.add(pivot)
    await async_session.flush()

    result = await _QUser.query_with_role("editor", session=async_session)
    ids = [r.id for r in result]
    assert u1.id in ids
    assert u2.id not in ids


# ── FR-051-10: Events system ──────────────────────────────────────────────────


def test_events_module_importable() -> None:
    """FR-051-10a: arvel_permission.events must be importable."""
    from arvel_permission import events

    assert hasattr(events, "RoleAttachedEvent")
    assert hasattr(events, "RoleDetachedEvent")
    assert hasattr(events, "PermissionAttachedEvent")
    assert hasattr(events, "PermissionDetachedEvent")


def test_permission_config_has_events_enabled_field() -> None:
    """FR-051-10b: PermissionConfig must have events_enabled field (default False)."""
    from arvel_permission.config import PermissionConfig

    config = PermissionConfig()
    assert hasattr(config, "events_enabled"), "PermissionConfig must have events_enabled"
    assert config.events_enabled is False, "events_enabled must default to False"


def test_events_listener_called_on_assign_role() -> None:
    """FR-051-10c: assign_role dispatches RoleAttachedEvent when events_enabled=True."""
    from arvel_permission import events
    from arvel_permission.config import PermissionConfig

    fired: list[object] = []
    events.on(events.RoleAttachedEvent, fired.append)

    class _User(HasRoles, HasPermissions):
        default_guard_name = "web"
        _permission_config = PermissionConfig(events_enabled=True)

        def __init__(self) -> None:
            self.roles = []
            self.permissions = []

    user = _User()
    user.assign_role("editor")
    assert fired, "RoleAttachedEvent must fire when events_enabled=True"
    assert isinstance(fired[0], events.RoleAttachedEvent)

    # Cleanup listener
    events.clear_listeners()


def test_events_not_fired_when_disabled() -> None:
    """FR-051-10g: No events dispatched when events_enabled=False (default)."""
    from arvel_permission import events
    from arvel_permission.traits import HasRoles

    fired: list[object] = []
    events.on(events.RoleAttachedEvent, fired.append)

    class _User(HasRoles):
        default_guard_name = "web"

        def __init__(self) -> None:
            self.roles = []

    user = _User()
    user.assign_role("editor")
    assert not fired, "No events must fire when events_enabled=False (default)"

    events.clear_listeners()


def test_events_on_and_fire_api() -> None:
    """FR-051-10h: arvel_permission.events.on() and fire() work."""
    from arvel_permission import events

    fired: list[object] = []

    @events.on(events.RoleAttachedEvent)
    def _handler(evt: events.RoleAttachedEvent) -> None:
        fired.append(evt)

    del _handler  # registered via @events.on; drop local binding

    events.fire(events.RoleAttachedEvent(model=None, role=None))
    assert len(fired) == 1

    events.clear_listeners()
