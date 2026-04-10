"""Listener auto-discovery from module listeners/ directories."""

from __future__ import annotations

import importlib.util
import inspect
from typing import TYPE_CHECKING, get_type_hints

if TYPE_CHECKING:
    from pathlib import Path

from arvel.events.event import Event
from arvel.events.listener import Listener
from arvel.logging import Log

logger = Log.named("arvel.events.discovery")


def discover_listeners(
    modules_path: Path,
) -> list[tuple[type[Event], type[Listener]]]:
    """Scan all modules under *modules_path* for listener classes.

    Returns a list of (event_type, listener_class) pairs discovered from
    files in each module's ``listeners/`` directory. Files that don't
    contain a valid Listener subclass are silently skipped.
    """
    discovered: list[tuple[type[Event], type[Listener]]] = []

    if not modules_path.is_dir():
        return discovered

    for module_dir in sorted(modules_path.iterdir()):
        if not module_dir.is_dir():
            continue

        listeners_dir = module_dir / "listeners"
        if not listeners_dir.is_dir():
            continue

        for py_file in sorted(listeners_dir.glob("*.py")):
            if py_file.name.startswith("__"):
                continue
            _load_listeners_from_file(py_file, discovered)

    return discovered


def _load_listeners_from_file(
    py_file: Path,
    out: list[tuple[type[Event], type[Listener]]],
) -> None:
    """Import a single .py file and extract Listener subclasses."""
    module_name = f"_discovered_listener_{py_file.stem}_{id(py_file)}"
    spec = importlib.util.spec_from_file_location(module_name, py_file)
    if spec is None or spec.loader is None:
        return

    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception:
        logger.warning("listener_load_failed", file=str(py_file), exc_info=True)
        return

    for _name, obj in inspect.getmembers(module, inspect.isclass):
        if obj is Listener or not issubclass(obj, Listener):
            continue

        event_type = _resolve_event_type(obj)
        if event_type is None:
            continue

        out.append((event_type, obj))


def _resolve_event_type(listener_class: type[Listener]) -> type[Event] | None:
    """Extract the event type from the handle() method's type hint."""
    handle_method = getattr(listener_class, "handle", None)
    if handle_method is None:
        return None

    try:
        hints = get_type_hints(handle_method)
    except Exception:
        return None

    hint = hints.get("event")
    if hint is None:
        params = list(inspect.signature(handle_method).parameters.values())
        if len(params) >= 2:
            hint = hints.get(params[1].name)

    if hint is None or not isinstance(hint, type) or not issubclass(hint, Event):
        return None

    return hint
