"""``ApplicationBuilder.with_config_dir(path)``.

Discovers every ``.py`` file in ``path`` (non-recursive, no ``_`` prefix),
loads each via the namespaced loader, and exposes its top-level attributes
through ``arvel.config.lookup`` under the dotted key
``<module_stem>.<ATTR>``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from arvel import Application


def _make_config_dir(tmp_path: Path) -> Path:
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "app.py").write_text('NAME = "test-app"\nDEBUG = False\n')
    (cfg / "database.py").write_text(
        'DEFAULT = "sqlite"\n'
        'CONNECTIONS = {"sqlite": {"url": "sqlite+aiosqlite:///./database/database.sqlite"}}\n',
    )
    return cfg


def test_with_config_dir_accepts_pathlib_path(tmp_path: Path) -> None:
    cfg = _make_config_dir(tmp_path)
    builder = Application.configure(tmp_path).with_environment("testing").with_config_dir(cfg)
    assert builder is not None


def test_with_config_dir_accepts_str_path(tmp_path: Path) -> None:
    cfg = _make_config_dir(tmp_path)
    builder = Application.configure(tmp_path).with_environment("testing").with_config_dir(str(cfg))
    assert builder is not None


def test_with_config_dir_loads_top_level_attributes(tmp_path: Path) -> None:
    """After create(), config('database.DEFAULT') resolves to the loaded value."""
    from arvel.config import lookup

    cfg = _make_config_dir(tmp_path)

    Application.configure(tmp_path).with_environment("testing").with_config_dir(cfg).create()

    assert lookup("database.DEFAULT") == "sqlite"
    assert lookup("app.NAME") == "test-app"


def test_with_config_dir_dotted_traversal_into_dict(tmp_path: Path) -> None:
    """Dotted keys traverse dict subscripts (config('database.CONNECTIONS.sqlite.url'))."""
    from arvel.config import lookup

    cfg = _make_config_dir(tmp_path)

    Application.configure(tmp_path).with_environment("testing").with_config_dir(cfg).create()

    assert (
        lookup("database.CONNECTIONS.sqlite.url")
        == "sqlite+aiosqlite:///./database/database.sqlite"
    )


def test_with_config_dir_missing_key_raises_config_key_error(tmp_path: Path) -> None:
    from arvel.config import ConfigKeyError, lookup

    cfg = _make_config_dir(tmp_path)
    Application.configure(tmp_path).with_environment("testing").with_config_dir(cfg).create()

    with pytest.raises(ConfigKeyError):
        lookup("database.NO_SUCH_KEY")


def test_with_config_dir_ignores_underscore_prefixed_files(tmp_path: Path) -> None:
    """Files starting with _ are excluded from discovery."""
    from arvel.config import ConfigKeyError, lookup

    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "app.py").write_text('NAME = "visible"\n')
    (cfg / "_private.py").write_text('SECRET = "hidden"\n')

    Application.configure(tmp_path).with_environment("testing").with_config_dir(cfg).create()

    assert lookup("app.NAME") == "visible"
    with pytest.raises(ConfigKeyError):
        lookup("_private.SECRET")


def test_with_config_dir_ignores_non_py_files(tmp_path: Path) -> None:
    """README.md, .env etc. are skipped — only .py is discovered."""
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "app.py").write_text('NAME = "x"\n')
    (cfg / "README.md").write_text("# Config docs\n")
    (cfg / ".env").write_text("APP_ENV=local\n")

    # No raise — non-.py files simply skipped, build succeeds.
    Application.configure(tmp_path).with_environment("testing").with_config_dir(cfg).create()


def test_with_config_dir_does_not_recurse_into_subdirectories(tmp_path: Path) -> None:
    from arvel.config import ConfigKeyError, lookup

    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "app.py").write_text('NAME = "top"\n')
    nested = cfg / "nested"
    nested.mkdir()
    (nested / "deep.py").write_text('VALUE = "found"\n')

    Application.configure(tmp_path).with_environment("testing").with_config_dir(cfg).create()

    assert lookup("app.NAME") == "top"
    with pytest.raises(ConfigKeyError):
        lookup("deep.VALUE")
    with pytest.raises(ConfigKeyError):
        lookup("nested.deep.VALUE")


def test_with_config_dir_missing_directory_raises_at_create(tmp_path: Path) -> None:
    missing = tmp_path / "no_such_config_dir"

    builder = Application.configure(tmp_path).with_environment("testing").with_config_dir(missing)
    with pytest.raises((FileNotFoundError, RuntimeError)):
        builder.create()


def test_logging_config_file_does_not_shadow_stdlib(tmp_path: Path) -> None:
    """A user's config/logging.py MUST NOT replace stdlib logging in sys.modules."""
    import logging as stdlib_logging
    import sys

    from arvel.config import lookup

    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "logging.py").write_text('LEVEL = "INFO"\n')

    Application.configure(tmp_path).with_environment("testing").with_config_dir(cfg).create()

    assert sys.modules["logging"] is stdlib_logging
    assert lookup("logging.LEVEL") == "INFO"
