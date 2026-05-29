"""FastAPI bridge: ``Depends(arvel.dep(MyService))`` resolves from the request scope."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from starlette.requests import Request

from arvel.container.container import Container

T = TypeVar("T")


def dep(abstract: type[T]) -> Callable[..., T]:
    """Return a FastAPI-compatible resolver for ``abstract``.

    The resolver expects the request to expose ``request.state.arvel_scope``, an
    instance of ``arvel.container.Container`` (created per-request by the framework's
    scope middleware, shipped fully in WI-arvel-002).
    """

    def _resolve(request: Request) -> T:
        scoped: Container | None = getattr(request.state, "arvel_scope", None)
        if scoped is None:
            msg = (
                "Arvel request scope is not installed. "
                "Mount ArvelScopeMiddleware on your FastAPI app."
            )
            raise RuntimeError(msg)
        return scoped.make(abstract)

    _resolve.__annotations__["return"] = abstract
    return _resolve
