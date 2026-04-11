"""HTTP service provider — boot-time wiring of routes and middleware.

This is a framework-level provider (priority 10) that runs during the
application boot phase. It discovers module routes, resolves middleware
aliases, and mounts the HTTP kernel. Per-route middleware is wired by
wrapping each route's ASGI app after registration.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from arvel.foundation.config import get_module_settings
from arvel.foundation.exceptions import ConfigurationError
from arvel.foundation.provider import ServiceProvider
from arvel.http.config import HttpSettings
from arvel.http.kernel import HttpKernel
from arvel.http.middleware import MiddlewareStack
from arvel.http.router import discover_routes
from arvel.logging import Log

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from typing import Any

    from arvel.foundation.application import Application
    from arvel.foundation.container import ContainerBuilder
    from arvel.http.router import RouteEntry

logger = Log.named("arvel.http.provider")


class HttpServiceProvider(ServiceProvider):
    """Framework-level provider for the HTTP and routing layer.

    Discovers module routes, resolves middleware aliases from HttpSettings,
    registers global middleware on the kernel, and mounts routes on FastAPI.
    Per-route middleware is resolved and wrapped around each route's ASGI app.
    """

    priority: int = 10

    async def register(self, container: ContainerBuilder) -> None:
        pass

    async def boot(self, app: Application) -> None:
        config = app.config
        try:
            http_settings = get_module_settings(config, HttpSettings)
        except (ConfigurationError, KeyError) as exc:
            logger.warning(
                "http_settings_fallback",
                error=str(exc),
            )
            http_settings = HttpSettings()

        kernel = HttpKernel()
        stack = MiddlewareStack(
            aliases=http_settings.middleware_aliases,
            groups=http_settings.middleware_groups,
        )

        if http_settings.middleware_aliases:
            for alias, priority in http_settings.global_middleware:
                resolved = stack.resolve([alias])
                if resolved:
                    kernel.add_global_middleware(resolved[0], priority=priority)

        routers = discover_routes(app.base_path)

        fastapi_app = app.asgi_app()
        for mod_name, router in routers:
            start_index = len(fastapi_app.routes)
            fastapi_app.include_router(router)
            added_routes = fastapi_app.routes[start_index:]
            _attach_route_middleware(
                entries=router.route_entries,
                added_routes=added_routes,
                module_name=mod_name,
                stack=stack,
            )

        if kernel.global_middleware:
            kernel.mount(fastapi_app)

        logger.debug(
            "http_boot_complete",
            routes=sum(len(r.route_entries) for _, r in routers),
            modules=len(routers),
            global_middleware=len(kernel.global_middleware),
        )


def _resolve_effective_middleware(
    middleware_names: list[str],
    exclude_names: list[str],
    stack: MiddlewareStack,
) -> list[type]:
    """Resolve route middleware, expand groups, and apply exclusions."""
    if not middleware_names:
        return []

    expanded = stack.expand(middleware_names)
    if exclude_names:
        exclude_expanded = set(stack.expand(exclude_names))
        expanded = [n for n in expanded if n not in exclude_expanded]

    if not expanded:
        return []

    return stack.resolve(expanded)


def _attach_route_middleware(
    *,
    entries: list[RouteEntry],
    added_routes: Sequence[object],
    module_name: str,
    stack: MiddlewareStack,
) -> None:
    """Apply Arvel middleware to routes after router inclusion."""
    for index, entry in enumerate(entries):
        methods_list = sorted(entry.methods)
        effective_middleware = _resolve_effective_middleware(
            entry.middleware,
            entry.without_middleware,
            stack,
        )
        if index < len(added_routes) and effective_middleware:
            _wrap_specific_route(added_routes[index], effective_middleware)
            logger.debug(
                "route_middleware_attached",
                module=module_name,
                path=entry.path,
                middleware=[cls.__name__ for cls in effective_middleware],
            )
        logger.debug(
            "route_registered",
            module=module_name,
            method=",".join(methods_list),
            path=entry.path,
            name=entry.name,
        )


def _wrap_specific_route(route: object, middleware_classes: Sequence[Callable[..., Any]]) -> None:
    """Wrap one route's ASGI app with middleware classes."""
    typed_route = cast("Any", route)
    original_app = getattr(typed_route, "app", None)
    if original_app is None:
        return

    chain = original_app
    for cls in reversed(middleware_classes):
        chain = cls(chain)
    typed_route.app = chain
