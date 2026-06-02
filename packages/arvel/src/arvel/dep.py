"""FastAPI bridge: ``Depends(arvel.dep(MyService))`` resolves from the request scope."""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import TYPE_CHECKING, TypeVar

from arvel.container.container import Container

if TYPE_CHECKING:
    from starlette.requests import Request

T = TypeVar("T")


def dep(abstract: type[T]) -> Callable[..., T]:
    """Return a FastAPI-compatible resolver for ``abstract``.

    The resolver expects the request to expose ``request.state.arvel_scope``, an
    instance of ``arvel.container.Container`` (created per-request by the framework's
    scope middleware, shipped fully).
    """
    # starlette is loaded on first call, not at module import, so `from arvel
    # import dep` stays cheap on the CLI hot path. FastAPI reads the concrete
    # annotation set below — it doesn't need `Request` in this module's globals.
    request_cls = importlib.import_module("starlette.requests").Request

    def _resolve(request: Request) -> T:
        scoped: Container | None = getattr(request.state, "arvel_scope", None)
        if scoped is None:
            msg = (
                "Arvel request scope is not installed. "
                "Mount ArvelScopeMiddleware on your FastAPI app."
            )
            raise RuntimeError(msg)
        return scoped.make(abstract)

    _resolve.__annotations__["request"] = request_cls
    _resolve.__annotations__["return"] = abstract
    return _resolve
