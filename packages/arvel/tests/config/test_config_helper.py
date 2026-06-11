"""Tests for the config() helper (arvel.config._lookup_registry.config).

Mirrors the env() test style. Every test sets up a real config directory via
ApplicationBuilder.with_config_dir so the helper exercises the live registry.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from arvel import Application


@pytest.fixture
def app_with_config(tmp_path: Path) -> None:
    """Bootstrap a minimal app with two config modules."""
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "app.py").write_text(
        'timezone = "UTC"\nname = "arvel-test"\ndebug = False\nmax_upload_mb = 10\n'
        'providers = ["Auth", "Cache", "Queue"]\n'
    )
    (cfg / "database.py").write_text(
        'DEFAULT = "sqlite"\nCONNECTIONS = {"sqlite": {"url": "sqlite+aiosqlite:///./test.db"}}\n'
    )
    Application.configure(tmp_path).with_environment("testing").with_config_dir(cfg).create()


def test_config_returns_value_for_existing_key(app_with_config: None) -> None:
    from arvel import config

    assert config("app.timezone") == "UTC"


def test_config_returns_none_when_key_missing_and_no_default(app_with_config: None) -> None:
    from arvel import config

    assert config("app.nonexistent") is None


def test_config_returns_default_when_key_missing(app_with_config: None) -> None:
    from arvel import config

    assert config("app.nonexistent", "UTC") == "UTC"
    assert config("app.nonexistent", 42) == 42
    assert config("app.nonexistent", False) is False


def test_config_returns_actual_value_not_default_when_key_found(app_with_config: None) -> None:
    from arvel import config

    # "UTC" is the real value; default should be ignored
    assert config("app.timezone", "fallback") == "UTC"


def test_config_returns_none_default_explicitly(app_with_config: None) -> None:
    from arvel import config

    # Explicit None default — same as omitting it
    assert config("app.missing_key", None) is None


def test_config_traverses_dict(app_with_config: None) -> None:
    from arvel import config

    assert config("database.CONNECTIONS.sqlite.url") == "sqlite+aiosqlite:///./test.db"


def test_config_returns_none_for_missing_module(app_with_config: None) -> None:
    from arvel import config

    # "cache" module was never loaded — should return None, not raise
    assert config("cache.store") is None


def test_config_returns_default_for_missing_module(app_with_config: None) -> None:
    from arvel import config

    assert config("cache.store", "array") == "array"


def test_config_indexes_into_list(app_with_config: None) -> None:
    from arvel import config

    assert config("app.providers.0") == "Auth"
    assert config("app.providers.2") == "Queue"
    assert config("app.providers.-1") == "Queue"


def test_config_list_index_out_of_range_returns_default(app_with_config: None) -> None:
    from arvel import config

    assert config("app.providers.9", "fallback") == "fallback"


def test_config_non_numeric_list_segment_returns_default(app_with_config: None) -> None:
    from arvel import config

    # A list never exposes its methods via dotted access.
    assert config("app.providers.append", "safe") == "safe"


def test_has_true_for_existing_key(app_with_config: None) -> None:
    from arvel.config import has

    assert has("app.timezone") is True
    assert has("app.providers.0") is True
    assert has("database.CONNECTIONS.sqlite.url") is True


def test_has_false_for_missing_key_or_module(app_with_config: None) -> None:
    from arvel.config import has

    assert has("app.nonexistent") is False
    assert has("cache.store") is False
    assert has("app.providers.9") is False


def test_config_is_importable_from_top_level_arvel() -> None:
    from arvel import config

    assert callable(config)


def test_config_is_importable_from_arvel_config() -> None:
    from arvel.config import config

    assert callable(config)
