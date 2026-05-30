"""Workspace-root pytest config.

Hosts two unrelated, workspace-wide concerns:

1. The FB-010 per-module coverage gate — reads
   ``[tool.coverage.arvel_per_module]`` from the workspace ``pyproject.toml``
   and, after pytest-cov has finished collecting, fails the run if any listed
   module's line coverage falls below its declared floor.

2. Shared ORM fixtures (``engine`` / ``session_maker`` / ``session``) for the
   in-memory async-SQLite + bound-session pattern used by every package's
   tests. Defined here so that ``packages/arvel-image/tests/`` and any future
   sibling package inherit them automatically through pytest's conftest
   hierarchy — without duplicating the fixture code per-package.

Living at the workspace root means pytest finds it automatically before any
test collection, no ``pytest_plugins`` indirection needed.
"""

from __future__ import annotations

import os
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest_asyncio
from arvel.database.session import reset_active_session, set_active_session
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Typer bakes FORCE_TERMINAL=True at rich_utils import when GITHUB_ACTIONS / FORCE_COLOR
# / PY_COLORS is set. Under pytest-xdist stdout isn't a real tty, so rich auto-detects a
# bad width and wraps option names — breaking help-text asserts in CI only. rich_utils is
# imported lazily on first help render, so setting these here (before any test runs) keeps
# help output identical everywhere.
os.environ.setdefault("_TYPER_FORCE_DISABLE_TERMINAL", "1")
os.environ.setdefault("TERMINAL_WIDTH", "200")

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover — guaranteed by requires-python = ">=3.14"
    import tomli as tomllib  # type: ignore[no-redef]

if TYPE_CHECKING:
    from _pytest.config import Config
    from _pytest.main import Session
    from _pytest.terminal import TerminalReporter

_PYPROJECT = Path(__file__).resolve().parent / "pyproject.toml"
_PENDING_FAILURE = False


def _load_floors() -> dict[str, float]:
    if not _PYPROJECT.exists():
        return {}
    data = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    raw = data.get("tool", {}).get("coverage", {}).get("arvel_per_module", {})
    return {str(k): float(v) for k, v in raw.items()}


def _module_coverage_percent(cov_obj: object, module_dotted: str) -> float | None:
    """Compute aggregate line coverage % for files under ``module_dotted``."""
    from coverage import Coverage

    if not isinstance(cov_obj, Coverage):
        return None

    module_prefix = module_dotted.replace(".", "/")
    total_statements = 0
    missing_statements = 0

    for filename in cov_obj.get_data().measured_files():
        norm = filename.replace("\\", "/")
        if f"/{module_prefix}/" not in norm and not norm.endswith(f"/{module_prefix}.py"):
            continue
        try:
            _, statements, _, missing, _ = cov_obj.analysis2(filename)
        except Exception:  # noqa: BLE001 — defensive against rare analysis errors
            continue
        total_statements += len(statements)
        missing_statements += len(missing)

    if total_statements == 0:
        return None
    return 100.0 * (total_statements - missing_statements) / total_statements


def pytest_terminal_summary(
    terminalreporter: "TerminalReporter", exitstatus: int, config: "Config"
) -> None:
    """Report per-module coverage and arm the session-finish failure flag."""
    global _PENDING_FAILURE
    _PENDING_FAILURE = False

    floors = _load_floors()
    if not floors:
        return

    cov_plugin = config.pluginmanager.getplugin("_cov")
    if cov_plugin is None or not getattr(cov_plugin, "cov_controller", None):
        return
    cov = getattr(cov_plugin.cov_controller, "cov", None)
    if cov is None:
        return

    failures: list[str] = []
    terminalreporter.section("Per-module coverage gates (FB-010 / ADR-017)")
    for module_dotted, floor in sorted(floors.items()):
        actual = _module_coverage_percent(cov, module_dotted)
        if actual is None:
            terminalreporter.write_line(f"  {module_dotted:<50s} [SKIP — no measured files]")
            continue
        status = "OK" if actual >= floor else "FAIL"
        terminalreporter.write_line(
            f"  {module_dotted:<50s} {actual:6.2f}% (floor {floor:5.2f}%) {status}"
        )
        if actual < floor:
            failures.append(f"{module_dotted}: {actual:.2f}% < {floor:.2f}%")

    if failures:
        terminalreporter.write_line("")
        terminalreporter.write_line("FAIL: per-module coverage gates not met (FB-010):")
        for f in failures:
            terminalreporter.write_line(f"  - {f}")
        _PENDING_FAILURE = True


def pytest_sessionfinish(session: "Session", exitstatus: int) -> None:
    """Promote per-module coverage breaches into a non-zero exit."""
    if _PENDING_FAILURE and exitstatus == 0:
        session.exitstatus = 1


# ─── Shared ORM fixtures (in-memory async SQLite + bound active session) ─────


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    """Per-test async SQLite engine."""
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest_asyncio.fixture
async def session_maker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def session(
    session_maker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with session_maker() as s:
        token = set_active_session(s)
        try:
            yield s
        finally:
            reset_active_session(token)
