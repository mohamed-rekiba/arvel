"""Query helpers must match the morph-alias discriminator that MorphToMany writes.

MorphToMany stores ``model_type = get_morph_alias(owner_cls)``. When a morph map
(or ``__morph_class__``) is registered, that token differs from the short class
name, so the ``query_with/without_*`` helpers have to resolve the same alias —
filtering by ``cls.__name__`` would never match the stored rows.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import ClassVar

import pytest
import pytest_asyncio
from arvel.database.columns import id_
from arvel.database.model import Model
from arvel.database.orm import MorphToMany
from arvel.database.orm.morph_map import morph_map, reset_morph_map
from arvel.database.session import use_session
from arvel_permission.models import (
    Permission,
    Role,
    model_has_permissions,
    model_has_roles,
)
from arvel_permission.traits import HasPermissions, HasRoles
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


class _AliasUser(Model, HasRoles, HasPermissions):
    __tablename__ = "users_052_alias_scope"
    id: int = id_(init=False)
    default_guard_name: ClassVar[str] = "web"

    roles: ClassVar[MorphToMany[Role]] = MorphToMany(
        Role, table=model_has_roles, name="model", related_key="role_id"
    )
    permissions: ClassVar[MorphToMany[Permission]] = MorphToMany(
        Permission, table=model_has_permissions, name="model", related_key="permission_id"
    )


@pytest_asyncio.fixture()
async def aliased(async_engine: AsyncEngine) -> AsyncGenerator[None]:
    async with async_engine.begin() as conn:
        await conn.run_sync(_AliasUser.metadata.create_all)
    morph_map({"alias_user": _AliasUser})
    try:
        yield
    finally:
        reset_morph_map()


@pytest.mark.asyncio
async def test_query_with_role_matches_morph_alias(
    async_session: AsyncSession, aliased: None
) -> None:
    async with use_session(async_session):
        holder = _AliasUser()
        other = _AliasUser()
        async_session.add_all([holder, other])
        await async_session.flush()
        await holder.assign_role("editor")

        with_ids = [u.id for u in await _AliasUser.query_with_role("editor", session=async_session)]
        without_ids = [
            u.id for u in await _AliasUser.query_without_role("editor", session=async_session)
        ]

    assert holder.id in with_ids
    assert other.id not in with_ids
    assert other.id in without_ids
    assert holder.id not in without_ids


@pytest.mark.asyncio
async def test_query_with_permission_matches_morph_alias(
    async_session: AsyncSession, aliased: None
) -> None:
    async with use_session(async_session):
        holder = _AliasUser()
        other = _AliasUser()
        async_session.add_all([holder, other])
        await async_session.flush()
        await holder.give_permission_to("posts.edit")

        with_ids = [
            u.id
            for u in await _AliasUser.query_with_permission("posts.edit", session=async_session)
        ]
        without_ids = [
            u.id
            for u in await _AliasUser.query_without_permission("posts.edit", session=async_session)
        ]

    assert holder.id in with_ids
    assert other.id not in with_ids
    assert other.id in without_ids
    assert holder.id not in without_ids
