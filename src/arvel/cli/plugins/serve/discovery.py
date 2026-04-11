"""ASGI app discovery and import path setup for ``arvel serve``."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from arvel.cli.exceptions import ArvelCLIError

_ENTRYPOINT = "bootstrap.app:create_app"


def _discover_app(base_path: Path | None = None) -> str:
    """Ensure bootstrap/app.py exists and return the ASGI import path.

    Args:
        base_path: Project root directory. Defaults to CWD.
    """
    root = base_path or Path.cwd()
    if not (root / "bootstrap" / "app.py").is_file():
        raise ArvelCLIError(
            "bootstrap/app.py not found. Every Arvel app must have this file "
            "with a create_app() factory. Use --app to override."
        )
    return _ENTRYPOINT


def _ensure_cwd_importable(app_dir: Path | None = None) -> None:
    """Put *app_dir* (or CWD) on sys.path so uvicorn workers can import the app."""
    target = str((app_dir or Path.cwd()).resolve())
    if target not in sys.path:
        sys.path.insert(0, target)
    existing = os.environ.get("PYTHONPATH", "")
    if target not in existing.split(os.pathsep):
        os.environ["PYTHONPATH"] = f"{target}{os.pathsep}{existing}" if existing else target
