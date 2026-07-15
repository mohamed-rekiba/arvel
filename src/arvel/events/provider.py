"""EventServiceProvider — binds the dispatcher (auto-discovered via entry point) and, at boot,
auto-discovers class listeners in ``app/listeners/`` by their ``handle`` type hint (DR-0046)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING, Any

from arvel.events.dispatcher import Dispatcher
from arvel.kernel.service_provider import ServiceProvider

if TYPE_CHECKING:
    from arvel.contracts import Container


def discover_listeners(app: Any, paths: list[str]) -> list[Any]:
    """Load every ``*.py`` under each ``paths`` dir (relative to ``base_path``) and return the
    listener classes they define — those with a callable ``handle``. The dispatcher's ``discover``
    then binds each to the event in its ``handle(self, event: X)`` type hint. Files are loaded **by
    path** (like ``config/*.py`` and migrations), so discovery doesn't depend on ``base_path`` being
    on ``sys.path``. A dir that doesn't exist is skipped; a module that fails to import
    (``ImportError``) is skipped — other errors propagate so a genuinely broken listener is loud."""
    found: list[Any] = []
    for rel in paths:
        directory = Path(app.base_path) / rel
        if not directory.is_dir():
            continue
        for file in sorted(directory.glob("*.py")):
            if file.stem.startswith("_"):
                continue
            spec = importlib.util.spec_from_file_location(f"_arvel_listener_{file.stem}", file)
            if spec is None or spec.loader is None:  # pragma: no cover - defensive
                continue
            module = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(module)
            except ImportError:
                continue
            found.extend(
                obj
                for obj in vars(module).values()
                # a class this module actually defines (not one it imported) with a handle()
                if isinstance(obj, type)
                and obj.__module__ == module.__name__
                and callable(getattr(obj, "handle", None))
            )
    return found


class EventServiceProvider(ServiceProvider):
    def register(self) -> None:
        def make_dispatcher(app: Container) -> Dispatcher:
            return Dispatcher(app)

        self.app.singleton("events", make_dispatcher)

    def boot(self) -> None:
        """Auto-discover class listeners from the configured dirs (default ``app/listeners``),
        unless turned off with ``config('events.discover', False)``. Explicit ``events.listen(...)``
        registration keeps working alongside this."""
        if not self.app.config("events.discover", True):
            return
        paths = self.app.config("events.discover_paths", ["app/listeners"])
        listeners = discover_listeners(self.app, paths)
        if listeners:
            self.app.make("events").discover(listeners)
