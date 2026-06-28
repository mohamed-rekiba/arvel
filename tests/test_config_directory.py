"""Config directory autoload (M6) — Laravel-style ``config/*.py`` discovery at boot."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from arvel.kernel import Application
from arvel.kernel.service_provider import load_config_directory


def _config_dir(tmp_path: Any) -> Path:
    cfg = Path(str(tmp_path)) / "config"
    cfg.mkdir()
    return cfg


def test_loads_files_under_their_stem(tmp_path: Any) -> None:
    (_config_dir(tmp_path) / "app.py").write_text("config = {'name': 'from-file', 'debug': True}\n")
    app = Application(base_path=str(tmp_path))
    load_config_directory(app)
    assert app.config("app.name") == "from-file"
    assert app.config("app.debug") is True


def test_with_config_overrides_files_which_fill_gaps(tmp_path: Any) -> None:
    (_config_dir(tmp_path) / "app.py").write_text("config = {'name': 'from-file', 'tz': 'UTC'}\n")
    app = Application(base_path=str(tmp_path))
    app.make("config").set("app", {"name": "programmatic"})  # mimics with_config(...)
    load_config_directory(app)
    assert app.config("app.name") == "programmatic"  # with_config wins
    assert app.config("app.tz") == "UTC"  # the file fills the gap


def test_nested_dict_deep_merges_with_existing(tmp_path: Any) -> None:
    # The config-dir path must deep-merge a nested dict against existing config (existing wins).
    (_config_dir(tmp_path) / "services.py").write_text(
        "config = {'mail': {'host': 'smtp', 'port': 25}}\n"
    )
    app = Application(base_path=str(tmp_path))
    app.make("config").set("services", {"mail": {"host": "override"}})  # nested with_config
    load_config_directory(app)
    assert app.config("services.mail.host") == "override"  # existing nested value wins
    assert app.config("services.mail.port") == 25  # the file fills the nested gap


def test_uppercase_module_vars_fallback(tmp_path: Any) -> None:
    (_config_dir(tmp_path) / "mail.py").write_text("HOST = 'localhost'\nPORT = 25\nlower = 'x'\n")
    app = Application(base_path=str(tmp_path))
    load_config_directory(app)
    assert app.config("mail.HOST") == "localhost"
    assert app.config("mail.PORT") == 25
    assert app.config("mail.lower", "missing") == "missing"  # only UPPERCASE vars are read


def test_config_file_can_read_env(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_NAME", "env-app")
    (_config_dir(tmp_path) / "app.py").write_text(
        "from arvel import env\nconfig = {'name': env('APP_NAME', 'default')}\n"
    )
    app = Application(base_path=str(tmp_path))
    load_config_directory(app)
    assert app.config("app.name") == "env-app"


def test_missing_directory_is_noop(tmp_path: Any) -> None:
    app = Application(base_path=str(tmp_path))  # no config/ dir
    load_config_directory(app)  # must not raise
    assert app.config("app.name", "default") == "default"


def test_underscore_files_are_skipped(tmp_path: Any) -> None:
    (_config_dir(tmp_path) / "_shared.py").write_text("config = {'x': 1}\n")
    app = Application(base_path=str(tmp_path))
    load_config_directory(app)
    assert app.config("_shared", None) is None


def test_malformed_file_surfaces_an_error(tmp_path: Any) -> None:
    (_config_dir(tmp_path) / "broken.py").write_text("def =\n")  # invalid Python
    app = Application(base_path=str(tmp_path))
    with pytest.raises(SyntaxError):
        load_config_directory(app)
