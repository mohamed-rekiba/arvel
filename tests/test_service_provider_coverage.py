"""Coverage — ServiceProvider config merge / load / publishes (doc 03)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from arvel.kernel.service_provider import ServiceProvider, _deep_merge, _load_config_file


def test_deep_merge_recursive() -> None:
    base: dict[str, Any] = {"a": {"x": 1}, "b": 2}
    _deep_merge(base, {"a": {"y": 2}, "b": 3})
    assert base == {"a": {"x": 1, "y": 2}, "b": 3}


def test_load_config_file_with_config_dict(tmp_path: Path) -> None:
    cfg = tmp_path / "cfg.py"
    cfg.write_text("config = {'k': 'v'}\nUPPER = 1\n")
    assert _load_config_file(str(cfg)) == {"k": "v"}


def test_load_config_file_uppercase_fallback(tmp_path: Path) -> None:
    cfg = tmp_path / "cfg2.py"
    cfg.write_text("NAME = 'arvel'\nlower = 9\n")
    assert _load_config_file(str(cfg)) == {"NAME": "arvel"}


def test_load_config_file_rejects_non_py(tmp_path: Path) -> None:
    # a config file is executed as Python — a non-.py path fails clearly, not as an exec error.
    cfg = tmp_path / "cfg.json"
    cfg.write_text('{"k": "v"}')
    import pytest

    with pytest.raises(ValueError, match=r"\.py module"):
        _load_config_file(str(cfg))


class _App:
    """Duck-typed stand-in exposing just the registry seam the verbs write to."""

    def __init__(self) -> None:
        self._registries: dict[str, Any] = {}

    def registry(self, key: str, factory: Any) -> Any:
        return self._registries.setdefault(key, factory())


def test_publishes_and_publishes_migrations() -> None:
    class P(ServiceProvider):
        def register(self) -> None: ...

    provider = P(_App())  # type: ignore[arg-type]
    provider.publishes({"src/a": "dst/a"}, tag="config")
    provider.publishes_migrations({"src/m": "db/m"})
    assert provider.app.registry("console.published", dict)["config"] == {"src/a": "dst/a"}
    assert provider.app.registry("console.published", dict)["migrations"] == {"src/m": "db/m"}
