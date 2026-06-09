"""Locate installed framework package sources for source-contract tests.

These tests assert patterns in arvel / arvel-permission source. Resolving via
importlib (not a relative parents[N] path) keeps them working both in the
monorepo and in a standalone scaffolded kit, where the packages live in
site-packages rather than ../../packages/<pkg>/src.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


def package_src(name: str) -> Path:
    spec = importlib.util.find_spec(name)
    if spec is None or not spec.submodule_search_locations:
        raise RuntimeError(f"package {name!r} is not importable")
    return Path(next(iter(spec.submodule_search_locations)))


ARVEL_SRC = package_src("arvel")
ARVEL_PERMISSION_SRC = package_src("arvel_permission")
