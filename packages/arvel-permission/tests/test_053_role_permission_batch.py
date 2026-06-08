"""Role permissions must load in one query, not one per role (no N+1).

A user with N roles should cost a single query against ``role_has_permissions``
when checking or listing permissions inherited through roles.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from typing import ClassVar

import pytest
import pytest_asyncio
from arvel.database.columns import id_
from arvel.database.model import Model
from arvel.database.orm import MorphToMany
from arvel.database.session import use_session
from arvel_permission.models import (
    Permission,
    Role,
    model_has_permissions,
    model_has_roles,
)
from arvel_permission.traits import HasPermissions, HasRoles
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


class _BatchUser(Model, HasRoles, HasPermissions):
    __tablename__ = "users_053_batch"
    id: int = id_(init=False)
    default_guard_name: ClassVar[str] = "web"

    roles: ClassVar[MorphToMany[Role]] = MorphToMany(
        Role, table=model_has_roles, name="model", related_key="role_id"
    )
    permissions: ClassVar[MorphToMany[Permission]] = MorphToMany(
        Permission, table=model_has_permissions, name="model", related_key="permission_id"
    )


@pytest_asyncio.fixture()
async def batch_tables(async_engine: AsyncEngine) -> AsyncGenerator[None]:
    async with async_engine.begin() as conn:
        await conn.run_sync(_BatchUser.metadata.create_all)
    yield


def _pivot_query_counter(engine: AsyncEngine) -> tuple[list[int], Callable[..., None]]:
    """Count statements that touch role_has_permissions. Returns (count, listener)."""
    hits = [0]

    def _listener(*args: object) -> None:
        statement = args[2]
        if isinstance(statement, str) and "role_has_permissions" in statement:
            hits[0] += 1

    event.listen(engine.sync_engine, "before_cursor_execute", _listener)
    return hits, _listener


@pytest.mark.asyncio
async def test_get_permissions_via_roles_is_one_query(
    async_engine: AsyncEngine, async_session: AsyncSession, batch_tables: None
) -> None:
    async with use_session(async_session):
        user = _BatchUser()
        async_session.add(user)
        await async_session.flush()
        await user.assign_role("a", "b", "c")
        for i, role in enumerate(await user.roles.all()):
            await role.give_permission_to(f"perm.{i}")

        hits, listener = _pivot_query_counter(async_engine)
        try:
            perms = await user.get_permissions_via_roles()
        finally:
            event.remove(async_engine.sync_engine, "before_cursor_execute", listener)

    assert {p.name for p in perms} == {"perm.0", "perm.1", "perm.2"}
    assert hits[0] == 1  # batched — would be 3 (one per role) with the old N+1


@pytest.mark.asyncio
async def test_has_permission_to_via_roles_is_one_query(
    async_engine: AsyncEngine, async_session: AsyncSession, batch_tables: None
) -> None:
    async with use_session(async_session):
        user = _BatchUser()
        async_session.add(user)
        await async_session.flush()
        await user.assign_role("a", "b", "c")
        for i, role in enumerate(await user.roles.all()):
            await role.give_permission_to(f"perm.{i}")

        hits, listener = _pivot_query_counter(async_engine)
        try:
            # perm.2 lives on the last role — the worst case for the old per-role loop.
            granted = await user.has_permission_to("perm.2")
        finally:
            event.remove(async_engine.sync_engine, "before_cursor_execute", listener)

    assert granted is True
    assert hits[0] == 1
