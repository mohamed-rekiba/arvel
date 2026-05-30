"""Docker availability probe used by the emulator fixtures.

We don't want a missing Docker daemon to raise a ``DockerException`` deep
inside testcontainers — that produces a noisy traceback and a hard fail
instead of a clean skip. The fixtures call :func:`docker_available` first
and skip with a clear, actionable message if the daemon isn't reachable.
"""

from __future__ import annotations

import importlib
from functools import lru_cache
from typing import Any


@lru_cache(maxsize=1)
def docker_available() -> bool:
    """Return ``True`` when a Docker daemon answers a ping; ``False`` otherwise.

    Cached so we only pay the round-trip once per pytest session even if
    multiple emulator fixtures are requested.
    """
    try:
        docker_mod: Any = importlib.import_module("docker")
    except ImportError:
        return False

    try:
        client: Any = docker_mod.from_env()
        client.ping()
    except Exception:  # any failure means "Docker not available"
        return False
    return True


__all__ = ["docker_available"]
