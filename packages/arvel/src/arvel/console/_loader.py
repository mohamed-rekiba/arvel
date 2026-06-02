"""Entry-point based plugin discovery for arvel.commands group."""

from __future__ import annotations

import importlib.metadata
import logging

from arvel.console import Command

_log = logging.getLogger("arvel.console")


def _instantiate(ep: importlib.metadata.EntryPoint) -> Command | None:
    """Load and instantiate one entry-point's Command, or None if it fails.

    Entry-point loading runs arbitrary user code; we broaden beyond ImportError
    because plugin authors have shipped TypeError, AttributeError, and SystemExit
    in the wild. The failure is logged per-entry-point so debugging stays sharp —
    one faulty plugin never takes down the whole CLI.
    """
    try:
        cls: type[Command] = ep.load()
    except Exception as exc:  # noqa: BLE001
        _log.warning(
            "Skipping CLI entry-point %r: %s raised on load (%s). "
            "If this is an optional command, install the matching extra.",
            ep.name,
            type(exc).__name__,
            exc,
        )
        return None
    try:
        return cls()
    except Exception as exc:  # noqa: BLE001
        _log.warning(
            "Skipping CLI entry-point %r: %s raised on instantiation (%s).",
            ep.name,
            type(exc).__name__,
            exc,
        )
        return None


def discover_commands() -> list[Command]:
    """Load every command advertised under the ``arvel.commands`` entry-point group."""
    group_eps = importlib.metadata.entry_points(group="arvel.commands")
    commands: list[Command] = []
    for ep in group_eps:
        instance = _instantiate(ep)
        if instance is not None:
            commands.append(instance)
    return commands


def entry_point_names() -> list[str]:
    """Command names from entry-point metadata only — no module imports."""
    return [ep.name for ep in importlib.metadata.entry_points(group="arvel.commands")]


def load_command(name: str) -> Command | None:
    """Load just the single command matching ``name`` without importing the rest.

    The hot path — running one concrete command — shouldn't pay to import all
    ~70 command modules. Returns None when no entry point matches ``name`` (the
    caller then falls back to full discovery so Typer can render a proper
    "no such command" with the full list).
    """
    group_eps = importlib.metadata.entry_points(group="arvel.commands")
    for ep in group_eps:
        if ep.name == name:
            return _instantiate(ep)
    return None
