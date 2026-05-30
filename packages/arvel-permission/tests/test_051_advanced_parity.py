"""Regression tests for WI-arvel-051 advanced permission parity."""

from __future__ import annotations

from typing import cast

import pytest
from arvel.cache.stores.array import ArrayStore
from arvel_permission.config import PermissionConfig
from arvel_permission.models import Permission, Role
from arvel_permission.service import PermissionRegistrar
from arvel_permission.traits import HasPermissions, HasRoles, apply_model_config
from sqlalchemy.ext.asyncio import AsyncSession


class CustomRole(Role):
    pass


class CustomPermission(Permission):
    pass


def test_permission_config_accepts_custom_models() -> None:
    config = PermissionConfig(role_model=CustomRole, permission_model=CustomPermission)

    assert config.role_model is CustomRole
    assert config.permission_model is CustomPermission


def test_registrar_uses_custom_models_for_sync_registration() -> None:
    config = PermissionConfig(role_model=CustomRole, permission_model=CustomPermission)
    registrar = PermissionRegistrar(config=config)

    role = registrar.register_role("editor")
    permission = registrar.register_permission("articles.edit")

    assert isinstance(role, CustomRole)
    assert isinstance(permission, CustomPermission)


def test_mixins_use_custom_models_for_string_coercion() -> None:
    config = PermissionConfig(role_model=CustomRole, permission_model=CustomPermission)
    apply_model_config(config)

    class User(HasRoles, HasPermissions):
        default_guard_name = "web"

    try:
        user = User()
        object.__setattr__(user, "roles", [])
        object.__setattr__(user, "permissions", [])
        user.assign_role("editor")
        user.give_permission_to("articles.edit")

        roles = cast("list[Role]", object.__getattribute__(user, "roles"))
        permissions = cast("list[Permission]", object.__getattribute__(user, "permissions"))
        assert isinstance(roles[0], CustomRole)
        assert isinstance(permissions[0], CustomPermission)
    finally:
        apply_model_config(PermissionConfig())


@pytest.mark.asyncio
async def test_persistent_cache_survives_new_registrar_instance(
    async_session: AsyncSession,
) -> None:
    store = ArrayStore(prefix="permission-test")
    config = PermissionConfig(cache_store="array", cache_prefix="test-permissions")

    first = PermissionRegistrar(session=async_session, config=config, cache_store=store)
    await first.a_register_role("editor")

    second = PermissionRegistrar(session=async_session, config=config, cache_store=store)
    cached = await second.a_register_role("editor")

    assert cached.name == "editor"
    assert second.find_role("editor") is cached


@pytest.mark.asyncio
async def test_persistent_cache_honours_cache_enabled_false(
    async_session: AsyncSession,
) -> None:
    store = ArrayStore(prefix="permission-test")
    config = PermissionConfig(
        cache_enabled=False,
        cache_store="array",
        cache_prefix="disabled-permissions",
    )

    registrar = PermissionRegistrar(session=async_session, config=config, cache_store=store)
    await registrar.a_register_role("editor")

    assert store.entries == {}
    assert registrar.find_role("editor") is None


@pytest.mark.asyncio
async def test_async_refresh_cache_flushes_persistent_store(async_session: AsyncSession) -> None:
    store = ArrayStore(prefix="permission-test")
    config = PermissionConfig(cache_store="array", cache_prefix="flush-permissions")
    registrar = PermissionRegistrar(session=async_session, config=config, cache_store=store)

    await registrar.a_register_permission("articles.edit")
    assert store.entries

    await registrar.a_refresh_cache()

    assert store.entries == {}
    assert registrar.find_permission("articles.edit") is None
