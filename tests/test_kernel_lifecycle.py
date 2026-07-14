"""C2b — kernel lifecycle: logging config, full lifespan (.env), graceful DB dispose."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from arvel.database.provider import DatabaseServiceProvider
from arvel.kernel import Application, set_application
from arvel.kernel.bootstrap import lifespan
from arvel.kernel.logging import LogManager, configure_logging


def test_configure_logging_both_modes() -> None:
    configure_logging(json_logs=False)
    LogManager().info("console_mode", k=1)  # must not raise
    configure_logging(json_logs=True)
    LogManager().bind(request_id="r1").info("json_mode", k=2)


async def test_lifespan_loads_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".env").write_text("LIFESPAN_TEST_VAR=present\n")
    monkeypatch.delenv("LIFESPAN_TEST_VAR", raising=False)
    app = (
        Application.configure(str(tmp_path)).with_config({"app": {"boot_report": "quiet"}}).create()
    )
    try:
        async with lifespan(app) as running:
            assert running.booted is True
            assert os.environ.get("LIFESPAN_TEST_VAR") == "present"
    finally:
        monkeypatch.delenv("LIFESPAN_TEST_VAR", raising=False)
        set_application(None)


async def test_database_provider_registers_health_checked_resource() -> None:
    # DB teardown now rides the resource lifecycle (DatabaseResource.disconnect -> dispose), driven
    # by the ResourceManager at shutdown — not a bare terminating hook on the provider (DR-0039).
    app = Application()
    app.make("config").set(
        "database",
        {"default": "pg", "connections": {"pg": {"url": "sqlite+aiosqlite:///:memory:"}}},
    )
    set_application(app)
    try:
        provider = DatabaseServiceProvider(app)
        provider.register()
        provider.boot()
        assert "database" in [r.name for r in app.resources.resources]
    finally:
        set_application(None)


def test_database_settings_reads_config_and_preserves_driver_keys() -> None:
    from arvel.database.provider import DatabaseSettings

    app = Application()
    app.make("config").set(
        "database",
        {"default": "pg", "connections": {"pg": {"url": "postgres://h/db", "pool_size": 10}}},
    )
    set_application(app)  # config() is the single source of truth (DR-0016)
    try:
        s = DatabaseSettings()
        assert s.default == "pg"
        assert s.connections["pg"]["url"] == "postgres://h/db"
        assert s.connections["pg"]["pool_size"] == 10  # driver-specific keys passed through
    finally:
        set_application(None)
