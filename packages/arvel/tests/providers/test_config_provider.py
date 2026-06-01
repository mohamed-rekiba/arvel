"""ConfigServiceProvider."""

from __future__ import annotations

from pathlib import Path


async def test_config_provider_registers_user_configs(tmp_path: Path) -> None:
    from arvel import Application
    from arvel.config import ArvelSettings, Config
    from arvel.providers import ConfigServiceProvider

    class MyCfg(ArvelSettings):
        thing: int = 42

    app = (
        Application.configure(tmp_path)
        .with_environment("testing")
        .with_config_files([MyCfg])
        .with_providers([ConfigServiceProvider])
        .create()
    )
    await app.boot()

    out = Config.of(MyCfg)
    assert out.thing == 42

    await app.shutdown()


async def test_config_provider_validation_error_aborts_boot(tmp_path: Path) -> None:
    import os

    import pytest
    from arvel import Application, BootError
    from arvel.config import ArvelSettings
    from arvel.providers import ConfigServiceProvider

    class StrictCfg(ArvelSettings):
        port: int = 5432

    os.environ["STRICT_CFG_PORT"] = "not-an-int"
    try:
        app = (
            Application.configure(tmp_path)
            .with_environment("testing")
            .with_config_files([StrictCfg])
            .with_providers([ConfigServiceProvider])
            .create()
        )
        with pytest.raises(BootError):
            await app.boot()
    finally:
        os.environ.pop("STRICT_CFG_PORT", None)
