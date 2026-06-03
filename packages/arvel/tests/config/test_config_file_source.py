"""Config-file cascade: config/*.py > env > field default.

Drives the registry directly via _lookup_registry.register so each test
controls exactly which config modules are "loaded".
"""

from __future__ import annotations

import os
import types
from collections.abc import Iterator

import pytest
from arvel.config import _lookup_registry as reg
from arvel.config.settings import ArvelSettings
from pydantic_settings import SettingsConfigDict


@pytest.fixture(autouse=True)
def clean_state() -> Iterator[None]:
    env_snapshot = dict(os.environ)
    reg.reset()
    try:
        yield
    finally:
        reg.reset()
        os.environ.clear()
        os.environ.update(env_snapshot)


def _register(stem: str, **attrs: object) -> None:
    reg.register(stem, types.SimpleNamespace(**attrs))


class WidgetConfig(ArvelSettings):
    model_config = SettingsConfigDict(env_prefix="WIDGET_")
    __config_path__ = "widgets.entries.{default}"

    size: int = 1
    color: str = "blue"
    connection: str | None = None


class FlatConfig(ArvelSettings):
    model_config = SettingsConfigDict(env_prefix="FLAT_")
    __config_path__ = "flat"

    name: str = "default-name"
    count: int = 0


def test_config_file_value_wins_over_env() -> None:
    os.environ["FLAT_NAME"] = "from-env"
    _register("flat", name="from-config", count=5)
    cfg = FlatConfig()
    assert cfg.name == "from-config"
    assert cfg.count == 5


def test_absent_module_falls_back_to_env() -> None:
    os.environ["FLAT_NAME"] = "from-env"
    cfg = FlatConfig()
    assert cfg.name == "from-env"


def test_absent_module_falls_back_to_default() -> None:
    cfg = FlatConfig()
    assert cfg.name == "default-name"
    assert cfg.count == 0


def test_partial_config_mixes_config_env_and_default() -> None:
    os.environ["FLAT_COUNT"] = "9"
    _register("flat", name="only-name")  # count omitted
    cfg = FlatConfig()
    assert cfg.name == "only-name"  # from config
    assert cfg.count == 9  # config omitted it -> env


def test_explicit_kwarg_wins_over_config_file() -> None:
    _register("flat", name="from-config")
    cfg = FlatConfig(name="explicit")
    assert cfg.name == "explicit"


def test_extra_keys_in_config_are_ignored() -> None:
    _register("flat", name="ok", bogus="nope", another=123)
    cfg = FlatConfig()
    assert cfg.name == "ok"


def test_default_token_resolves_named_entry() -> None:
    _register(
        "widgets",
        default="alpha",
        entries={"alpha": {"size": 10, "color": "red"}, "beta": {"size": 2}},
    )
    cfg = WidgetConfig()
    assert cfg.size == 10
    assert cfg.color == "red"


def test_default_token_injects_selector_into_connection() -> None:
    _register("widgets", default="beta", entries={"beta": {"size": 7}})
    cfg = WidgetConfig()
    assert cfg.connection == "beta"
    assert cfg.size == 7


def test_unresolvable_default_token_falls_back() -> None:
    os.environ["WIDGET_SIZE"] = "42"
    _register("widgets", entries={"alpha": {"size": 10}})  # no `default`
    cfg = WidgetConfig()
    assert cfg.size == 42  # token unresolved -> env


def test_dict_module_shape_resolves() -> None:
    reg.register("flat", {"name": "dict-shape"})
    cfg = FlatConfig()
    assert cfg.name == "dict-shape"


def test_no_config_path_class_is_unaffected() -> None:
    class PlainConfig(ArvelSettings):
        model_config = SettingsConfigDict(env_prefix="PLAIN_")
        value: str = "fallback"

    os.environ["PLAIN_VALUE"] = "env-value"
    _register("plain", value="should-be-ignored")
    cfg = PlainConfig()
    assert cfg.value == "env-value"  # no __config_path__ -> registry ignored
