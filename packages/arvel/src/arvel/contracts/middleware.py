"""Contract for global ASGI middleware declared in ``bootstrap/middleware.py``."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

    from arvel.container import Container


class GlobalMiddleware(ABC):
    """A global ASGI middleware that knows how to mount itself.

    The HTTP-stack analogue of ``ServiceProvider``: declared in
    ``bootstrap/middleware.py`` and resolved by ``Application.into_asgi``. The
    framework hands each entry the ASGI app plus the root container; the entry
    reads its own config and calls ``app.add_middleware(...)`` — or returns
    without mounting when it isn't applicable for the current config.

    List order is outer→inner (the first entry is the outermost layer). The
    framework mounts entries so that order holds regardless of Starlette's
    prepend semantics.
    """

    @classmethod
    @abstractmethod
    def boot(cls, app: FastAPI, container: Container) -> None:
        """Mount this middleware onto ``app``, or skip when not applicable."""
