"""The current-application accessor.

A single process-wide reference to the running :class:`~arvel.contracts.Application`,
set once at bootstrap (``set_application``). The ``app()`` helper resolves the app
itself or — given an abstract — a service from its container. Facades (T2.1),
``config()`` (T1.2), and other global helpers read through this. Stdlib-only.
"""

from __future__ import annotations

from typing import Any

from arvel.contracts import Application

_application: Application | None = None


def set_application(app: Application | None) -> None:
    """Register (or clear) the running application. Called at bootstrap."""
    global _application
    _application = app


def has_application() -> bool:
    return _application is not None


def app(abstract: Any = None) -> Any:
    """Return the running application, or resolve ``abstract`` from its container."""
    if _application is None:
        raise RuntimeError("No application has been bootstrapped (call set_application).")
    return _application if abstract is None else _application.make(abstract)
