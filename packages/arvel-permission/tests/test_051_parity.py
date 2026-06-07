"""Extended async ``MorphToMany`` behaviour: middleware, scoping, edge cases.

Behavioural tests run against a real session; middleware tests use async user
stubs because the middleware awaits the checks.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any, ClassVar

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
    role_has_permissions,
)
from arvel_permission.traits import HasPermissions, HasRoles
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


def _passthrough(r: Any) -> Any:
    """call_next stub for middleware tests — returns the request unchanged."""
    return r


class _QUser(Model, HasRoles, HasPermissions):
    __tablename__ = "users_051_query_scope"
    id: int = id_(init=False)
    default_guard_name: ClassVar[str] = "web"

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


# PermissionConfig.wildcard_enabled gates has_permission_to


@pytest.mark.asyncio
async def test_wildcard_config_disables_matching_globally(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    from arvel_permission.config import PermissionConfig
    from arvel_permission.traits import apply_wildcard_config

    config = PermissionConfig(wildcard_enabled=False)
    original = HasPermissions.wildcard_permission
    try:
        apply_wildcard_config(config)
        assert HasPermissions.wildcard_permission is False

        async with session_factory() as session, use_session(session):
            user = _QUser()
            session.add(user)
            await session.flush()
            await user.give_permission_to("edit.*")
            assert await user.has_permission_to("edit.articles") is False
    finally:
        HasPermissions.wildcard_permission = original


@pytest.mark.asyncio
async def test_wildcard_model_level_override_wins(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    from arvel_permission.config import PermissionConfig
    from arvel_permission.traits import apply_wildcard_config

    config = PermissionConfig(wildcard_enabled=False)
    original = HasPermissions.wildcard_permission
    try:
        apply_wildcard_config(config)

        async with session_factory() as session, use_session(session):
            user = _QUser()
            user.wildcard_permission = True
            session.add(user)
            await session.flush()
            await user.give_permission_to("edit.*")
            assert await user.has_permission_to("edit.articles") is True
    finally:
        HasPermissions.wildcard_permission = original


# role_has_permissions composite PK


def test_role_has_permissions_migration_uses_composite_pk() -> None:
    import inspect

    from arvel_permission.migrations.create_permission_tables import up

    source = inspect.getsource(up)
    assert '"role_has_permissions_unique"' not in source, (
        "Migration must not use a named unique constraint on role_has_permissions; "
        "use composite PK instead."
    )


def test_role_has_permissions_table_declares_composite_pk() -> None:
    pk_cols = {c.name for c in role_has_permissions.primary_key}
    assert pk_cols == {"permission_id", "role_id"}


# Middleware guard forwarding


@pytest.mark.asyncio
async def test_role_middleware_forwards_guard_to_has_role() -> None:
    from arvel_permission.exceptions import UnauthorizedException
    from arvel_permission.middleware import RoleMiddleware

    captured: dict[str, str | None] = {"guard": None}

    class _User:
        async def has_role(self, role: str, *, guard: str | None = None) -> bool:
            captured["guard"] = guard
            return False

    class _State:
        user = _User()

    class _Request:
        state = _State()

    mw = RoleMiddleware("admin", guard="api")
    with pytest.raises(UnauthorizedException):
        await mw.handle(_Request(), call_next=_passthrough)
    assert captured["guard"] == "api"


@pytest.mark.asyncio
async def test_permission_middleware_forwards_guard() -> None:
    from arvel_permission.exceptions import UnauthorizedException
    from arvel_permission.middleware import PermissionMiddleware

    captured: dict[str, str | None] = {"guard": None}

    class _User:
        async def has_permission_to(self, perm: str, *, guard: str | None = None) -> bool:
            captured["guard"] = guard
            return False

    class _State:
        user = _User()

    class _Request:
        state = _State()

    mw = PermissionMiddleware("edit", guard="api")
    with pytest.raises(UnauthorizedException):
        await mw.handle(_Request(), call_next=_passthrough)
    assert captured["guard"] == "api"


# Middleware pipe-separated OR syntax


@pytest.mark.asyncio
async def test_role_middleware_pipe_or_grants_on_second_match() -> None:
    from arvel_permission.middleware import RoleMiddleware

    class _User:
        async def has_role(self, role: str, *, guard: str | None = None) -> bool:
            return role == "manager"

    sentinel: list[Any] = []

    async def _next(r: Any) -> str:
        sentinel.append("ok")
        return "ok"

    class _State:
        user = _User()

    class _Request:
        state = _State()

    mw = RoleMiddleware("admin|manager")
    await mw.handle(_Request(), call_next=_next)
    assert sentinel


@pytest.mark.asyncio
async def test_permission_middleware_pipe_or_grants_on_first_match() -> None:
    from arvel_permission.middleware import PermissionMiddleware

    class _User:
        async def has_permission_to(self, perm: str, *, guard: str | None = None) -> bool:
            return perm == "publish"

    sentinel: list[Any] = []

    async def _next(r: Any) -> str:
        sentinel.append("ok")
        return "ok"

    class _State:
        user = _User()

    class _Request:
        state = _State()

    mw = PermissionMiddleware("publish|edit")
    await mw.handle(_Request(), call_next=_next)
    assert sentinel


@pytest.mark.asyncio
async def test_role_middleware_pipe_or_denies_when_none_match() -> None:
    from arvel_permission.exceptions import UnauthorizedException
    from arvel_permission.middleware import RoleMiddleware

    class _User:
        async def has_role(self, role: str, *, guard: str | None = None) -> bool:
            return False

    class _State:
        user = _User()

    class _Request:
        state = _State()

    mw = RoleMiddleware("admin|manager")
    with pytest.raises(UnauthorizedException) as exc_info:
        await mw.handle(_Request(), call_next=_passthrough)
    assert exc_info.value.status_code == 403


# Async registrar cache_enabled consistency


@pytest.mark.asyncio
async def test_async_registrar_cache_disabled_does_not_cache(
    async_session: AsyncSession,
) -> None:
    from arvel_permission.config import PermissionConfig
    from arvel_permission.service import PermissionRegistrar

    config = PermissionConfig(cache_enabled=False)
    reg = PermissionRegistrar(session=async_session, config=config)
    await reg.a_register_role("editor")
    assert reg.find_role("editor") is None


@pytest.mark.asyncio
async def test_async_registrar_cache_enabled_does_cache(
    async_session: AsyncSession,
) -> None:
    from arvel_permission.config import PermissionConfig
    from arvel_permission.service import PermissionRegistrar

    config = PermissionConfig(cache_enabled=True)
    reg = PermissionRegistrar(session=async_session, config=config)
    await reg.a_register_role("editor")
    assert reg.find_role("editor") is not None


# Bidirectional Permission ↔ Role API


def test_permission_roles_is_belongs_to_many() -> None:
    descriptor = Permission.__dict__["roles"]
    assert isinstance(descriptor, BelongsToMany)


def test_permission_has_assign_role_method() -> None:
    assert hasattr(Permission, "assign_role")
    assert hasattr(Permission, "remove_role")
    assert hasattr(Permission, "sync_roles")


@pytest.mark.asyncio
async def test_permission_assign_and_remove_role_db(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, use_session(session):
        perm = Permission(name="edit articles", guard_name="web")
        session.add(perm)
        await session.flush()

        await perm.assign_role("editor")
        assert any(r.name == "editor" for r in await perm.roles.all())

        await perm.remove_role("editor")
        assert not any(r.name == "editor" for r in await perm.roles.all())


@pytest.mark.asyncio
async def test_permission_sync_roles_db(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, use_session(session):
        perm = Permission(name="edit articles", guard_name="web")
        session.add(perm)
        await session.flush()

        await perm.assign_role("old-role")
        await perm.sync_roles(["editor", "admin"])
        names = {r.name for r in await perm.roles.all()}
        assert "old-role" not in names
        assert names == {"editor", "admin"}


# UnauthorizedException


def test_unauthorized_exception_importable() -> None:
    from arvel_permission.exceptions import UnauthorizedException

    assert issubclass(UnauthorizedException, Exception)


def test_unauthorized_exception_has_status_code() -> None:
    from arvel_permission.exceptions import UnauthorizedException

    exc = UnauthorizedException(status_code=403)
    assert exc.status_code == 403


@pytest.mark.asyncio
async def test_role_middleware_raises_unauthorized_on_deny() -> None:
    from arvel_permission.exceptions import UnauthorizedException
    from arvel_permission.middleware import RoleMiddleware

    class _User:
        async def has_role(self, role: str, *, guard: str | None = None) -> bool:
            return False

    class _State:
        user = _User()

    class _Request:
        state = _State()

    mw = RoleMiddleware("admin")
    with pytest.raises(UnauthorizedException):
        await mw.handle(_Request(), call_next=_passthrough)


@pytest.mark.asyncio
async def test_permission_middleware_raises_unauthorized_on_deny() -> None:
    from arvel_permission.exceptions import UnauthorizedException
    from arvel_permission.middleware import PermissionMiddleware

    class _User:
        async def has_permission_to(self, perm: str, *, guard: str | None = None) -> bool:
            return False

    class _State:
        user = _User()

    class _Request:
        state = _State()

    mw = PermissionMiddleware("edit")
    with pytest.raises(UnauthorizedException):
        await mw.handle(_Request(), call_next=_passthrough)


@pytest.mark.asyncio
async def test_no_user_raises_unauthorized_with_401() -> None:
    from arvel_permission.exceptions import UnauthorizedException
    from arvel_permission.middleware import RoleMiddleware

    class _State:
        user = None

    class _Request:
        state = _State()

    mw = RoleMiddleware("admin")
    with pytest.raises(UnauthorizedException) as exc_info:
        await mw.handle(_Request(), call_next=_passthrough)
    assert exc_info.value.status_code == 401


# Wildcard subpart syntax (comma-separated segments)


def test_wildcard_subpart_resource_action() -> None:
    from arvel_permission.traits import matches_wildcard

    assert matches_wildcard("posts,users.create,update", "posts.create")
    assert matches_wildcard("posts,users.create,update", "users.update")
    assert not matches_wildcard("posts,users.create,update", "posts.delete")
    assert not matches_wildcard("posts,users.create,update", "roles.create")


def test_wildcard_subpart_star_action() -> None:
    from arvel_permission.traits import matches_wildcard

    assert matches_wildcard("*.create,update", "articles.create")
    assert matches_wildcard("*.create,update", "roles.update")
    assert not matches_wildcard("*.create,update", "articles.delete")


def test_wildcard_subpart_three_segment() -> None:
    from arvel_permission.traits import matches_wildcard

    assert matches_wildcard("posts.*.1,4,6", "posts.edit.1")
    assert matches_wildcard("posts.*.1,4,6", "posts.view.4")
    assert not matches_wildcard("posts.*.1,4,6", "posts.edit.2")


def test_wildcard_subpart_existing_patterns_unchanged() -> None:
    from arvel_permission.traits import matches_wildcard

    assert matches_wildcard("*", "anything.at.all")
    assert matches_wildcard("edit.*", "edit.articles")
    assert not matches_wildcard("edit.*", "publish.articles")
    assert not matches_wildcard("edit.*", "edit.articles.section")


# Model query scopes


def test_has_roles_has_query_with_role_classmethod() -> None:
    assert hasattr(HasRoles, "query_with_role")
    assert hasattr(HasRoles, "query_without_role")


def test_has_permissions_has_query_with_permission_classmethod() -> None:
    assert hasattr(HasPermissions, "query_with_permission")
    assert hasattr(HasPermissions, "query_without_permission")


@pytest.mark.asyncio
async def test_query_with_role_returns_matching_models(
    async_session: AsyncSession,
) -> None:
    async with use_session(async_session):
        u1 = _QUser()
        u2 = _QUser()
        async_session.add_all([u1, u2])
        await async_session.flush()
        await u1.assign_role("editor")

        result = await _QUser.query_with_role("editor", session=async_session)
        ids = [r.id for r in result]
        assert u1.id in ids
        assert u2.id not in ids


# Events system


def test_events_module_importable() -> None:
    from arvel_permission import events

    assert hasattr(events, "RoleAttachedEvent")
    assert hasattr(events, "RoleDetachedEvent")
    assert hasattr(events, "PermissionAttachedEvent")
    assert hasattr(events, "PermissionDetachedEvent")


def test_permission_config_has_events_enabled_field() -> None:
    from arvel_permission.config import PermissionConfig

    config = PermissionConfig()
    assert hasattr(config, "events_enabled")
    assert config.events_enabled is False


class _EventUser(Model, HasRoles, HasPermissions):
    __tablename__ = "users_051_events"
    id: int = id_(init=False)
    default_guard_name: ClassVar[str] = "web"

    roles: ClassVar[MorphToMany[Role]] = MorphToMany(
        Role, table=model_has_roles, name="model", related_key="role_id"
    )
    permissions: ClassVar[MorphToMany[Permission]] = MorphToMany(
        Permission, table=model_has_permissions, name="model", related_key="permission_id"
    )


@pytest.mark.asyncio
async def test_events_listener_called_on_assign_role(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    from arvel_permission import events
    from arvel_permission.config import PermissionConfig

    fired: list[object] = []
    events.on(events.RoleAttachedEvent, fired.append)
    try:
        async with session_factory() as session, use_session(session):
            user = _EventUser()
            object.__setattr__(user, "_permission_config", PermissionConfig(events_enabled=True))
            session.add(user)
            await session.flush()
            await user.assign_role("editor")
        assert fired
        assert isinstance(fired[0], events.RoleAttachedEvent)
    finally:
        events.clear_listeners()


@pytest.mark.asyncio
async def test_events_not_fired_when_disabled(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    from arvel_permission import events

    fired: list[object] = []
    events.on(events.RoleAttachedEvent, fired.append)
    try:
        async with session_factory() as session, use_session(session):
            user = _EventUser()
            session.add(user)
            await session.flush()
            await user.assign_role("editor")
        assert not fired
    finally:
        events.clear_listeners()


def test_events_on_and_fire_api() -> None:
    from arvel_permission import events

    fired: list[object] = []

    @events.on(events.RoleAttachedEvent)
    def _handler(evt: events.RoleAttachedEvent) -> None:
        fired.append(evt)

    del _handler

    events.fire(events.RoleAttachedEvent(model=None, role=None))
    assert len(fired) == 1

    events.clear_listeners()
