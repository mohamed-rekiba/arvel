"""Shared fixtures for the Arvel test suite."""

from __future__ import annotations

import inspect
import os
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

_SETTINGS_ENV_PREFIXES = (
    "APP_",
    "BROADCAST_",
    "CACHE_",
    "DB_",
    "HTTP_",
    "LOCK_",
    "MAIL_",
    "MEDIA_",
    "NOTIFICATION_",
    "OBSERVABILITY_",
    "OIDC_",
    "QUEUE_",
    "SCHEDULER_",
    "SECURITY_",
    "STORAGE_",
)


_TEST_ENV_OVERRIDES: dict[str, str] = {
    "STORAGE_LOCAL_ROOT": ".tests/storage/app",
    "OBSERVABILITY_LOG_CHANNEL_PATHS": """{
        "single": ".tests/storage/logs/app.log",
        "daily": ".tests/storage/logs/app-daily.log"
    }""",
}


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove Docker/service env vars, then inject test-specific overrides.

    Routes storage and log artifacts into ``.tests/`` (gitignored) so tests
    don't pollute the working tree.
    """
    for key in list(os.environ):
        if key.startswith(_SETTINGS_ENV_PREFIXES):
            monkeypatch.delenv(key)
    for key, value in _TEST_ENV_OVERRIDES.items():
        monkeypatch.setenv(key, value)


_DB_TEST_DIRS = ("/data/", "/testing_pkg/", "/audit/", "/activity/")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Auto-mark async tests with anyio and DB tests with the db marker.

    - Every ``async def`` test gets ``@pytest.mark.anyio`` automatically.
    - Tests under DB-using directories get ``@pytest.mark.db``.
    """
    anyio_marker = pytest.mark.anyio
    db_marker = pytest.mark.db
    for item in items:
        fspath = str(item.fspath)
        if item.get_closest_marker("anyio") is None and hasattr(item, "function"):
            fn = item.function
            if hasattr(fn, "__wrapped__") or inspect.iscoroutinefunction(fn):
                item.add_marker(anyio_marker)
        if any(d in fspath for d in _DB_TEST_DIRS) and item.get_closest_marker("db") is None:
            item.add_marker(db_marker)


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a minimal Arvel project structure in a temp directory."""
    bootstrap_dir = tmp_path / "bootstrap"
    bootstrap_dir.mkdir(parents=True)
    (bootstrap_dir / "providers.py").write_text("providers = []\n")
    (tmp_path / ".env").write_text("APP_NAME=TestApp\nAPP_ENV=development\nAPP_DEBUG=true\n")
    return tmp_path


@pytest.fixture
def tmp_project_with_modules(tmp_project: Path) -> Path:
    """Project with two valid service providers via bootstrap/providers.py."""
    (tmp_project / "bootstrap" / "providers.py").write_text(
        "from arvel.foundation.provider import ServiceProvider\n\n"
        "class UsersProvider(ServiceProvider):\n"
        "    async def register(self, container):\n"
        "        pass\n\n"
        "    async def boot(self, app):\n"
        "        pass\n\n"
        "class BillingProvider(ServiceProvider):\n"
        "    async def register(self, container):\n"
        "        pass\n\n"
        "    async def boot(self, app):\n"
        "        pass\n\n"
        "providers = [UsersProvider, BillingProvider]\n"
    )
    return tmp_project


@pytest.fixture
def tmp_project_no_modules(tmp_project: Path) -> Path:
    """Project with bootstrap/providers.py and an empty providers list."""
    return tmp_project


@pytest.fixture
def tmp_project_bad_provider(tmp_project: Path) -> Path:
    """bootstrap/providers.py exists but does not define a ``providers`` list."""
    (tmp_project / "bootstrap" / "providers.py").write_text(
        "# Invalid — no module-level providers list\nx = 42\n"
    )
    return tmp_project
