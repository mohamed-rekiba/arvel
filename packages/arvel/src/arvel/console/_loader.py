"""Entry-point based plugin discovery for arvel.commands group."""

from __future__ import annotations

import importlib.metadata
import logging

from arvel.console import Command

_log = logging.getLogger("arvel.console")


def discover_commands() -> list[Command]:
    """Load commands advertised under the ``arvel.commands`` entry-point group.

    A faulty entry-point (missing extra, broken module, bad ``__init__``) must
    never take down the whole CLI bootstrap — every other plugin's commands
    still load. Each failure is logged with the entry-point name and the
    exception class so the operator knows exactly which plugin to investigate.
    """
    group_eps = importlib.metadata.entry_points(group="arvel.commands")
    commands: list[Command] = []
    for ep in group_eps:
        try:
            cls: type[Command] = ep.load()
        except Exception as exc:  # noqa: BLE001
            # Entry-point loading runs arbitrary user code; we broaden beyond
            # ImportError because plugin authors have shipped TypeError,
            # AttributeError, and SystemExit in the wild. The narrow except
            # is captured per-entry-point in the log so debugging stays sharp.
            _log.warning(
                "Skipping CLI entry-point %r: %s raised on load (%s). "
                "If this is an optional command, install the matching extra.",
                ep.name,
                type(exc).__name__,
                exc,
            )
            continue
        try:
            instance = cls()
        except Exception as exc:  # noqa: BLE001
            _log.warning(
                "Skipping CLI entry-point %r: %s raised on instantiation (%s).",
                ep.name,
                type(exc).__name__,
                exc,
            )
            continue
        commands.append(instance)
    return commands
