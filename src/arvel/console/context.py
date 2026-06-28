"""Console context — installer mode vs project mode (doc 13 §One binary, two modes).

The same ``arvel`` CLI works **before** a project exists (scaffolding: ``arvel new``) and
**inside** one (``migrate``, ``queue:work``, ``make:*``, …). It tells which by looking for
``bootstrap/app.py`` in the working directory. stdlib-only, so this stays on the T0 fast path.
"""

from __future__ import annotations

from pathlib import Path


def in_project(base: str | None = None) -> bool:
    """True when run inside an arvel project (a ``bootstrap/app.py`` is present)."""
    root = Path(base) if base is not None else Path.cwd()
    return (root / "bootstrap" / "app.py").is_file()


def console_mode(base: str | None = None) -> str:
    """``"project"`` inside an arvel project, else ``"installer"``."""
    return "project" if in_project(base) else "installer"
