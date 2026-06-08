"""Dotted config lookups into dicts must be key-only.

A missing key that happens to share a name with a dict builtin
(``get``, ``items``, ``keys``, ``values``, ``pop``, ...) must NOT resolve to
the bound method. It must miss — so ``config(key, default)`` returns the
default and ``lookup(key)`` raises ``ConfigKeyError``.
"""

from __future__ import annotations

import types

import pytest
from arvel.config._lookup_registry import (
    ConfigKeyError,
    config,
    lookup,
    register,
    reset,
)

_DICT_BUILTINS = (
    "get",
    "items",
    "keys",
    "values",
    "pop",
    "popitem",
    "copy",
    "update",
    "clear",
    "setdefault",
    "fromkeys",
)


@pytest.fixture(autouse=True)
def registry() -> None:
    reset()
    register("cache", types.SimpleNamespace(stores={"redis": {"host": "localhost"}}))


def test_real_key_still_resolves() -> None:
    assert config("cache.stores.redis.host") == "localhost"


def test_missing_plain_key_returns_default() -> None:
    assert config("cache.stores.missing", "FALLBACK") == "FALLBACK"


@pytest.mark.parametrize("method_name", _DICT_BUILTINS)
def test_dict_builtin_name_does_not_shadow_missing_key(method_name: str) -> None:
    result = config(f"cache.stores.{method_name}", "FALLBACK")
    assert result == "FALLBACK", f"{method_name!r} leaked a bound method instead of the default"
    assert not callable(result)


@pytest.mark.parametrize("method_name", _DICT_BUILTINS)
def test_lookup_raises_for_dict_builtin_name(method_name: str) -> None:
    with pytest.raises(ConfigKeyError):
        lookup(f"cache.stores.{method_name}")


def test_attribute_access_still_works_on_namespaces() -> None:
    # Top-level registry entries are namespaces/modules — attribute access stands.
    register("app", types.SimpleNamespace(name="arvel", nested=types.SimpleNamespace(tz="UTC")))
    assert config("app.name") == "arvel"
    assert config("app.nested.tz") == "UTC"
