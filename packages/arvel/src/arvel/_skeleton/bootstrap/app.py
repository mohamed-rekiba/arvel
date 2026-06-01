"""Application bootstrap — builds the Arvel application from the canonical layout.

Wires providers (``bootstrap/providers.py``), config (``config/``), and
routing (``routes/web.py``, ``routes/api.py``, ``routes/console.py``).
The console path is stored for the future ``arvel`` CLI.
"""

from __future__ import annotations

from pathlib import Path

from arvel import Application

_BASE_PATH = Path(__file__).resolve().parent.parent


def create_application() -> Application:
    """Build the application from the canonical Laravel-shaped layout."""
    routes_dir = _BASE_PATH / "routes"
    return (
        Application.configure(_BASE_PATH)
        .with_config_dir(_BASE_PATH / "config")
        .with_providers(_BASE_PATH / "bootstrap" / "providers.py")
        .with_routing(
            web=routes_dir / "web.py",
            api=routes_dir / "api.py",
            console=routes_dir / "console.py",
        )
        .create()
    )
