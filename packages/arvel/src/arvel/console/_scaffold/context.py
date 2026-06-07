"""Inputs handed to a kit's post-render ``finalize`` hook.

A leaf module on purpose: it imports nothing from the scaffold package, so the
kit modules and the registry can both depend on it without an import cycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ScaffoldContext:
    """State a kit's ``finalize`` hook gets once the skeleton is on disk."""

    target: Path
    # Already validated against PROJECT_NAME_REGEX — safe to inline into files.
    project_name: str
    # target / kit.python_project_subdir — where the pyproject.toml ended up.
    python_project_dir: Path
