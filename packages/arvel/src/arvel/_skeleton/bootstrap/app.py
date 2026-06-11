"""Application bootstrap — builds the Arvel application from the canonical layout.

Wires providers (``bootstrap/providers.py``), config (``config/``), and
routing (``routes/web.py``, ``routes/api.py``, ``routes/console.py``).

``required_subsystems`` is forwarded by the ``arvel`` CLI: when present, only
the providers whose subsystem is in the set boot — the rest are skipped. The
ASGI entrypoint (``public/asgi.py``) calls this with ``None`` to get the
full chain.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from arvel import Application

if TYPE_CHECKING:
    from arvel.console._subsystem import CliSubsystem

_BASE_PATH = Path(__file__).resolve().parent.parent


def create_application(
    *,
    required_subsystems: frozenset[CliSubsystem] | None = None,
) -> Application:
    """Build the application from the canonical Laravel-shaped layout."""
    routes_dir = _BASE_PATH / "routes"
    builder = (
        Application.configure(_BASE_PATH)
        .with_config_dir(_BASE_PATH / "config")
        .with_providers(_BASE_PATH / "bootstrap" / "providers.py")
        .with_middleware(_BASE_PATH / "bootstrap" / "middleware.py")
        .with_routing(
            web=routes_dir / "web.py",
            api=routes_dir / "api.py",
            console=routes_dir / "console.py",
        )
    )
    if required_subsystems is not None:
        builder = builder.with_required_subsystems(required_subsystems)
    return builder.create()
