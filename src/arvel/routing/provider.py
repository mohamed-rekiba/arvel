"""RoutingServiceProvider — binds the Router (auto-discovered)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from arvel.kernel.service_provider import ServiceProvider
from arvel.routing import Router

if TYPE_CHECKING:
    from arvel.contracts import Container
    from arvel.kernel.application import Application


def _build_served_kernel(app: Application) -> Any:
    """The fully-configured served HttpKernel (global gate, default groups, builder middleware,
    routes applied). Shared by the ASGI builder and non-serving consumers of the compiled app —
    e.g. ``openapi:export``, which renders the OpenAPI document without binding a socket."""
    from arvel.http import HttpKernel

    kernel = HttpKernel(app=app)
    kernel.use_default_global()  # maintenance-mode 503 gate runs on every request
    kernel.use_default_groups()  # web=session+CSRF, api=throttle
    # applied here since the served kernel is built on demand, not bound under "http" (the HTTP client)
    for middleware in app.builder_middlewares:
        kernel.global_middleware.append(kernel.resolve_middleware(middleware))
    if app.bound("router"):
        app.make("router").apply_to(kernel)
    return kernel


def _build_served_asgi(app: Application) -> object:
    """Compile the served ASGI app. Lives here (routing→http is a legal downward edge)
    so ``Application.as_asgi`` can resolve it from the container rather than importing
    ``arvel.http`` directly — ``kernel→http`` would violate the boundary (DR-0026)."""
    from arvel.kernel.bootstrap import serve_lifespan

    return _build_served_kernel(app).as_asgi(lifespan=serve_lifespan(app))


class RoutingServiceProvider(ServiceProvider):
    def register(self) -> None:
        if not self.app.bound("router"):  # respect a router the app already provided

            def make_router(_app: Container) -> Router:
                return Router()

            self.app.singleton("router", make_router)
        # resolved by Application.as_asgi()
        self.app.instance("http.asgi_builder", _build_served_asgi)
        self.app.instance("http.kernel_builder", _build_served_kernel)

        # `limiter` (the RateLimiter facade root) over the app's cache — bound in a provider so it
        # resolves on ANY boot (not only the served HttpKernel path), and routing→http.rate_limiter
        # is a legal downward edge. Lazy: the factory resolves "cache" at make-time, so an app with
        # no cache only fails if something actually asks for the limiter.
        if not self.app.bound("limiter"):

            def make_limiter(app: Container) -> Any:
                from arvel.http.rate_limiter import RateLimiter

                return RateLimiter(app.make("cache"))

            self.app.singleton("limiter", make_limiter)
        # registered here (not the telemetry provider) so telemetry needn't import arvel.http;
        # done in `register` so it lands before the router compiles into the served app
        from arvel.telemetry import TelemetrySettings

        if TelemetrySettings().prometheus and self.app.bound("router"):
            from arvel.http.response import prometheus_metrics

            self.app.make("router").get("/metrics", prometheus_metrics, name="telemetry.metrics")

        # Health probes (DR-0039): /health is the readiness check — runs every registered resource's
        # health check in parallel and 503s when a critical one is down (typed, so it shows in the
        # docs). /livez is a cheap liveness probe, hidden from the schema (infra, not API).
        if self.app.bound("router"):
            from arvel.http.health import health, liveness

            router = self.app.make("router")
            router.get("/health", health, name="health")
            router.get("/livez", liveness, name="health.live").hidden()

        # The channel-authorization endpoint (spec 19): needs BOTH the authenticated user (auth)
        # and the channel-callback registry (broadcasting) — routing is the top layer, so it can
        # see both without either importing the other (broadcasting must never import auth, G1).
        if self.app.bound("router"):
            from arvel.auth.middleware import Authenticate
            from arvel.routing.broadcasting_auth import broadcasting_auth

            self.app.make("router").post(
                "/broadcasting/auth", broadcasting_auth, name="broadcasting.auth"
            ).middleware(Authenticate)

        # with_public_dir(...) — the public/ needs zero lines in routes/web.php; same here.
        if self.app.public_dir is not None and self.app.bound("router"):
            self.app.make("router").public(
                self.app.public_dir,
                path=self.app.public_path,
                spa_fallback=self.app.public_spa_fallback,
            )

    def boot(self) -> None:
        """No-op."""
