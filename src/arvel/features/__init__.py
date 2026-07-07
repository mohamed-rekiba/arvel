"""arvel.features — feature flags.

``Feature.define(name, resolver)`` registers a flag; ``resolver(scope) -> bool | str | value`` is
evaluated **once per scope** — the resolved value is written straight to the configured store, so
the next ``active``/``value`` call for that same scope reads the persisted value instead of
re-running the resolver. On top of that persisted store sits a **request/task-scoped memo**
(``contextvars``, like ``arvel.support.Context``): once a scope's value is read (persisted or
just-resolved) it is cached for the rest of the current task, so repeat reads in the same
request never hit the store again — call ``FeatureManager.flush_cache()`` (or
``Feature.flush_cache()``) to drop it (a new task/request starts with none). ``scope`` is whatever
the flag varies by (a user, a team, or ``None`` for a global flag) and is serialized to a string
key (``_scope_key``) before it ever reaches a store.

Resolvers must be **side-effect-free / idempotent**: on the database and cache drivers the
get→resolve→put window has an ``await`` I/O suspension, so two concurrent first-time calls for the
same scope can both miss the store and run the resolver twice (best-effort memoization, exactly as
the reference design). The stored *value* is unaffected (the put is idempotent); only a resolver with an
observable side effect would notice. The array driver has no suspension point, so it is strictly
once.

Storage drivers (the ``arvel.support.manager.Manager`` strategy base, config ``features.driver``):
``array`` (in-memory, default/test), ``database`` (the ``features`` table, story 10), ``cache``
(story 06 — tagged per flag name so :meth:`FeatureManager.purge` can clear every scope for a flag
in one call). Not part of the original ch-08 port spec — added on request, following the
reference design (a small, high-value addition needing no new infra beyond cache/db; DR-0029).
"""

from __future__ import annotations

import asyncio
import contextvars
import inspect
from collections.abc import Callable
from typing import Any, ClassVar, Literal, cast

from arvel.database import Model
from arvel.kernel import Settings
from arvel.support.manager import Manager

type FeatureDriver = Literal["array", "database", "cache"]

#: sentinel distinguishing "no stored value yet" from a legitimately falsy/None stored value.
_MISSING: Any = object()

#: the store key an "activate for everyone" row is kept under — never a legal `_scope_key()`
#: output for a real scope (those are either `default_scope` or `f"{Cls}:{pk}"`).
_EVERYONE_SCOPE_KEY = "__everyone__"

#: Request/task-scoped memo of already-resolved ``(store id, name, scope_key) -> value`` pairs,
#: layered on top of the persisted store (see the module docstring) — copy-on-write per task,
#: exactly like ``arvel.support.Context``. Keyed by the resolving store's id (not just
#: name/scope_key) so two ``FeatureManager``s never bleed values into each other within one task.
_MemoKey = tuple[int, str, str]
_memo: contextvars.ContextVar[dict[_MemoKey, Any] | None] = contextvars.ContextVar(
    "arvel_features_memo", default=None
)


def _memo_get() -> dict[_MemoKey, Any]:
    return _memo.get() or {}


def _memo_remember(key: _MemoKey, value: Any) -> None:
    _memo.set({**_memo_get(), key: value})


def _memo_forget(key: _MemoKey) -> None:
    current = _memo_get()
    if key in current:
        updated = dict(current)
        del updated[key]
        _memo.set(updated)


def flush_cache() -> None:
    """Drop the request/task-scoped memo (not the persisted store) — call between requests in a
    context that reuses a task, or in test teardown."""
    _memo.set({})


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

    async def purge_all(self) -> None:
        """Drop every stored value, defined flag or not."""
        self._values.clear()


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

    async def purge_all(self) -> None:
        """Delete every row, defined flag or not."""
        await FeatureValue.query().delete()


#: the tag + key a set of every flag name ever put through :class:`CacheFeatureStore` is kept
#: under — `purge_all()` needs this to reach undefined-flag rows a "defined flags" loop would miss.
_CACHE_KNOWN_NAMES_TAG = "__feature_names__"
_CACHE_KNOWN_NAMES_KEY = "names"


class CacheFeatureStore:
    """Persists resolved values in the cache store (story 06), tagged per flag name so
    :meth:`purge` can clear every scope for a flag in one call (``TaggedCache.flush``)."""

    def __init__(self, cache_manager: Any) -> None:
        self._cache_manager = cache_manager
        self._names_lock: asyncio.Lock | None = None  # created lazily on the running loop

    def _tagged(self, name: str) -> Any:
        return self._cache_manager.driver().tags(f"feature:{name}")

    def _known_names(self) -> Any:
        return self._cache_manager.driver().tags(_CACHE_KNOWN_NAMES_TAG)

    async def _remember_name(self, name: str) -> None:
        # serialized read-modify-write: two concurrent put()s for different new names must
        # not overwrite each other's registry update, or purge_all() would miss a flag.
        # ponytail: an in-process lock; a multi-process registry needs an atomic append
        # on the backing store.
        if self._names_lock is None:
            self._names_lock = asyncio.Lock()
        async with self._names_lock:
            names: list[str] = await self._known_names().get(_CACHE_KNOWN_NAMES_KEY, [])
            if name not in names:
                await self._known_names().forever(_CACHE_KNOWN_NAMES_KEY, [*names, name])

    async def get(self, name: str, scope_key: str) -> Any:
        return await self._tagged(name).get(scope_key, _MISSING)

    async def put(self, name: str, scope_key: str, value: Any) -> None:
        await self._remember_name(name)
        await self._tagged(name).forever(scope_key, value)

    async def forget(self, name: str, scope_key: str) -> None:
        await self._tagged(name).forget(scope_key)

    async def purge(self, name: str) -> None:
        await self._tagged(name).flush()

    async def purge_all(self) -> None:
        """Flush every flag name ever put (defined or not) — ``purge(name)`` only reaches a
        single flag's tag; this walks the full "known names" registry instead."""
        names: list[str] = await self._known_names().get(_CACHE_KNOWN_NAMES_KEY, [])
        for name in names:
            await self._tagged(name).flush()
        await self._known_names().flush()


class FeatureManager(Manager):
    """Resolves the configured feature store + does per-scope resolution (the reference's
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

    def _memo_key(self, name: str, scope_key: str) -> _MemoKey:
        return (id(self.driver()), name, scope_key)

    async def _resolve(self, name: str, scope: Any) -> Any:
        scope_key = _scope_key(scope, self._default_scope())
        memo_key = self._memo_key(name, scope_key)
        memo = _memo_get()
        if memo_key in memo:
            return memo[memo_key]

        store = self.driver()
        stored = await store.get(name, scope_key)
        if stored is not _MISSING:
            _memo_remember(memo_key, stored)
            return stored

        # precedence: an explicit per-scope value (above) beats an "activate for everyone" row,
        # which beats the resolver's definition default.
        everyone = await store.get(name, _EVERYONE_SCOPE_KEY)
        if everyone is not _MISSING:
            _memo_remember(memo_key, everyone)
            return everyone

        resolver = self._resolvers.get(name)
        if resolver is None:
            raise LookupError(f"no feature named {name!r}; define it first with Feature.define()")
        value = resolver(scope)
        if inspect.isawaitable(value):
            value = await value
        await store.put(name, scope_key, value)
        _memo_remember(memo_key, value)
        return value

    def flush_cache(self) -> None:
        """Drop the request/task-scoped memo (not the persisted store)."""
        flush_cache()

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
        _memo_remember(self._memo_key(name, scope_key), value)

    async def deactivate(self, name: str, scope: Any = None) -> None:
        await self.activate(name, scope, value=False)

    async def activate_for_everyone(self, name: str, value: Any = True) -> None:
        """Write a wildcard row every scope with no explicit value of its own consults —
        precedence: an explicit per-scope value > this everyone value > the definition default."""
        await self.driver().put(name, _EVERYONE_SCOPE_KEY, value)

    async def deactivate_for_everyone(self, name: str) -> None:
        await self.activate_for_everyone(name, value=False)

    async def forget(self, name: str, scope: Any = None) -> None:
        scope_key = _scope_key(scope, self._default_scope())
        await self.driver().forget(name, scope_key)
        _memo_forget(self._memo_key(name, scope_key))

    async def purge(self, name: str | None = None) -> None:
        """Drop stored values for ``name``, or for every stored flag — defined or not — when
        ``name`` is None. Also drops this store's memo entries (name-matching, or all of them for
        a full purge) so a subsequent read re-resolves instead of serving the stale memo."""
        store = self.driver()
        store_id = id(store)
        if name is None:
            await store.purge_all()
            _memo.set({k: v for k, v in _memo_get().items() if k[0] != store_id})
        else:
            await store.purge(name)
            _memo.set(
                {k: v for k, v in _memo_get().items() if not (k[0] == store_id and k[1] == name)}
            )

    async def values(self, names: list[str] | None = None, scope: Any = None) -> dict[str, Any]:
        """Resolve several flags for one scope at once — every defined flag when ``names`` is None."""
        return {
            n: await self._resolve(n, scope)
            for n in (names if names is not None else self.defined())
        }

    async def all_are_active(self, names: list[str], scope: Any = None) -> bool:
        """Whether every flag in ``names`` is active for ``scope``."""
        for name in names:
            if not await self.active(name, scope):
                return False
        return True

    async def some_are_active(self, names: list[str], scope: Any = None) -> bool:
        """Whether at least one flag in ``names`` is active for ``scope``."""
        for name in names:
            if await self.active(name, scope):
                return True
        return False

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

    async def all_are_active(self, names: list[str]) -> bool:
        return await self._manager.all_are_active(names, self._scope)

    async def some_are_active(self, names: list[str]) -> bool:
        return await self._manager.some_are_active(names, self._scope)


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
    async def activate_for_everyone(name: str, value: Any = True) -> None:
        await Feature._manager().activate_for_everyone(name, value)

    @staticmethod
    async def deactivate_for_everyone(name: str) -> None:
        await Feature._manager().deactivate_for_everyone(name)

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
    async def all_are_active(names: list[str], scope: Any = None) -> bool:
        return await Feature._manager().all_are_active(names, scope)

    @staticmethod
    async def some_are_active(names: list[str], scope: Any = None) -> bool:
        return await Feature._manager().some_are_active(names, scope)

    @staticmethod
    def flush_cache() -> None:
        flush_cache()

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
    "flush_cache",
]
