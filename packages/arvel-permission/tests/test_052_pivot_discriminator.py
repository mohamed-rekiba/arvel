"""Regression: trait-assigned roles/permissions must persist the polymorphic
``model_type`` discriminator and survive a fresh session.

The async ``MorphToMany`` accessor writes ``model_type`` explicitly on every
INSERT, so trait grants never produce a NULL discriminator. Reads filter on
``model_type == "<Model>"``, so a row that survives into a fresh session proves
the discriminator was written.
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


class _PivotUser(Model, HasRoles, HasPermissions):
    __tablename__ = "users_052_pivot"
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
async def test_trait_assigned_role_survives_fresh_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as s1, use_session(s1):
        user = _PivotUser()
        s1.add(user)
        await s1.flush()
        await user.assign_role("editor")
        await s1.commit()
        user_id = user.id

    async with session_factory() as s2, use_session(s2):
        reloaded = await _PivotUser.where(_PivotUser.id == user_id).first()
        assert reloaded is not None
        names = [r.name for r in await reloaded.roles.all()]
        assert names == ["editor"], "role assigned via the trait must survive into a fresh session"


@pytest.mark.asyncio
async def test_trait_granted_permission_survives_fresh_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as s1, use_session(s1):
        user = _PivotUser()
        s1.add(user)
        await s1.flush()
        await user.give_permission_to("articles.edit")
        await s1.commit()
        user_id = user.id

    async with session_factory() as s2, use_session(s2):
        reloaded = await _PivotUser.where(_PivotUser.id == user_id).first()
        assert reloaded is not None
        names = [p.name for p in await reloaded.permissions.all()]
        assert names == ["articles.edit"], (
            "permission granted via the trait must survive into a fresh session"
        )


@pytest.mark.asyncio
async def test_trait_remove_role_deletes_pivot_row(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as s1, use_session(s1):
        user = _PivotUser()
        s1.add(user)
        await s1.flush()
        await user.assign_role("editor")
        await s1.commit()
        user_id = user.id

    async with session_factory() as s2, use_session(s2):
        reloaded = await _PivotUser.where(_PivotUser.id == user_id).first()
        assert reloaded is not None
        await reloaded.remove_role("editor")
        await s2.commit()

    async with session_factory() as s3, use_session(s3):
        again = await _PivotUser.where(_PivotUser.id == user_id).first()
        assert again is not None
        assert await again.roles.all() == [], "remove_role must delete the pivot row"
