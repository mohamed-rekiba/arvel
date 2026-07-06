"""arvel.features — Pennant-style feature flags.

``Feature.define(name, resolver)`` registers a flag; ``resolver(scope) -> bool | str | value`` is
evaluated **once per scope** — the resolved value is written straight to the configured store, so
the next ``active``/``value`` call for that same scope reads the stored value instead of
re-running the resolver (the store *is* the memoization; there is no separate in-request cache).
``scope`` is whatever the flag varies by (a user, a team, or ``None`` for a global flag) and is
serialized to a string key (``_scope_key``) before it ever reaches a store.

Resolvers must be **side-effect-free / idempotent**: on the database and cache drivers the
get→resolve→put window has an ``await`` I/O suspension, so two concurrent first-time calls for the
same scope can both miss the store and run the resolver twice (best-effort memoization, exactly as
Pennant). The stored *value* is unaffected (the put is idempotent); only a resolver with an
observable side effect would notice. The array driver has no suspension point, so it is strictly
once.

Storage drivers (the ``arvel.support.manager.Manager`` strategy base, config ``features.driver``):
``array`` (in-memory, default/test), ``database`` (the ``features`` table, story 10), ``cache``
(story 06 — tagged per flag name so :meth:`FeatureManager.purge` can clear every scope for a flag
in one call). Not part of the original ch-08 port spec — added on request, following the
Pennant design (a small, high-value addition needing no new infra beyond cache/db; DR-0029).
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any, ClassVar, Literal, cast

from arvel.database import Model
from arvel.kernel import Settings
from arvel.support.manager import Manager

type FeatureDriver = Literal["array", "database", "cache"]

#: sentinel distinguishing "no stored value yet" from a legitimately falsy/None stored value.
_MISSING: Any = object()


class FeatureSettings(Settings):
    """Typed, validated view over the ``features`` config section (DR-0016).

    ``default_scope`` is the store key used for a ``None`` (global) scope.
    """

    __config_key__ = "features"
    driver: FeatureDriver = "array"
    default_scope: str = "__global__"


def _scope_key(scope: Any, default_scope: str) -> str:
    """Serialize ``scope`` to the string key a store keys its rows/entries by."""
    if scope is None:
        return default_scope
    if isinstance(scope, str):
        return scope
    pk_name = cast("str", getattr(scope, "__primary_key__", "id"))
    pk = getattr(scope, pk_name, None)
    if pk is not None:
        return f"{type(scope).__name__}:{pk}"
    return str(scope)


def _normalize_resolver(resolver: Any) -> Callable[[Any], Any]:
    """Accept a closure, an already-instantiated callable, or a class-based feature (a bare class
    is instantiated once and dispatched through its ``resolve`` method
    class-based-feature parity)."""
    if isinstance(resolver, type):
        resolver = resolver()
    resolve = getattr(resolver, "resolve", None)
    return cast("Callable[[Any], Any]", resolve) if callable(resolve) else resolver


class ArrayFeatureStore:
    """In-memory store — the default/test driver. Not shared across manager instances (no
    persistence guarantee, like the array cache/search drivers)."""

    def __init__(self) -> None:
        self._values: dict[tuple[str, str], Any] = {}

    async def get(self, name: str, scope_key: str) -> Any:
        return self._values.get((name, scope_key), _MISSING)

    async def put(self, name: str, scope_key: str, value: Any) -> None:
        self._values[(name, scope_key)] = value

    async def forget(self, name: str, scope_key: str) -> None:
        self._values.pop((name, scope_key), None)

    async def purge(self, name: str) -> None:
        for key in [k for k in self._values if k[0] == name]:
            del self._values[key]


class FeatureValue(Model):
    """A resolved flag value, persisted per scope — the ``database`` driver's backing table."""

    __table_name__ = "features"
    __fields__: ClassVar[dict[str, Any]] = {"name": str, "scope": str, "value": str}
    __fillable__: ClassVar[list[str]] = list(__fields__)
    __casts__: ClassVar[dict[str, str]] = {"value": "json"}


class DatabaseFeatureStore:
    """Persists resolved values in the ``features`` table (:class:`FeatureValue`) — a fresh
    process (a new :class:`FeatureManager`) sees stored values, since the model reads through the
    connection resolver rather than any of this store's own memory.

    ``value`` is wrapped in a single-key dict (``{"v": value}``) before it's assigned to the
    model's ``json``-cast column: the cast's write path treats an already-``str`` value as
    pre-serialized JSON and stores it verbatim (so a bare string flag value like ``"variant"``
    would round-trip as invalid JSON) — wrapping in a dict sidesteps that, since a dict is never
    mistaken for already-serialized text.
    """

    async def get(self, name: str, scope_key: str) -> Any:
        row = await FeatureValue.where(name=name, scope=scope_key).first()
        return row.value["v"] if row is not None else _MISSING

    async def put(self, name: str, scope_key: str, value: Any) -> None:
        await FeatureValue.update_or_create(
            {"name": name, "scope": scope_key}, {"value": {"v": value}}
        )

    async def forget(self, name: str, scope_key: str) -> None:
        await FeatureValue.where(name=name, scope=scope_key).delete()

    async def purge(self, name: str) -> None:
        await FeatureValue.where(name=name).delete()


class CacheFeatureStore:
    """Persists resolved values in the cache store (story 06), tagged per flag name so
    :meth:`purge` can clear every scope for a flag in one call (``TaggedCache.flush``)."""

    def __init__(self, cache_manager: Any) -> None:
        self._cache_manager = cache_manager

    def _tagged(self, name: str) -> Any:
        return self._cache_manager.driver().tags(f"feature:{name}")

    async def get(self, name: str, scope_key: str) -> Any:
        return await self._tagged(name).get(scope_key, _MISSING)

    async def put(self, name: str, scope_key: str, value: Any) -> None:
        await self._tagged(name).forever(scope_key, value)

    async def forget(self, name: str, scope_key: str) -> None:
        await self._tagged(name).forget(scope_key)

    async def purge(self, name: str) -> None:
        await self._tagged(name).flush()


class FeatureManager(Manager):
    """Resolves the configured feature store + does per-scope resolution (Pennant's
    ``FeatureManager``): the store only remembers already-resolved values — this class owns the
    resolver registry and the "run once per scope" behavior."""

    def __init__(self, app: Any = None) -> None:
        super().__init__(app)
        self._resolvers: dict[str, Callable[[Any], Any]] = {}

    def default_driver(self) -> str:
        return self._settings(FeatureSettings).driver  # auto-loads + validates config("features")

    def create_array_driver(self) -> ArrayFeatureStore:
        return ArrayFeatureStore()

    def create_database_driver(self) -> DatabaseFeatureStore:
        return DatabaseFeatureStore()

    def create_cache_driver(self) -> CacheFeatureStore:
        if self.app is None or not self.app.bound("cache"):
            raise RuntimeError(
                "features.driver='cache' requires a bound 'cache' service — register "
                "arvel.cache.provider.CacheServiceProvider."
            )
        return CacheFeatureStore(self.app.make("cache"))

    def _default_scope(self) -> str:
        return self._settings(FeatureSettings).default_scope

    def define(self, name: str, resolver: Any) -> None:
        """Register ``resolver(scope) -> bool | str | value`` under ``name``."""
        self._resolvers[name] = _normalize_resolver(resolver)

    def defined(self) -> list[str]:
        """The names of every flag registered via:meth:`define`."""
        return sorted(self._resolvers)

    async def _resolve(self, name: str, scope: Any) -> Any:
        scope_key = _scope_key(scope, self._default_scope())
        store = self.driver()
        stored = await store.get(name, scope_key)
        if stored is not _MISSING:
            return stored
        resolver = self._resolvers.get(name)
        if resolver is None:
            raise LookupError(f"no feature named {name!r}; define it first with Feature.define()")
        value = resolver(scope)
        if inspect.isawaitable(value):
            value = await value
        await store.put(name, scope_key, value)
        return value

    async def value(self, name: str, scope: Any = None) -> Any:
        return await self._resolve(name, scope)

    async def active(self, name: str, scope: Any = None) -> bool:
        return bool(await self._resolve(name, scope))

    async def inactive(self, name: str, scope: Any = None) -> bool:
        return not await self.active(name, scope)

    async def when(self, name: str, scope: Any, when_active: Any, when_inactive: Any) -> Any:
        value = await self._resolve(name, scope)
        branch = when_active if value else when_inactive
        result = branch(value) if callable(branch) else branch
        if inspect.isawaitable(result):
            result = await result
        return result

    async def activate(self, name: str, scope: Any = None, value: Any = True) -> None:
        scope_key = _scope_key(scope, self._default_scope())
        await self.driver().put(name, scope_key, value)

    async def deactivate(self, name: str, scope: Any = None) -> None:
        await self.activate(name, scope, value=False)

    async def forget(self, name: str, scope: Any = None) -> None:
        scope_key = _scope_key(scope, self._default_scope())
        await self.driver().forget(name, scope_key)

    async def purge(self, name: str | None = None) -> None:
        """Drop stored values for ``name``, or for every defined flag when ``name`` is None."""
        store = self.driver()
        for target in [name] if name is not None else self.defined():
            await store.purge(target)

    async def values(self, names: list[str] | None = None, scope: Any = None) -> dict[str, Any]:
        """Resolve several flags for one scope at once — every defined flag when ``names`` is None."""
        return {
            n: await self._resolve(n, scope)
            for n in (names if names is not None else self.defined())
        }

    def for_(self, scope: Any) -> ScopedFeatures:
        """A features view bound to ``scope``."""
        return ScopedFeatures(self, scope)


class ScopedFeatures:
    """Returned by :meth:`FeatureManager.for_`/``Feature.for_`` — the same read/mutate surface,
    with ``scope`` already bound."""

    def __init__(self, manager: FeatureManager, scope: Any) -> None:
        self._manager = manager
        self._scope = scope

    async def active(self, name: str) -> bool:
        return await self._manager.active(name, self._scope)

    async def inactive(self, name: str) -> bool:
        return await self._manager.inactive(name, self._scope)

    async def value(self, name: str) -> Any:
        return await self._manager.value(name, self._scope)

    async def when(self, name: str, when_active: Any, when_inactive: Any) -> Any:
        return await self._manager.when(name, self._scope, when_active, when_inactive)

    async def activate(self, name: str, value: Any = True) -> None:
        await self._manager.activate(name, self._scope, value)

    async def deactivate(self, name: str) -> None:
        await self._manager.deactivate(name, self._scope)

    async def forget(self, name: str) -> None:
        await self._manager.forget(name, self._scope)


class Feature:
    """Static-looking front door — forwards to the app-bound
    :class:`FeatureManager` singleton. Requires a booted application with
    ``FeatureServiceProvider`` registered (mirrors how ``Searchable`` resolves ``app("search")`` —
    no facade class here: ``arvel.support.facades`` sits below this module in the G1 layer DAG)."""

    @staticmethod
    def _manager() -> FeatureManager:
        from arvel.kernel import app, has_application

        if not (has_application() and app().bound("features")):
            raise RuntimeError(
                "Feature requires a booted application with FeatureServiceProvider registered."
            )
        return cast("FeatureManager", app().make("features"))

    @staticmethod
    def define(name: str, resolver: Any) -> None:
        Feature._manager().define(name, resolver)

    @staticmethod
    def defined() -> list[str]:
        return Feature._manager().defined()

    @staticmethod
    async def active(name: str, scope: Any = None) -> bool:
        return await Feature._manager().active(name, scope)

    @staticmethod
    async def inactive(name: str, scope: Any = None) -> bool:
        return await Feature._manager().inactive(name, scope)

    @staticmethod
    async def value(name: str, scope: Any = None) -> Any:
        return await Feature._manager().value(name, scope)

    @staticmethod
    async def when(name: str, scope: Any, when_active: Any, when_inactive: Any) -> Any:
        return await Feature._manager().when(name, scope, when_active, when_inactive)

    @staticmethod
    async def activate(name: str, scope: Any = None, value: Any = True) -> None:
        await Feature._manager().activate(name, scope, value)

    @staticmethod
    async def deactivate(name: str, scope: Any = None) -> None:
        await Feature._manager().deactivate(name, scope)

    @staticmethod
    async def forget(name: str, scope: Any = None) -> None:
        await Feature._manager().forget(name, scope)

    @staticmethod
    async def purge(name: str | None = None) -> None:
        await Feature._manager().purge(name)

    @staticmethod
    async def values(names: list[str] | None = None, scope: Any = None) -> dict[str, Any]:
        return await Feature._manager().values(names, scope)

    @staticmethod
    def for_(scope: Any) -> ScopedFeatures:
        return Feature._manager().for_(scope)


__all__ = [
    "ArrayFeatureStore",
    "CacheFeatureStore",
    "DatabaseFeatureStore",
    "Feature",
    "FeatureDriver",
    "FeatureManager",
    "FeatureSettings",
    "FeatureValue",
    "ScopedFeatures",
]
