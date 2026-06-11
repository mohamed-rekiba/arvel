"""Tests for config:cache, config:clear, and the ApplicationBuilder cache integration."""

from __future__ import annotations

import json
import types
from pathlib import Path
from unittest.mock import patch

import pytest
from arvel.config._lookup_registry import (
    dump_config_cache,
    load_from_cache,
    register,
    reset,
    to_jsonable,
)
from arvel.console import Application as ConsoleApplication
from arvel.console.commands.config_commands import ConfigCacheCommand, ConfigClearCommand
from typer.testing import CliRunner

# ---------------------------------------------------------------------------
# to_jsonable
# ---------------------------------------------------------------------------


class TestToJsonable:
    def test_primitives(self) -> None:
        assert to_jsonable(None) is None
        assert to_jsonable(True) is True
        assert to_jsonable(42) == 42
        assert to_jsonable(3.14) == 3.14
        assert to_jsonable("hello") == "hello"

    def test_list_and_tuple(self) -> None:
        assert to_jsonable([1, "x", None]) == [1, "x", None]
        assert to_jsonable((1, 2)) == [1, 2]

    def test_dict(self) -> None:
        assert to_jsonable({"a": 1, "b": [2, 3]}) == {"a": 1, "b": [2, 3]}

    def test_pydantic_model(self) -> None:
        from pydantic import BaseModel

        class M(BaseModel):
            x: int = 5

        result = to_jsonable(M())
        assert result == {"x": 5}

    def test_unserializable_raises(self) -> None:
        with pytest.raises(TypeError):
            to_jsonable(object())


# ---------------------------------------------------------------------------
# dump_config_cache / load_from_cache round trip
# ---------------------------------------------------------------------------


class TestConfigCacheRoundTrip:
    def test_round_trip_primitives(self, tmp_path: Path) -> None:
        reset()
        mod = types.SimpleNamespace(FOO="bar", NUM=42, FLAG=True)
        register("app", mod)

        dest = tmp_path / "bootstrap" / "cache" / "config.json"
        written = dump_config_cache(dest)
        assert written == 1
        assert dest.exists()

        reset()
        ok = load_from_cache(dest)
        assert ok is True

        from arvel.config._lookup_registry import lookup

        assert lookup("app.FOO") == "bar"
        assert lookup("app.NUM") == 42

    def test_skips_unserializable_attrs(self, tmp_path: Path) -> None:
        reset()
        mod = types.SimpleNamespace(GOOD="value", BAD=object())
        register("misc", mod)

        dest = tmp_path / "config.json"
        dump_config_cache(dest)
        data = json.loads(dest.read_text())
        assert "GOOD" in data["misc"]
        assert "BAD" not in data["misc"]

    def test_load_returns_false_on_missing_file(self, tmp_path: Path) -> None:
        assert load_from_cache(tmp_path / "nonexistent.json") is False

    def test_load_returns_false_on_invalid_json(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("not json{")
        assert load_from_cache(bad) is False


class TestSecretRedaction:
    """dump_config_cache must never persist credentials to disk."""

    def test_secret_keys_are_stripped(self, tmp_path: Path) -> None:
        reset()
        register(
            "database",
            types.SimpleNamespace(
                default="postgresql",
                connections={
                    "postgresql": {
                        "host": "db.internal",
                        "password": "super-secret",
                        "username": "app",
                    }
                },
            ),
        )
        register(
            "filesystems",
            types.SimpleNamespace(
                disks={"s3": {"bucket": "media", "key": "AKIA...", "secret": "shhh"}}
            ),
        )

        dest = tmp_path / "config.json"
        dump_config_cache(dest)
        raw = dest.read_text()
        data = json.loads(raw)

        pg = data["database"]["connections"]["postgresql"]
        assert pg["host"] == "db.internal"
        assert "password" not in pg
        s3 = data["filesystems"]["disks"]["s3"]
        assert s3["bucket"] == "media"
        assert "key" not in s3
        assert "secret" not in s3
        # Belt and suspenders: the literal secret values never hit the file.
        assert "super-secret" not in raw
        assert "shhh" not in raw


# ---------------------------------------------------------------------------
# ApplicationBuilder cache integration
# ---------------------------------------------------------------------------


class TestApplicationBuilderConfigCache:
    def test_cache_file_skips_py_load(self, tmp_path: Path) -> None:
        """When bootstrap/cache/config.json exists, Python files are not loaded."""
        cache_file = tmp_path / "bootstrap" / "cache" / "config.json"
        cache_file.parent.mkdir(parents=True)
        cache_file.write_text(json.dumps({"myapp": {"KEY": "from_cache"}}))

        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "myapp.py").write_text('KEY = "from_file"\n')

        from arvel.application.application import ApplicationBuilder
        from arvel.config._lookup_registry import lookup

        reset()
        builder = ApplicationBuilder(tmp_path)
        builder.with_config_dir(config_dir)
        builder.create()

        assert lookup("myapp.KEY") == "from_cache"

    def test_missing_cache_falls_back_to_py(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "myapp.py").write_text('KEY = "from_file"\n')

        from arvel.application.application import ApplicationBuilder
        from arvel.config._lookup_registry import lookup

        reset()
        builder = ApplicationBuilder(tmp_path)
        builder.with_config_dir(config_dir)
        builder.create()

        assert lookup("myapp.KEY") == "from_file"


# ---------------------------------------------------------------------------
# ConfigCacheCommand
# ---------------------------------------------------------------------------


class TestConfigCacheCommand:
    def test_command_writes_cache_and_echoes_count(self, tmp_path: Path) -> None:
        reset()
        mod = types.SimpleNamespace(VAL="hello")
        register("cfg", mod)

        cmd = ConfigCacheCommand()
        with patch.object(cmd, "cache_path", return_value=tmp_path / "config.json"):
            app = ConsoleApplication([cmd])
            result = CliRunner().invoke(app.typer_app, ["config:cache"])

        assert result.exit_code == 0, result.output
        assert "cached" in result.output
        assert (tmp_path / "config.json").exists()

    def test_cache_path_falls_back_to_cwd(self) -> None:
        cmd = ConfigCacheCommand()
        cmd.app = None
        p = cmd.cache_path()
        assert p.name == "config.json"


# ---------------------------------------------------------------------------
# ConfigClearCommand
# ---------------------------------------------------------------------------


class TestConfigClearCommand:
    def test_clears_existing_cache(self, tmp_path: Path) -> None:
        reset()
        cache = tmp_path / "bootstrap" / "cache" / "config.json"
        cache.parent.mkdir(parents=True)
        cache.write_text("{}")

        cmd = ConfigClearCommand()
        app = ConsoleApplication([cmd])
        with patch(
            "arvel.console.commands.config_commands.Path.cwd",
            return_value=tmp_path,
        ):
            result = CliRunner().invoke(app.typer_app, ["config:clear"])

        assert result.exit_code == 0, result.output

    def test_no_error_when_cache_missing(self) -> None:
        cmd = ConfigClearCommand()
        app = ConsoleApplication([cmd])
        result = CliRunner().invoke(app.typer_app, ["config:clear"])
        assert result.exit_code == 0
        assert "nothing to clear" in result.output.lower()


# ---------------------------------------------------------------------------
# _config_cache_path — cache and clear must agree on the same base_path file
# ---------------------------------------------------------------------------


class TestConfigCachePathResolution:
    def test_cache_and_clear_resolve_same_base_path_file(self, tmp_path: Path) -> None:
        from arvel.console.commands.config_commands import config_cache_path

        app = types.SimpleNamespace(base_path=lambda: tmp_path)

        cache_target = ConfigCacheCommand()
        cache_target.app = app  # type: ignore[assignment]
        clear_target = ConfigClearCommand()
        clear_target.app = app  # type: ignore[assignment]

        expected = tmp_path / "bootstrap" / "cache" / "config.json"
        assert cache_target.cache_path() == expected
        assert config_cache_path(clear_target.app) == expected  # type: ignore[arg-type]

    def test_falls_back_to_cwd_without_app(self) -> None:
        from arvel.console.commands.config_commands import config_cache_path

        p = config_cache_path(None)
        assert p.parts[-3:] == ("bootstrap", "cache", "config.json")
