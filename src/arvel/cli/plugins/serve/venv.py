"""Project virtualenv detection for ``arvel serve``."""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def _activate_project_venv(app_dir: Path) -> None:
    """Add the project's .venv site-packages to sys.path if present.

    When arvel is installed globally but the project has its own virtualenv,
    the project's dependencies won't be importable unless we inject them.
    """
    for venv_name in (".venv", "venv"):
        venv_dir = app_dir / venv_name
        if not venv_dir.is_dir():
            continue

        lib_dir = venv_dir / "lib"
        if not lib_dir.is_dir():
            continue

        for child in lib_dir.iterdir():
            sp = child / "site-packages"
            if sp.is_dir():
                sp_str = str(sp)
                if sp_str not in sys.path:
                    sys.path.insert(0, sp_str)
                os.environ["VIRTUAL_ENV"] = str(venv_dir)
                return
