"""Maintenance mode subsystem (WI-arvel-023, ADR-072).

Two-layer design:

- :class:`MaintenanceModeManager` owns the on-disk marker file at
  ``storage/framework/down`` and the JSON read/write logic.
- :class:`MaintenanceModeMiddleware` is the Starlette/ASGI middleware that
  reads the manager on every request and returns 503 (or passes through with
  bypass) accordingly.

The manager is normally bound on the container by ``HttpServiceProvider``.
The middleware is registered conditionally inside ``Application.into_asgi()``
when the manager binding is present.
"""

from arvel.maintenance.manager import MaintenanceMarker, MaintenanceModeManager
from arvel.maintenance.middleware import MaintenanceModeMiddleware

__all__ = [
    "MaintenanceMarker",
    "MaintenanceModeManager",
    "MaintenanceModeMiddleware",
]
