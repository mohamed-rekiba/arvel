"""Entry-point package for the Arvel e-commerce demo kit.

Exposes :func:`kit_root` so ``arvel new --kit ecommerce`` can locate the
kit source tree without hard-coding filesystem paths.
"""

from __future__ import annotations

import importlib.resources
from pathlib import Path

__all__ = ["kit_root"]


def kit_root() -> Path:
    """Return the root of the e-commerce demo kit tree.

    The kit root is the directory that contains ``backend/``, ``frontend/``,
    ``Makefile``, ``docker-compose.yml``, and ``README.md``.
    """
    # importlib.resources.files points at the installed arvel_ecommerce_demo
    # package directory (src/arvel_ecommerce_demo/). Two levels up is the
    # package root that holds the actual kit tree.
    return Path(str(importlib.resources.files("arvel_ecommerce_demo"))).parent.parent
