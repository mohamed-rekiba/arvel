"""Config typed accessor."""

from __future__ import annotations

import pytest


def test_config_of_returns_typed_instance() -> None:
    from arvel.config import ArvelSettings, Config
    from arvel.container import Container

    class MyCfg(ArvelSettings):
        name: str = "myapp"

    c = Container()
    c.singleton(MyCfg)
    Config.bind(c)

    out = Config.of(MyCfg)
    assert isinstance(out, MyCfg)
    assert out.name == "myapp"


def test_config_of_unregistered_raises() -> None:
    from arvel.config import ArvelSettings, Config, ConfigNotRegisteredError
    from arvel.container import Container

    class MissingCfg(ArvelSettings):
        x: int = 0

    c = Container()
    Config.bind(c)
    with pytest.raises(ConfigNotRegisteredError, match="MissingCfg"):
        Config.of(MissingCfg)


def test_config_register_decorator_records_class() -> None:
    from arvel.config import ArvelSettings, register
    from arvel.config.registry import registered_configs

    @register
    class AnotherCfg(ArvelSettings):
        thing: int = 1

    assert AnotherCfg in list(registered_configs())
