"""CLI built-ins via arvel.commands entry-points.

Tests for:
 pyproject.toml declares [project.entry-points."arvel.commands"]
 Entry-points list covers all 24 expected built-ins + reverb:start
 console.entrypoint.get_commands collapses to discover_commands
 arvel --help displays the same 24 commands (regression guard)
 Queue commands stay OUT of the entry-points group
 discover_commands tolerates ImportError from individual entry-points
 Discovery test pins expected names so future removal fails CI
"""

from __future__ import annotations

import importlib.metadata
import logging
import tomllib
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from arvel.console._loader import discover_commands
from arvel.console.entrypoint import get_commands

# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def pyproject_data() -> dict[str, Any]:
    """Parse the framework package's pyproject.toml."""
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    data: dict[str, Any] = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    return data


@pytest.fixture(scope="module")
def entry_points_table(pyproject_data: dict[str, Any]) -> dict[str, str]:
    """Return the `[project.entry-points."arvel.commands"]` table."""
    project: dict[str, Any] = pyproject_data["project"]
    eps: dict[str, dict[str, str]] = project.get("entry-points", {})
    return eps.get("arvel.commands", {})


# ─── / : pyproject declares all expected entry-points ──────


EXPECTED_BUILTINS = {
    # make:* generators ( core + additions)
    "make:controller",
    "make:model",
    "make:service",
    "make:job",
    "make:event",
    "make:middleware",
    "make:policy",
    "make:provider",
    "make:request",
    "make:seeder",
    "make:migration",
    "make:test",
    "make:factory",
    "make:listener",
    "make:notification",
    "make:mail",
    "make:command",
    "make:resource",
    "make:cast",
    "make:observer",
    "make:channel",
    "make:view",
    # publishing — replaces the old per-table make:<feature>-table commands
    "vendor:publish",
    "config:publish",
    # migrate family ( + )
    "migrate",
    "migrate:rollback",
    "migrate:status",
    "migrate:fresh",
    "migrate:reset",
    "migrate:refresh",
    # ops + infra
    "route:list",
    "db:seed",
    "db:show",
    "db:table",
    "config:show",
    "model:show",
    "channel:list",
    "event:list",
    "key:rotate",
    "about",
    "shell",
    "tinker",
    "storage:link",
    "storage:unlink",
    "auth:clear-resets",
    "test",
    "down",
    "up",
    # queue ops (entry-point safe — DI-required ones still live in )
    "queue:restart",
    "queue:clear",
    "queue:prune-failed",
    # cache
    "cache:clear",
    "cache:forget",
    "view:clear",
    # schedule
    "schedule:work",
    "schedule:list",
    "schedule:run",
    # reverb (newly reachable when [broadcasting] installed)
    "reverb:start",
}


QUEUE_COMMANDS_THAT_MUST_NOT_BE_IN_ENTRY_POINTS = {
    "queue:work",
    "queue:failed",
    "queue:retry",
    "queue:flush",
    "queue:forget",
}


def test_pyproject_declares_arvel_commands_entry_points_table(
    entry_points_table: dict[str, str],
) -> None:
    """pyproject.toml has the [project.entry-points."arvel.commands"] table."""
    assert entry_points_table, (
        '[project.entry-points."arvel.commands"] section is missing '
        "from packages/arvel/pyproject.toml"
    )


@pytest.mark.parametrize("command_name", sorted(EXPECTED_BUILTINS))
def test_each_builtin_is_declared_as_entry_point(
    entry_points_table: dict[str, str], command_name: str
) -> None:
    """/ : every expected built-in is declared as an entry-point."""
    assert command_name in entry_points_table, (
        f"Built-in {command_name!r} is missing from "
        '[project.entry-points."arvel.commands"] in pyproject.toml'
    )
    target = entry_points_table[command_name]
    assert ":" in target, (
        f"Entry-point target for {command_name!r} must be 'module.path:ClassName', got {target!r}"
    )


@pytest.mark.parametrize("command_name", sorted(QUEUE_COMMANDS_THAT_MUST_NOT_BE_IN_ENTRY_POINTS))
def test_queue_commands_are_not_declared_as_entry_points(
    entry_points_table: dict[str, str], command_name: str
) -> None:
    """queue commands need DI; they must NOT be declared as entry-points."""
    assert command_name not in entry_points_table, (
        f'Queue command {command_name!r} must NOT be in [project.entry-points."arvel.commands"] '
        "— it needs DI and is intentionally deferred to WI-arvel-021."
    )


# ─── : get_commands() collapses to discover_commands() ──────────────


def test_entrypoint_get_commands_returns_only_discover_commands_result() -> None:
    """get_commands no longer composes a hardcoded list."""
    import inspect

    import arvel.console.entrypoint as entrypoint_mod

    src = inspect.getsource(entrypoint_mod.get_commands)
    # Discover-commands MUST be the sole source.
    assert "discover_commands" in src
    # The hardcoded built_in list MUST be gone.
    assert "built_in" not in src, (
        "get_commands() must no longer hardcode a built_in list — entry-points handle it now"
    )
    # No direct command-class instantiations inside get_commands().
    forbidden = [
        "MakeControllerCommand(",
        "MigrateCommand(",
        "AboutCommand(",
        "ScheduleWorkCommand(",
        "CacheClearCommand(",
        "StorageLinkCommand(",
    ]
    for needle in forbidden:
        assert needle not in src, (
            f"get_commands() must not instantiate {needle!r} directly anymore; "
            "use the entry-points declaration in pyproject.toml"
        )


# ─── : arvel --help discovers all expected built-ins via entry-points


def test_discover_commands_finds_all_expected_builtins_against_installed_wheel() -> None:
    """+ : at runtime, the installed wheel exposes every expected command."""
    eps = importlib.metadata.entry_points(group="arvel.commands")
    discovered_names = {ep.name for ep in eps}

    # Some optional commands may legitimately be absent depending on extras
    # installed in the test env. The hard floor is: every CORE built-in
    # we used to ship hardcoded must be discoverable.
    core_required = EXPECTED_BUILTINS - {"reverb:start"}
    missing = core_required - discovered_names
    assert not missing, (
        f"Core built-ins missing from installed entry-points: {sorted(missing)}. "
        "Either pyproject.toml is incomplete or the wheel was not re-installed after "
        "the entry-points change (try `uv sync --reinstall-package arvel`)."
    )


def test_get_commands_returns_at_least_core_builtins_at_runtime() -> None:
    """get_commands resolves the core built-ins via the installed wheel."""
    commands = get_commands()
    names = {c.name for c in commands}
    core_required = EXPECTED_BUILTINS - {"reverb:start"}
    missing = core_required - names
    assert not missing, (
        f"get_commands() did not resolve {sorted(missing)}. "
        "Re-run `uv sync` to refresh the installed entry-points table."
    )


# ─── D: ImportError-tolerant entry-point loader ─────────────────────


def test_discover_commands_skips_entry_point_that_raises_importerror(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """D: a single ImportError-raising entry-point must NOT abort discovery."""

    broken_ep = MagicMock()
    broken_ep.name = "broken:cmd"
    broken_ep.load.side_effect = ImportError("optional dependency missing")

    class _GoodCmd:
        name = "good"
        help = "Good command"

        def register(self, *_args: object, **_kwargs: object) -> None:
            pass

        def handle(self, *_args: object, **_kwargs: object) -> int:
            return 0

    good_ep = MagicMock()
    good_ep.name = "good"
    good_ep.load.return_value = _GoodCmd

    with (
        patch(
            "arvel.console._loader.importlib.metadata.entry_points",
            return_value=[broken_ep, good_ep],
        ),
        caplog.at_level(logging.WARNING, logger="arvel.console"),
    ):
        commands = discover_commands()

    # The good command was registered.
    assert any(getattr(c, "name", None) == "good" for c in commands), (
        "discover_commands() must continue past an ImportError and register the next entry-point"
    )
    # The broken one was logged.
    assert any("broken:cmd" in rec.message for rec in caplog.records), (
        "discover_commands() must log a warning naming the broken entry-point"
    )


def test_discover_commands_logs_runtime_errors_and_continues(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """supersedes the old "RuntimeError propagates" behavior.

    A faulty plugin must never take down the whole CLI bootstrap; the error
    class is captured in the log message so the operator still has a clear
    pointer to the broken entry-point.
    """
    broken_ep = MagicMock()
    broken_ep.name = "broken:cmd"
    broken_ep.load.side_effect = RuntimeError("real bug in command module")

    with (
        patch(
            "arvel.console._loader.importlib.metadata.entry_points",
            return_value=[broken_ep],
        ),
        caplog.at_level(logging.WARNING, logger="arvel.console"),
    ):
        commands = discover_commands()

    assert commands == []
    assert any(
        "broken:cmd" in rec.message and "RuntimeError" in rec.message for rec in caplog.records
    )
