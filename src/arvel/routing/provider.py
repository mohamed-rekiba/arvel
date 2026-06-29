"""RoutingServiceProvider — binds the Router (auto-discovered)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.kernel.service_provider import ServiceProvider
from arvel.routing import Router

if TYPE_CHECKING:
    from arvel.contracts import Container


def _build_served_asgi(app: Container) -> object:
    """Compile the served ASGI app. Lives here (routing→http is a legal downward edge)
    so ``Application.as_asgi`` can resolve it from the container rather than importing
    ``arvel.http`` directly — ``kernel→http`` would violate the boundary (DR-0026)."""
    from arvel.http import HttpKernel
    from arvel.kernel.bootstrap import serve_lifespan

    kernel = HttpKernel(app=app)
    kernel.use_default_global()  # maintenance-mode 503 gate runs on every request
    kernel.use_default_groups()  # web=session+CSRF, api=throttle
    if app.bound("router"):
        app.make("router").apply_to(kernel)
    return kernel.as_asgi(lifespan=serve_lifespan(app))


class RoutingServiceProvider(ServiceProvider):
    def register(self) -> None:
        if not self.app.bound("router"):  # respect a router the app already provided
            def make_router(_app: Container) -> Router:
                return Router()

            self.app.singleton("router", make_router)
        # The kernel resolves this builder in Application.as_asgi() (DR-0026).
        self.app.instance("http.asgi_builder", _build_served_asgi)

    def boot(self) -> None:
        """No-op."""
