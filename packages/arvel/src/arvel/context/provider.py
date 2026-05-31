"""ContextServiceProvider — reserves the context layer's place in the boot chain.

The request-scoped ``Context`` store is contextvar-backed and needs no container
binding. This provider exists so the baseline chain has a named slot for the
context layer (between logging and the database), and so ``ContextMiddleware`` /
``DeferredTaskMiddleware`` are mounted via ``Application.into_asgi()``.
"""

from __future__ import annotations

from arvel.providers.service_provider import ServiceProvider


class ContextServiceProvider(ServiceProvider):
    """Marker provider for the request-context layer."""


__all__ = ["ContextServiceProvider"]
