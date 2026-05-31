"""Integer-PK host support for arvel-permission — FR-032-08 / AC-19..20.

The async ``MorphToMany`` accessor str-casts the owner PK into the VARCHAR
``model_id`` pivot column, so grants persist and survive a fresh session
without ``_StringId``, ``cast``, or ``type: ignore``.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
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
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


class _IntPkUser(Model, HasRoles, HasPermissions):
    __tablename__ = "users_intpk"
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


@pytest.mark.asyncio
async def test_integer_pk_host_grants_survive(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as s1, use_session(s1):
        user = _IntPkUser()
        s1.add(user)
        await s1.flush()
        await user.assign_role("editor")
        await user.give_permission_to("articles.edit")
        await s1.commit()
        user_id = user.id

    async with session_factory() as s2, use_session(s2):
        reloaded = await _IntPkUser.where(_IntPkUser.id == user_id).first()
        assert reloaded is not None
        assert [r.name for r in await reloaded.roles.all()] == ["editor"]
        assert await reloaded.has_permission_to("articles.edit")
        assert await reloaded.has_role("editor")
