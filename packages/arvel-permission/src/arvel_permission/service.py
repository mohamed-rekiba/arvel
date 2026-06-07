"""Permission registrar — find/create roles and permissions, cache lookups.

Public surface: ``register_role``, ``register_permission``, ``find_role``,
``find_permission``, ``refresh_cache``.

Two operating modes:

- **In-memory** (default): construct with no args. Roles and permissions live
  in instance dictionaries. Useful for tests, REPL exploration, and apps that
  don't need DB persistence yet.
- **DB-backed**: pass an ``AsyncSession``. The registrar then queries and
  inserts ``Role`` / ``Permission`` rows on misses. Cache stays per-instance.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import select

from arvel_permission.config import PermissionConfig
from arvel_permission.models import Permission, Role

if TYPE_CHECKING:
    from arvel.cache.store import CacheStore
    from sqlalchemy.ext.asyncio import AsyncSession


class GuardMismatchError(Exception):
    """Raised when a caller asks about a role/permission under the wrong guard."""


class PermissionRegistrar:
    """Find/create roles and permissions with per-instance caching."""

    def __init__(
        self,
        session: AsyncSession | None = None,
        *,
        config: PermissionConfig | None = None,
        cache_store: CacheStore | None = None,
    ) -> None:
        self._session = session
        self._config = config or PermissionConfig()
        self._cache_store = cache_store
        self._pending_flush_tasks: set[asyncio.Task[None]] = set()
        self._roles: dict[tuple[str, str], Role] = {}
        self._permissions: dict[tuple[str, str], Permission] = {}

    @property
    def config(self) -> PermissionConfig:
        return self._config

    def _key(self, name: str, guard: str | None) -> tuple[str, str]:
        return (name, guard or self._config.default_guard_name)

    def register_role(self, name: str, *, guard: str | None = None) -> Role:
        """In-memory registration. For DB-backed registration use :meth:`a_register_role`."""
        key = self._key(name, guard)
        if self._config.cache_enabled and key in self._roles:
            return self._roles[key]
        role = self._config.role_model(name=name, guard_name=key[1])
        if self._config.cache_enabled:
            self._roles[key] = role
        return role

    def register_permission(self, name: str, *, guard: str | None = None) -> Permission:
        key = self._key(name, guard)
        if self._config.cache_enabled and key in self._permissions:
            return self._permissions[key]
        perm = self._config.permission_model(name=name, guard_name=key[1])
        if self._config.cache_enabled:
            self._permissions[key] = perm
        return perm

    def find_role(self, name: str, *, guard: str | None = None) -> Role | None:
        return self._roles.get(self._key(name, guard))

    def find_permission(self, name: str, *, guard: str | None = None) -> Permission | None:
        return self._permissions.get(self._key(name, guard))

    def refresh_cache(self) -> None:
        self._roles.clear()
        self._permissions.clear()
        if self._cache_store is None:
            return
        result = self._cache_store.flush()
        if inspect.isawaitable(result):
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                asyncio.run(result)
            else:
                if not inspect.iscoroutine(result):
                    return
                task = loop.create_task(result)
                self._pending_flush_tasks.add(task)
                task.add_done_callback(self._pending_flush_tasks.discard)

    async def a_refresh_cache(self) -> None:
        self._roles.clear()
        self._permissions.clear()
        if self._cache_store is not None:
            await self._cache_store.flush()

    async def a_register_role(self, name: str, *, guard: str | None = None) -> Role:
        """DB-backed register. Requires the registrar to hold an AsyncSession."""
        if self._session is None:
            return self.register_role(name, guard=guard)
        resolved_guard = guard or self._config.default_guard_name
        existing = await self._a_fetch_role(name, resolved_guard)
        if existing is not None:
            if self._config.cache_enabled:
                self._roles[(name, resolved_guard)] = existing
            return existing
        role = self._config.role_model(name=name, guard_name=resolved_guard)
        self._session.add(role)
        await self._session.flush()
        if self._config.cache_enabled:
            self._roles[(name, resolved_guard)] = role
            await self._put_cached_role(role)
        return role

    async def a_register_permission(self, name: str, *, guard: str | None = None) -> Permission:
        if self._session is None:
            return self.register_permission(name, guard=guard)
        resolved_guard = guard or self._config.default_guard_name
        existing = await self._a_fetch_permission(name, resolved_guard)
        if existing is not None:
            if self._config.cache_enabled:
                self._permissions[(name, resolved_guard)] = existing
            return existing
        perm = self._config.permission_model(name=name, guard_name=resolved_guard)
        self._session.add(perm)
        await self._session.flush()
        if self._config.cache_enabled:
            self._permissions[(name, resolved_guard)] = perm
            await self._put_cached_permission(perm)
        return perm

    async def _a_fetch_role(self, name: str, guard: str) -> Role | None:
        if self._session is None:
            return None
        key = (name, guard)
        if self._config.cache_enabled:
            cached = self._roles.get(key) or await self._get_cached_role(name, guard)
            if cached is not None:
                self._roles[key] = cached
                return cached
        role_model = self._config.role_model
        stmt = select(role_model).filter_by(name=name, guard_name=guard).limit(1)
        result = await self._session.execute(stmt)
        role = result.scalar_one_or_none()
        if role is not None and self._config.cache_enabled:
            self._roles[key] = role
            await self._put_cached_role(role)
        return role

    async def _a_fetch_permission(self, name: str, guard: str) -> Permission | None:
        if self._session is None:
            return None
        key = (name, guard)
        if self._config.cache_enabled:
            cached = self._permissions.get(key) or await self._get_cached_permission(name, guard)
            if cached is not None:
                self._permissions[key] = cached
                return cached
        permission_model = self._config.permission_model
        stmt = select(permission_model).filter_by(name=name, guard_name=guard).limit(1)
        result = await self._session.execute(stmt)
        perm = result.scalar_one_or_none()
        if perm is not None and self._config.cache_enabled:
            self._permissions[key] = perm
            await self._put_cached_permission(perm)
        return perm

    def _cache_key(self, kind: str, name: str, guard: str) -> str:
        return f"{self._config.cache_prefix}:{kind}:{guard}:{name}"

    @staticmethod
    def _serialize_model(item: Role | Permission) -> dict[str, Any]:
        return {
            "id": getattr(item, "id", None),
            "name": item.name,
            "guard_name": item.guard_name,
        }

    @staticmethod
    def _cached_payload(data: object) -> dict[str, object] | None:
        if not isinstance(data, Mapping):
            return None
        payload: dict[str, object] = {}
        mapping = cast("Mapping[object, object]", data)
        for key, value in mapping.items():
            if not isinstance(key, str):
                return None
            payload[key] = value
        return payload

    def _hydrate_role(self, data: dict[str, object]) -> Role:
        name = data.get("name")
        guard_name = data.get("guard_name")
        if not isinstance(name, str) or not isinstance(guard_name, str):
            raise TypeError("Invalid cached role payload")
        role = self._config.role_model(name=name, guard_name=guard_name)
        role_id = data.get("id")
        if role_id is not None:
            object.__setattr__(role, "id", role_id)
        return role

    def _hydrate_permission(self, data: dict[str, object]) -> Permission:
        name = data.get("name")
        guard_name = data.get("guard_name")
        if not isinstance(name, str) or not isinstance(guard_name, str):
            raise TypeError("Invalid cached permission payload")
        perm = self._config.permission_model(name=name, guard_name=guard_name)
        permission_id = data.get("id")
        if permission_id is not None:
            object.__setattr__(perm, "id", permission_id)
        return perm

    async def _get_cached_role(self, name: str, guard: str) -> Role | None:
        if self._cache_store is None:
            return None
        data = await self._cache_store.get(self._cache_key("role", name, guard))
        payload = self._cached_payload(data)
        return self._hydrate_role(payload) if payload is not None else None

    async def _get_cached_permission(self, name: str, guard: str) -> Permission | None:
        if self._cache_store is None:
            return None
        data = await self._cache_store.get(self._cache_key("permission", name, guard))
        payload = self._cached_payload(data)
        return self._hydrate_permission(payload) if payload is not None else None

    async def _put_cached_role(self, role: Role) -> None:
        if self._cache_store is None:
            return
        await self._cache_store.put(
            self._cache_key("role", role.name, role.guard_name),
            self._serialize_model(role),
            ttl=self._config.cache_ttl,
        )

    async def _put_cached_permission(self, permission: Permission) -> None:
        if self._cache_store is None:
            return
        await self._cache_store.put(
            self._cache_key("permission", permission.name, permission.guard_name),
            self._serialize_model(permission),
            ttl=self._config.cache_ttl,
        )
