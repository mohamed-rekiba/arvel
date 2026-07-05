"""arvel.features — the mutate/when surface, the cache-backed store, model scope keys, the
``ScopedFeatures`` view and the ``Feature`` static front door."""

from __future__ import annotations

from typing import Any

import pytest

from arvel.features import (
    CacheFeatureStore,
    Feature,
    FeatureManager,
    _scope_key,  # pyright: ignore[reportPrivateUsage]
)
from arvel.kernel import Application, set_application


# --- _scope_key -----------------------------------------------------------
class _Model:
    __primary_key__ = "id"

    def __init__(self, pk: Any) -> None:
        self.id = pk


def test_scope_key_serializes_a_model_by_class_and_pk() -> None:
    assert _scope_key(_Model(7), "default") == "_Model:7"


def test_scope_key_of_a_model_without_a_pk_falls_back_to_str() -> None:
    m = _Model(None)
    assert _scope_key(m, "default") == str(m)


# --- CacheFeatureStore ----------------------------------------------------
class _FakeTagged:
    def __init__(self, store: dict[str, Any]) -> None:
        self.store = store

    async def get(self, key: str, default: Any) -> Any:
        return self.store.get(key, default)

    async def forever(self, key: str, value: Any) -> None:
        self.store[key] = value

    async def forget(self, key: str) -> None:
        self.store.pop(key, None)

    async def flush(self) -> None:
        self.store.clear()


class _FakeDriver:
    def __init__(self) -> None:
        self.tagsets: dict[str, dict[str, Any]] = {}

    def tags(self, tag: str) -> _FakeTagged:
        return _FakeTagged(self.tagsets.setdefault(tag, {}))


class _FakeCacheManager:
    def __init__(self) -> None:
        self._driver = _FakeDriver()

    def driver(self) -> _FakeDriver:
        return self._driver


async def test_cache_feature_store_round_trip() -> None:
    store = CacheFeatureStore(_FakeCacheManager())
    from arvel.features import _MISSING  # pyright: ignore[reportPrivateUsage]

    assert await store.get("flag", "u1") is _MISSING
    await store.put("flag", "u1", "purple")
    assert await store.get("flag", "u1") == "purple"
    await store.forget("flag", "u1")
    assert await store.get("flag", "u1") is _MISSING
    await store.put("flag", "u2", 1)
    await store.purge("flag")
    assert await store.get("flag", "u2") is _MISSING


def test_create_cache_driver_requires_a_bound_cache() -> None:
    with pytest.raises(RuntimeError, match="requires a bound 'cache' service"):
        FeatureManager().create_cache_driver()


# --- when / mutate surface ------------------------------------------------
async def test_when_runs_the_active_branch_and_awaits_callables() -> None:
    mgr = FeatureManager()
    mgr.define("beta", lambda scope: "gold")

    async def _active(value: Any) -> str:
        return f"on:{value}"

    assert await mgr.when("beta", "u1", _active, "off") == "on:gold"


async def test_when_runs_the_inactive_branch_with_a_plain_value() -> None:
    mgr = FeatureManager()
    mgr.define("beta", lambda scope: False)
    assert await mgr.when("beta", "u1", "yes", "no") == "no"


async def test_activate_deactivate_forget() -> None:
    mgr = FeatureManager()
    mgr.define("flag", lambda scope: False)
    await mgr.activate("flag", "u1")
    assert await mgr.active("flag", "u1") is True
    await mgr.deactivate("flag", "u1")
    assert await mgr.active("flag", "u1") is False
    await mgr.forget("flag", "u1")  # next read re-runs the resolver -> False
    assert await mgr.active("flag", "u1") is False


# --- ScopedFeatures + Feature front door ----------------------------------
@pytest.fixture
def booted_app() -> Any:
    app = Application()
    manager = FeatureManager(app)
    app.singleton("features", lambda _a: manager)
    set_application(app)
    try:
        yield manager
    finally:
        set_application(None)


async def test_feature_static_front_door_and_scoped_view(booted_app: FeatureManager) -> None:
    Feature.define("dark-mode", lambda scope: scope == "u1")
    assert "dark-mode" in Feature.defined()
    assert await Feature.active("dark-mode", "u1") is True
    assert await Feature.inactive("dark-mode", "u2") is True
    assert await Feature.value("dark-mode", "u1") is True
    assert await Feature.when("dark-mode", "u1", "yes", "no") == "yes"

    scoped = Feature.for_("u1")
    assert await scoped.active("dark-mode") is True
    assert await scoped.inactive("dark-mode") is False
    assert await scoped.value("dark-mode") is True
    assert await scoped.when("dark-mode", "y", "n") == "y"

    await Feature.activate("dark-mode", "u2")
    assert await Feature.active("dark-mode", "u2") is True
    await scoped.activate("dark-mode", value=False)
    assert await scoped.active("dark-mode") is False
    await Feature.deactivate("dark-mode", "u2")
    await scoped.deactivate("dark-mode")
    await Feature.forget("dark-mode", "u2")
    await scoped.forget("dark-mode")
    await Feature.purge("dark-mode")


def test_feature_front_door_requires_a_booted_application() -> None:
    set_application(None)
    with pytest.raises(RuntimeError, match="requires a booted application"):
        Feature.defined()
